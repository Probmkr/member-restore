from datetime import datetime
from sys import stdout
from typing import Any, List, TypeAlias, TypedDict
from dotenv import load_dotenv
import asyncio
import aiohttp
import aiomysql
from pydrive2.drive import GoogleDrive
from pydrive2.auth import GoogleAuth
from oauth2client.service_account import ServiceAccountCredentials
import os
import subprocess

from db import DBC, TokenData
# import disnake

GDRIVE_CREDENTIALS_FILE = "secrets/credentials.json"
API_START_POINT_V10 = "https://discord.com/api/v10"
API_START_POINT = "https://discord.com/api"
DATA_DIR = "data"
JSON_DATA_PATH = f"{DATA_DIR}/data.json"
SQL_DATA_PATH = f"{DATA_DIR}/sql.dump"

load_dotenv()
GDRIVE_CREDENTIALS = os.getenv("GDRIVE_CREDENTIALS")
GDRIVE_SQL_DATA_ID = os.getenv("GOOGLE_DRIVE_SQL_DATA_URL")
DATABASE_URL = os.getenv("DATABASE_URL")

if not os.path.isfile(GDRIVE_CREDENTIALS_FILE):
    if not GDRIVE_CREDENTIALS:
        raise Exception("[!] GDRIVE_CREDENTIALSが設定されていません")
    print("[+] {}がないので環境変数から書き込みます".format(GDRIVE_CREDENTIALS_FILE))
    with open(GDRIVE_CREDENTIALS_FILE, "w") as f:
        f.write(GDRIVE_CREDENTIALS)
    print("[+] 書き込みが完了しました")


def write_userdata(userdata: str):
    open(JSON_DATA_PATH, "w").write(userdata)


gauth = GoogleAuth()
scope = ["https://www.googleapis.com/auth/drive"]
gauth.auth_method = "service"
gauth.credentials = ServiceAccountCredentials.from_json_keyfile_name(
    GDRIVE_CREDENTIALS_FILE, scope)
drive = GoogleDrive(gauth)


def load_data_file(file_id: str):
    f = drive.CreateFile({"id": file_id})
    plain_data = f.GetContentString()
    open(JSON_DATA_PATH, "w").write(plain_data)


class SqlBackupManager:
    database_url: str
    drive: GoogleDrive
    local_backup_file: str
    remote_backup_file: str
    using_local_file: bool

    def __init__(self, remote_backup_file_id: str, local_backup_file: str, gdrive: GoogleDrive, *, database_url: str = DATABASE_URL):
        self.database_url = database_url
        self.drive = gdrive
        self.local_backup_file = local_backup_file
        self.remote_backup_file = remote_backup_file_id
        self.using_local_file = False

    def silent_shell(self, cmd: str) -> None:
        return subprocess.call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    def use_file(self):
        while self.using_local_file:
            pass
        self.using_local_file = True

    def user_file_done(self):
        self.using_local_file = False

    def dump(self) -> None:
        self.use_file()
        self.silent_shell("pg_dump -Fc --no-acl --no-owner -d '{}' > {}".format(
            self.database_url, self.local_backup_file))
        self.user_file_done()

    def restore(self, restore_file: str = None) -> None:
        if restore_file == None:
            restore_file = self.local_backup_file
        self.use_file()
        self.silent_shell(
            "pg_restore --verbose --clean --no-acl --no-owner -d '{}' {}".format(self.database_url, restore_file))
        self.user_file_done()

    def backup_from_local_file(self) -> bool:
        remote_file = self.drive.CreateFile({"id": self.remote_backup_file})
        if not remote_file:
            print("[!] その id のファイルは存在しません")
            return False
        self.use_file()
        remote_file.SetContentFile(self.local_backup_file)
        self.user_file_done()
        remote_file.Upload()
        return True

    def backup_from_database(self) -> bool:
        self.dump()
        return self.backup_from_local_file()

    def restore_from_remote_file(self):
        print("[+] ドライブからデータベース情報を取得します")
        remote_file = self.drive.CreateFile({"id": self.remote_backup_file})
        self.use_file()
        remote_file.GetContentFile(self.local_backup_file)
        self.user_file_done()
        self.restore()
        return True


