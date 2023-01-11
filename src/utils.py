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
from db import BDBC, TokenData, DiscordUser, SqlBackupManager, BackupDatabaseControl
from disnake.ext import commands
from mylogger import Logger, LCT

GDRIVE_CREDENTIALS_FILE = "secrets/credentials.json"
API_START_POINT_V10 = "https://discord.com/api/v10"
API_START_POINT = "https://discord.com/api"
DATA_DIR = "data"
JSON_DATA_PATH = f"{DATA_DIR}/data.json"
SQL_DATA_PATH = f"{DATA_DIR}/sql.dump"
logger = Logger()

load_dotenv()
GDRIVE_CREDENTIALS = os.getenv("GDRIVE_CREDENTIALS")
GDRIVE_SQL_DATA_ID = os.getenv("GOOGLE_DRIVE_SQL_DATA_URL")
DATABASE_URL = os.getenv("DATABASE_URL", "host=localhost dbname=verify")

if not os.path.isfile(GDRIVE_CREDENTIALS_FILE):
    if not GDRIVE_CREDENTIALS:
        raise Exception("GDRIVE_CREDENTIALSが設定されていません")
    logger.info("{}がないので環境変数から書き込みます".format(
        GDRIVE_CREDENTIALS_FILE), LCT.utils)
    with open(GDRIVE_CREDENTIALS_FILE, "w") as f:
        f.write(GDRIVE_CREDENTIALS)
    logger.info("書き込みが完了しました", LCT.utils)


def write_userdata(userdata: str):
    open(JSON_DATA_PATH, "w").write(userdata)


gauth = GoogleAuth()
scope = ["https://www.googleapis.com/auth/drive"]
gauth.auth_method = "service"
gauth.credentials = ServiceAccountCredentials.from_json_keyfile_name(
    GDRIVE_CREDENTIALS_FILE, scope)
