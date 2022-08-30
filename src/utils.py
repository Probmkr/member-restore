from datetime import datetime
from typing import Any, List, TypeAlias, TypedDict
from dotenv import load_dotenv
import asyncio
import psycopg2
import psycopg2.extras
import psycopg2.errors
import aiohttp
from pydrive.drive import GoogleDrive
from pydrive.auth import GoogleAuth
from oauth2client.service_account import ServiceAccountCredentials
import os
import subprocess
# import disnake

GDRIVE_CREDENTIALS_FILE = "secrets/credentials.json"
API_START_POINT_V10 = "https://discord.com/api/v10"
API_START_POINT = "https://discord.com/api"
DATA_DIR = "data"
JSON_DATA_PATH = f"{DATA_DIR}/data.json"
SQL_DATA_PATH = f"{DATA_DIR}/sql.dump"

load_dotenv()
heroku_app_name = os.getenv("APP_NAME")
gdrive_credentials = os.getenv("GDRIVE_CREDENTIALS")
gdrive_sql_data_id = os.getenv("GOOGLE_DRIVE_SQL_DATA_URL")

if not os.path.isfile(GDRIVE_CREDENTIALS_FILE):
    if not gdrive_credentials:
        raise Exception("[!] GDRIVE_CREDENTIALSが設定されていません")
    print("[+] {}がないので環境変数から書き込みます".format(GDRIVE_CREDENTIALS_FILE))
    with open(GDRIVE_CREDENTIALS_FILE, "w") as f:
        f.write(gdrive_credentials)
    print("[+] 書き込みが完了しました")


def write_userdata(userdata: str):
    jf = open(JSON_DATA_PATH, "w")
    jf.write(userdata)
    jf.close()


def read_sql_dump() -> bytes:
    return open(SQL_DATA_PATH, "rb").read()


gauth = GoogleAuth()
scope = ["https://www.googleapis.com/auth/drive"]
gauth.auth_method = "service"
gauth.credentials = ServiceAccountCredentials.from_json_keyfile_name(
    GDRIVE_CREDENTIALS_FILE, scope)
drive = GoogleDrive(gauth)


def load_data_file(file_id):
    f = drive.CreateFile({"id": file_id})
    plain_data = f.GetContentString()
    open(JSON_DATA_PATH, "w").write(plain_data)


class HerokuSqlBackupManager:
    def __init__(self, backup_file_id, database_url):
        self.file_id = backup_file_id
        self.database_url = database_url

    def dump(self):
        pass


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


class TokenData(TypedDict):
    user_id: int
    access_token: str
    expires_in: int
    refresh_token: str
    scope: str
    token_type: str
    last_update: datetime


class GuildRole(TypedDict):
    guild_id: int
    role: int