class DiscordUser(TypedDict):
    id: str
    username: str
    discriminator: str
    avatar: str
    bot: str
    system: str
    mfa_enabled: str
    banner: str
    accent_color: str
    locale: str
    verified: str
    email: str
    flags: str
    premium_type: str
    public_flags: str


class BadUsers(TypedDict):
    bad_users: List[int]
    del_users: List[int]


class utils:
    database_url: str
    token: str
    client_id: int
    client_secret: str
    redirect_uri: str

    def __init__(self, database_url, token, client_id, client_secret, redirect_uri):
        self.database_url = database_url
        self.token = token
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    async def update_token(self, *, dont_check_time=False, dont_update=False) -> BadUsers:
        bad_users = []
        del_users = []
        db = DBC(self.database_url)
        users_token_data: List[TokenData] = db.get_user_tokens()
        async with aiohttp.ClientSession() as session:
            for old_token_data in users_token_data:
                try:
                    if datetime.utcnow().timestamp() - old_token_data["last_update"] < 604800 and not dont_check_time or dont_update:
                        print("skipped")
                        continue
                    res_data = None
                    post_headers = {
                        "Content-Type": "application/x-www-form-urlencoded"}
                    post_data = {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "grant_type": "refresh_token",
                        "refresh_token": old_token_data["refresh_token"]}
                    endpoint = f"{API_START_POINT_V10}/oauth2/token"
                    while True:
                        temp = await session.post(endpoint, data=post_data, headers=post_headers)
                        res_data = await temp.json()
                        if "message" in res_data and res_data["message"] == "You are being rate limited.":
                            print("[!] Rate Limited. Sleeping {}s".format(
                                res_data["retry_after"]))
                            await asyncio.sleep(res_data["retry_after"])
                        elif "error" in res_data or "access_token" not in res_data:
                            print("[!] ユーザー:`{}` のトークンは以下の理由で更新できませんでした: `{}`".format(
                                old_token_data["user_id"], res_data["error"]))
                            bad_users.append(old_token_data["user_id"])
                            break
                        else:
                            res_data["last_update"] = datetime.utcnow(
                            ).timestamp()
                            token_data: TokenData = {
                                "user_id": old_token_data["user_id"], **res_data}
                            db.update_user_token(token_data)
                            user_data: DiscordUser = await self.get_user(res_data["access_token"])
                            print("[+] updated {}".format(
                                user_data["username"] + "#" + user_data["discriminator"]))
                            break
                except KeyError:
                    # del_users.append(user["user_id"])
                    pass
        return {"bad_users": bad_users, "del_users": del_users}

    async def get_token(self, code: str) -> dict:
        post_headers = {"content-type": "application/x-www-form-urlencoded"}
        post_data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "code": code,
            "grant_type": "authorization_code"}
        endpoint = f"{API_START_POINT_V10}/oauth2/token"
        async with aiohttp.ClientSession() as session:
            while True:
                temp = await session.post(endpoint, data=post_data, headers=post_headers)
                res_data = await temp.json()
                if "message" in res_data and res_data["message"] == "You are being rate limited.":
                    print("[!] Rate Limited. Sleeping {}s".format(
                        res_data["retry_after"]))
                    await asyncio.sleep(res_data["retry_after"])
                else:
                    return res_data

    async def get_user(self, access_token):
        endpoint = f"{API_START_POINT_V10}/users/@me"
        get_headers = {"Authorization": f"Bearer {access_token}"}
        async with aiohttp.ClientSession() as session:
            while True:
                temp = await session.get(endpoint, headers=get_headers)
                res_data = await temp.json()
                if "message" in res_data and res_data["message"] == "You are being rate limited.":
                    print("[!] Rate Limited. Sleeping {}s".format(
                        res_data["retry_after"]))
                    await asyncio.sleep(res_data["retry_after"])
                else:
                    return res_data

    async def add_role(self, guild_id, user_id, role_id) -> bool:
        endpoint = "{}/guilds/{}/members/{}/roles/{}".format(
            API_START_POINT_V10,
            guild_id,
            user_id,
            role_id)
        put_headers = {"authorization": f"Bot {self.token}"}
        async with aiohttp.ClientSession() as session:
            while True:
                temp = await session.put(endpoint, headers=put_headers)
                if temp.status == 204:
                    return True
                try:
                    json_data = await temp.json()
                    if "message" in json_data:
                        if json_data["message"] == "You are being rate limited.":
                            print("[!] Rate Limited. Sleeping {}s".format(
                                json_data["retry_after"]))
                            await asyncio.sleep(json_data["retry_after"])
                        else:
                            return False
                    else:
                        return True
                except Exception as e:
                    print("[!] エラーが発生しました:{}".format(e))
                    print(temp)
                    return False

    async def join_guild(self, access_token, guild_id, user_id) -> bool:
        endpoint = "{}/guilds/{}/members/{}".format(
            API_START_POINT_V10,
            guild_id,
            user_id)
        put_headers = {"Content-Type": "application/json",
                       "Authorization": f"Bot {self.token}"}
        put_data = {"access_token": access_token}
        async with aiohttp.ClientSession() as session:
            while True:
                temp = await session.put(endpoint, headers=put_headers, json=put_data)
                if temp.status == 201 or temp.status == 204:
                    return True
                try:
                    res_data = await temp.json()
                    if "message" in res_data:
                        if res_data["message"] == "You are being rate limited.":
                            print("[!] Rate Limited. Sleeping {}s".format(
                                res_data["retry_after"]))
                            await asyncio.sleep(res_data["retry_after"])
                        else:
                            return False
                    else:
                        return True
                except Exception as e:
                    print("[!] エラーが発生しました:{}".format(e))
                    return False


