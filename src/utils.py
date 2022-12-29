import asyncio
import aiohttp
import json
import os
import disnake
from datetime import datetime
from typing import List, TypedDict
from dotenv import load_dotenv
from pydrive2.drive import GoogleDrive
from pydrive2.auth import GoogleAuth
from oauth2client.service_account import ServiceAccountCredentials
from db import BDBC, TokenData, DiscordUser, SqlBackupManager
from disnake.ext import commands

GDRIVE_CREDENTIALS_FILE = "secrets/credentials.json"
API_START_POINT_V10 = "https://discord.com/api/v10"
API_START_POINT = "https://discord.com/api"
DATA_DIR = "data"
JSON_DATA_PATH = f"{DATA_DIR}/data.json"
SQL_DATA_PATH = f"{DATA_DIR}/sql.dump"

load_dotenv()
GDRIVE_CREDENTIALS = os.getenv("GDRIVE_CREDENTIALS")
GDRIVE_SQL_DATA_ID = os.getenv("GOOGLE_DRIVE_SQL_DATA_URL")
DATABASE_URL = os.getenv("DATABASE_URL", "host=localhost dbname=verify")

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
sqlmgr = SqlBackupManager(GDRIVE_SQL_DATA_ID, SQL_DATA_PATH, drive)
db = BDBC(DATABASE_URL)
bot = commands.Bot(command_prefix="!", intents=disnake.Intents.all())


def load_data_file(file_id: str):
    f = drive.CreateFile({"id": file_id})
    plain_data = f.GetContentString()
    open(JSON_DATA_PATH, "w").write(plain_data)


class BadUsers(TypedDict):
    bad_users: List[int]
    del_users: List[int]


class UpdateResult(TypedDict):
    code: int
    message: str
    bad_user: int


class Utils:
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

    async def update_tokens(self, *, dont_check_time=False, dont_update=False) -> BadUsers:
        bad_users = []
        del_users = []
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
                    pass
        return {"bad_users": bad_users, "del_users": del_users}

    async def update_token(self, old_token_data: TokenData, *, no_check_time: bool = False, no_update: bool = False) -> UpdateResult:
        old_token_data
        async with aiohttp.ClientSession() as session:
            try:
                if datetime.utcnow().timestamp() - old_token_data["last_update"] < 604800 and not no_check_time or no_update:
                    return {"code": 1, "message": "skipped"}
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
                    if "retry_after" in res_data:
                        print("[!] Rate Limited. Sleeping {}s".format(
                            res_data["retry_after"]+0.5))
                        await asyncio.sleep(res_data["retry_after"]+0.5)
                        continue
                    elif "error" in res_data or "access_token" not in res_data:
                        print("[!] ユーザー:`{}` のトークンは以下の理由で更新できませんでした: `{}`".format(
                            old_token_data["user_id"], res_data["error"]))
                        return {"code": 2, "message": "bad user", "bad_user": old_token_data["user_id"]}
                    else:
                        res_data["last_update"] = datetime.utcnow(
                        ).timestamp()
                        token_data: TokenData = {
                            "user_id": old_token_data["user_id"], **res_data}
                        db.update_user_token(token_data)
                        user = await bot.fetch_user(token_data["user_id"])
                        print("[+] {} のトークンを更新しました".format(user))
                        return {"code": 0, "message": "success"}
            except KeyError:
                print("[!] `{}`のトークンデータは破損しています")
                return {"code": 3, "message": "corrupted token data", "bad_user": old_token_data["user_id"]}

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
                        print("message")
                        print(json_data)
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

    async def join_guild(self, access_token: str, guild_id: int, user_id: int) -> bool:
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
                    if "retry_after" in res_data:
                        print("[!] Rate Limited. Sleeping {}s".format(
                            res_data["retry_after"]+0.5))
                        await asyncio.sleep(res_data["retry_after"]+0.5)
                        continue
                    if "code" in res_data:
                        if res_data["code"] == 50025:
                            db.delete_user_token(user_id)
                            print("ユーザーid`{}`のユーザーはトークンが不正なので削除しました".format(user_id))
                        print(res_data)
                    return False
                except Exception as e:
                    print("[!] エラーが発生しました:{}".format(e))
                    return False


def backup_database():
    print("[+] データベースをバックアップします")
    res = sqlmgr.backup_from_database()
    if res:
        print("[*] データベースのバックアップに成功しました")
    else:
        print("[!] データベースのバックアップに失敗しました")