drive = GoogleDrive(gauth)
sqlmgr = SqlBackupManager(GDRIVE_SQL_DATA_ID, SQL_DATA_PATH, drive)
db: BackupDatabaseControl = BDBC(DATABASE_URL)
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

    async def update_token(self, user_id: int, *, no_update: bool = False) -> UpdateResult:
        old_token_data = db.get_user_token(user_id)
        async with aiohttp.ClientSession() as session:
            try:
                if datetime.utcnow().timestamp() - old_token_data["last_update"] < 604800 or no_update:
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
                    res_data = await temp.json()
                    # res_data = {"error": "test run"}
                    if "retry_after" in res_data:
                        logger.trace("Rate Limited. Sleeping {}s".format(
                            res_data["retry_after"]+0.5), LCT.utils)
                        await asyncio.sleep(res_data["retry_after"]+0.5)
                        continue
                    elif "error" in res_data or "access_token" not in res_data:
                        logger.info("ユーザー:`{}` のトークンは以下の理由で更新できませんでした: `{}`".format(
                            user_id, res_data["error"]), LCT.utils)
                        return {"code": 2, "message": "bad user", "bad_user": user_id}
                    else:
                        res_data["last_update"] = datetime.utcnow(
                        ).timestamp()
                        token_data: TokenData = {
                            "user_id": user_id, **res_data}
                        db.update_user_token(token_data)
                        user = await bot.fetch_user(user_id)
                        logger.debug("{} のトークンを更新しました".format(user), LCT.utils)
                        return {"code": 0, "message": "success"}
            except KeyError:
                logger.info("`{}`のトークンデータは破損しています", LCT.utils)
                return {"code": 3, "message": "corrupted token data", "bad_user": user_id}

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
                if "retry_after" in res_data:
                    logger.trace("Rate Limited. Sleeping {}s".format(
                        res_data["retry_after"]+0.5), LCT.utils)
                    await asyncio.sleep(res_data["retry_after"]+0.5)
                else:
                    return res_data

    async def get_user(self, access_token: str):
        endpoint = f"{API_START_POINT_V10}/users/@me"
        get_headers = {"Authorization": f"Bearer {access_token}"}
        async with aiohttp.ClientSession() as session:
            while True:
                temp = await session.get(endpoint, headers=get_headers)
                res_data = await temp.json()
                if "retry_after" in res_data:
                    logger.trace("Rate Limited. Sleeping {}s".format(
                        res_data["retry_after"]), LCT.utils)
                    await asyncio.sleep(res_data["retry_after"])
                else:
                    return res_data

    async def add_role(self, guild_id: int, user_id: int, role_id: int) -> bool:
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
                    logger.debug("すでにロールは付与されています", LCT.utils)
                    return True
                try:
                    res_data = await temp.json()
                    logger.debug(res_data, LCT.utils)
                    if "retry_after" in res_data:
                        logger.trace("Rate Limited. Sleeping {}s".format(
                            res_data["retry_after"]), LCT.utils)
                        await asyncio.sleep(res_data["retry_after"])
                        continue
                    logger.debug("ロールを付与しました", LCT.utils)
                    return True
                except Exception as e:
                    logger.warn("エラーが発生しました: {}".format(e), LCT.utils)
                    return False

    async def join_guild(self, user_id: int, guild_id: int) -> bool:
        count=0
        token_data = db.get_user_token(user_id)
        endpoint = "{}/guilds/{}/members/{}".format(
            API_START_POINT_V10,
            guild_id,
            user_id)
        put_headers = {"Content-Type": "application/json",
                       "Authorization": f"Bot {self.token}"}
        put_data = {"access_token": token_data["access_token"]}
        async with aiohttp.ClientSession() as session:
            while count < 10:
                count += 1
                temp = await session.put(endpoint, headers=put_headers, json=put_data)
                if temp.status == 201 or temp.status == 204:
                    logger.trace("ユーザー`{}`のリストアに成功しました".format(user_id))
                    return True
                try:
                    res_data = await temp.json()
                    # logger.debug(res_data)
                    if "retry_after" in res_data:
                        logger.trace("Rate Limited. Sleeping {}s".format(
                            res_data["retry_after"]+0.5), LCT.utils)
                        await asyncio.sleep(res_data["retry_after"]+0.5)
                        continue
                    if "code" in res_data:
                        code = res_data["code"]
                        if code == 50025:
                            logger.info("ユーザー`{}`のユーザーはトークンが期限切れでした".format(
                                user_id), LCT.utils)
                            update_res = (await self.update_token(user_id))["code"]
                            if update_res == 0:
                                logger.debug("ユーザー`{}`のユーザーのトークンのアップデートに成功しました".format(
                                    user_id), LCT.utils)
                                continue
                            elif update_res == 2 or update_res == 3:
                                logger.warn(
                                    "ユーザー`{}`のトークンは壊れている可能性があるので削除します".format(user_id))
                                db.delete_user_token(user_id)
                                return False
                            else:
                                logger.warn(
                                    "トークンのアップデートをスキップしました (in Utils.join_guild)", LCT.utils)
                                return False
                        elif code == 30001:
                            logger.trace("user `{}` causes 30001 error".format(user_id))
                        logger.trace("server_join: user: {}, code: {}".format(
                            user_id,
                            res_data
                        ), LCT.utils)
                    return False
                except Exception as e:
                    logger.warn("エラーが発生しました:{}".format(e), LCT.utils)
                    return False


def backup_database():
    logger.debug("データベースをバックアップします", LCT.utils)
    res = sqlmgr.backup_from_database()
    if res:
        logger.debug("[*] データベースのバックアップに成功しました", LCT.utils)
    else:
        logger.info("データベースのバックアップに失敗しました", LCT.utils)


class RestoreResult(TypedDict):
    success: int
    all: int


async def auto_restore(dest_server_ids: List[int], util: Utils) -> RestoreResult:
    for guild in dest_server_ids:
        users: List[TokenData] = db.get_user_tokens()
        join_tasks = []
        for user in users:
            join_tasks.append(util.join_guild(
                user["user_id"], guild))
        # res = await asyncio.gather(*join_tasks)
        res = []
        while join_tasks:
            res += await asyncio.gather(*join_tasks[:10])
            del join_tasks[:10]
            await asyncio.sleep(10)
        result_sum: RestoreResult = {
            "success": res.count(True), "all": len(res)}
        logger.info(
            f"{guild}: {result_sum['success']}/{result_sum['all']}", LCT.server)
        return result_sum