# class FileManager:
#     def __init__(self, data, backup):
#         match = r"https://drive.google.com/file/d/([a-zA-Z0-9-_]+)/.*"
#         self.data_id = re.match(match, data).group(1)
#         self.backup_id = re.match(match, backup).group(1)
#         self.upload = False

#     def save(self, data):
#         plain_data = json.dumps(data)
#         open(DATA_PATH, "w").write(plain_data)
#         print("[+] アップロードを実行します、Botを停止しないでください。")
#         file = drive.CreateFile({"id": self.data_id})
#         if not file:
#             print("[!] URLが無効かファイルが存在しません")
#             return
#         else:
#             file.SetContentString(plain_data)
#             file.Upload()
#             self.backup(plain_data)
#         print("[+] 完了しました")

#     def backup(self, plain_data):
#         print("[+] バックアップをします")
#         file = drive.CreateFile({"id": self.backup_id})
#         file.SetContentString(plain_data)
#         file.Upload()

#     def load_file(self):
#         print("[+] ファイルをGoogleドライブから読み込んでいます")
#         f = drive.CreateFile({"id": self.data_id})
#         plain_data = f.GetContentString()
#         print("[+] 読み込みました")
#         if not plain_data:
#             print("[!] Googleドライブのファイルの中身がありませんでした")
#             self.load_backup()
#         try:
#             write_userdata(plain_data)
#         except Exception as e:
#             print("[+] 書き込みが失敗しました")
#             print("[+] 理由: {}".format(e))
#             self.load_backup()

#     def load_backup(self):
#         print("[!] ファイルの中身がない、または破損しているためバックアップを読み込んでいます")
#         f = drive.CreateFile({"id": self.backup_id})
#         plain_data = f.GetContentString()
#         print("[+] バックアップを読み込みました")
#         if not plain_data:
#             raise Exception
#         try:
#             write_userdata(plain_data)
#         except Exception as e:
#             print(e)
#             exit()