class DatabaseControl:
    def __init__(self, dsn: str):
        self.dsn = dsn
        if not self.check_table_exists("user_token"):
            print("[!] user_token データベースがないので作ります")
            self.execute(open("sqls/010-user-token.sql", "r").read())
        if not self.check_table_exists("guild_role"):
            print("[!] guild_role データベースがないので作ります")
            self.execute(open("sqls/020-guild-role.sql", "r").read())

    def get_dict_conn(self):
        return psycopg2.connect(self.dsn, cursor_factory=psycopg2.extras.DictCursor)

    def get_user_tokens(self) -> List[TokenData] | bool:
        with self.get_dict_conn() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("select * from user_token")
                    res: List[TokenData] = cur.fetchall()
                    return res
            except Exception as e:
                # print(e)
                return False

    def get_user_token(self, user_id: int) -> TokenData | None | bool:
        with self.get_dict_conn() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "select * from user_token where user_id = %s",
                        (user_id, )
                    )
                    res: TokenData = cur.fetchall()[0]
                    return res
            except IndexError:
                return None
            except Exception as e:
                # print(e)
                return False

    def update_user_token(self, token_data: TokenData) -> bool:
        with self.get_dict_conn() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        update user_token set
                        access_token = %(access_token)s,
                        expires_in = %(expires_in)s,
                        refresh_token = %(refresh_token)s,
                        scope = %(scope)s,
                        token_type = %(token_type)s,
                        last_update = %(last_update)s
                        where user_id = %(user_id)s
                        """,
                        {
                            "access_token": token_data["access_token"],
                            "expires_in": token_data["expires_in"],
                            "refresh_token": token_data["refresh_token"],
                            "scope": token_data["scope"],
                            "token_type": token_data["token_type"],
                            "last_update": token_data["last_update"],
                            "user_id": token_data["user_id"]
                        }
                    )
                    return True
            except Exception as e:
                # print(e)
                conn.rollback()
                return False

    def delete_user_token(self, user_id: int) -> TokenData | bool:
        with self.get_dict_conn() as conn:
            try:
                with conn.cursor() as cur:
                    token_data = self.get_user_token(user_id)
                    cur.execute(
                        "delete from user_token where user_id = %s",
                        (user_id, )
                    )
                    return token_data
            except Exception as e:
                # print(e)
                conn.rollback()
                return False

    def add_user_token(self, token_data: TokenData) -> bool:
        with self.get_dict_conn() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        insert into user_token values (
                            %(user_id)s,
                            %(access_token)s,
                            %(expires_in)s,
                            %(refresh_token)s,
                            %(scope)s,
                            %(token_type)s,
                            %(last_update)s
                        )
                        """,
                        {
                            "user_id": token_data["user_id"],
                            "access_token": token_data["access_token"],
                            "expires_in": token_data["expires_in"],
                            "refresh_token": token_data["refresh_token"],
                            "scope": token_data["scope"],
                            "token_type": token_data["token_type"],
                            "last_update": token_data["last_update"]
                        }
                    )
                    return True
            except Exception as e:
                # print(e)
                conn.rollback()
                return False

    def set_user_token(self, token_data: TokenData) -> bool:
        exists = self.get_user_token(token_data["user_id"])
        if exists:
            return self.update_user_token(token_data)
        elif exists == None:
            return self.add_user_token(token_data)
        else:
            return False

    def get_guild_roles(self) -> List[GuildRole] | bool:
        with self.get_dict_conn() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("select * from guild_role")
                    res: List[GuildRole] = cur.fetchall()
                    return res
            except Exception as e:
                # print(e)
                return False

    def get_guild_role(self, guild_id: int) -> GuildRole | None | bool:
        with self.get_dict_conn() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "select * from guild_role where guild_id = %s",
                        (guild_id, )
                    )
                    res: TokenData = cur.fetchall()[0]
                    return res
            except IndexError:
                return None
            except Exception as e:
                # print(e)
                return False

    def update_guild_role(self, guild_role: GuildRole) -> bool:
        with self.get_dict_conn() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        update guild_role set
                        role = %(role)s
                        where guild_id = %(guild_id)s
                        """,
                        {
                            "role": guild_role["role"],
                            "guild_id": guild_role["guild_id"]
                        }
                    )
                    return True
            except Exception as e:
                print(e)
                conn.rollback()
                return False

    def delete_guild_role(self, guild_id: int) -> GuildRole | bool:
        with self.get_dict_conn() as conn:
            try:
                with conn.cursor() as cur:
                    guild_role = self.get_guild_role(guild_id)
                    cur.execute(
                        "delete from guild_role where guild_id = %s",
                        (guild_id, )
                    )
                    return guild_role
            except Exception as e:
                # print(e)
                conn.rollback()
                return False

    def add_guild_role(self, guild_role: GuildRole) -> bool:
        with self.get_dict_conn() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        insert into guild_role values (
                            %(guild_id)s,
                            %(role)s
                        )
                        """,
                        {
                            "guild_id": guild_role["guild_id"],
                            "role": guild_role["role"]
                        }
                    )
                    return True
            except Exception as e:
                print(e)
                conn.rollback()
                return False

    def set_guild_role(self, guild_role: GuildRole) -> bool:
        exists = self.get_guild_role(guild_role["guild_id"])
        print(exists)
        print(bool(exists))
        if exists:
            return self.update_guild_role(guild_role)
        elif exists == None:
            return self.add_guild_role(guild_role)
        else:
            return False

    def check_table_exists(self, table_name: str) -> bool:
        with self.get_dict_conn() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "select exists (select from pg_tables where schemaname = 'public' and tablename = %s)",
                        (table_name, )
                    )
                    res = cur.fetchone()[0]
                    return res
            except Exception as e:
                # print(e)
                return False

    def execute(self, sql: str) -> Any:
        with self.get_dict_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return cur.description

    def execute_param(self, sql: str, param: dict) -> Any | Exception:
        with self.get_dict_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, param)
                return cur.description


DBC: TypeAlias = DatabaseControl


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
                            print("[!] updated {}".format(
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
