import asyncio
import aiohttp
import json
import os
import disnake
from datetime import datetime
from typing import Dict, List, TypedDict, TypeAlias
from dotenv import load_dotenv
from pydrive2.drive import GoogleDrive
from pydrive2.auth import GoogleAuth
from oauth2client.service_account import ServiceAccountCredentials
from db import BDBC, TokenData, DiscordUser, SqlBackupManager, BackupDatabaseControl
from disnake.ext import commands
from mylogger import Logger

GDRIVE_CREDENTIALS_FILE = "secrets/credentials.json"
API_START_POINT_V10 = "https://discord.com/api/v10"
API_START_POINT = "https://discord.com/api"
DATA_DIR = "data"
JSON_DATA_PATH = f"{DATA_DIR}/data.json"
SQL_DATA_PATH = f"{DATA_DIR}/sql.dump"
GUILD_BACKUP_BASE_DIR = "guild_backup/"
logger = Logger()

load_dotenv()
BOT_ID: int = int(os.getenv("BOT_ID"))
BOT_TOKEN: str = os.getenv("BOT_TOKEN")
BOT_SECRET = os.getenv("BOT_SECRET")
BOT_INVITATION_URL: str = os.getenv("BOT_INVITATION_URL", "")
REDIRECT_URI = os.getenv("REDIRECT_URI")
GDRIVE_CREDENTIALS = os.getenv("GDRIVE_CREDENTIALS")
GDRIVE_SQL_DATA_FILE_ID = os.getenv("GDRIVE_SQL_DATA_FILE_ID")
DATABASE_URL = os.getenv("DATABASE_URL", "host=localhost dbname=verify")
ADMIN_USERS = json.loads(os.getenv("ADMIN_USERS", []))

if not os.path.isfile(GDRIVE_CREDENTIALS_FILE):
    if not GDRIVE_CREDENTIALS:
        raise Exception("GDRIVE_CREDENTIALSが設定されていません")
    logger.info("{}がないので環境変数から書き込みます".format(
        GDRIVE_CREDENTIALS_FILE), "gdrive_cred")
    with open(GDRIVE_CREDENTIALS_FILE, "w") as f:
        f.write(GDRIVE_CREDENTIALS)
    logger.info("書き込みが完了しました", "gdrive_cred")


def write_userdata(userdata: str):
    open(JSON_DATA_PATH, "w").write(userdata)


class CustomBot(commands.Bot):
    def __init__(self, *, invitation_url, **args):
        super().__init__(**args)
        self.invitation_url = invitation_url


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
    bot_secret: str
    redirect_uri: str

    def __init__(self, database_url, token, client_id, client_secret, redirect_uri):
        self.database_url = database_url
        self.token = token
        self.client_id = client_id
        self.bot_secret = client_secret
        self.redirect_uri = redirect_uri

    async def update_token(self, user_id: int, *, no_update: bool = False, no_skip: bool = False) -> UpdateResult:
        old_token_data = await db.get_user_token(user_id)
        async with aiohttp.ClientSession() as session:
            try:
                if (datetime.utcnow().timestamp() - old_token_data["last_update"] < 604800 or no_update) and (not no_skip):
                    logger.debug("skipped", "update_token")
                    return {"code": 1, "message": "skipped"}
                res_data = None
                post_headers = {
                    "Content-Type": "application/x-www-form-urlencoded"}
                post_data = {
                    "client_id": self.client_id,
                    "client_secret": self.bot_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": old_token_data["refresh_token"]}
                endpoint = f"{API_START_POINT_V10}/oauth2/token"
                while True:
                    temp = await session.post(endpoint, data=post_data, headers=post_headers)
                    res_data = await temp.json()
                    # res_data = {"error": "test run"}
                    if "retry_after" in res_data:
                        logger.trace("Rate Limited. Sleeping {}s".format(
                            res_data["retry_after"]+0.5), "update_token")
                        await asyncio.sleep(res_data["retry_after"]+0.5)
                        continue
                    elif "error" in res_data or "access_token" not in res_data:
                        logger.info("ユーザー:`{}` のトークンは以下の理由で更新できませんでした: `{}`".format(
                            user_id, res_data["error"]), "update_token")
                        return {"code": 2, "message": "bad user", "bad_user": user_id}
                    else:
                        res_data["last_update"] = datetime.utcnow(
                        ).timestamp()
                        token_data: TokenData = {
                            "user_id": user_id, **res_data,
                            "verified_server_id": old_token_data["verified_server_id"]
                        }
                        await db.update_user_token(token_data)
                        user = await bot.fetch_user(user_id)
                        logger.debug("{} のトークンを更新しました".format(
                            user), "update_token")
                        # logger.warn(res_data)
                        return {"code": 0, "message": "success"}
            except KeyError:
                logger.info("`{}`のトークンデータは破損しています", "update_token")
                return {"code": 3, "message": "corrupted token data", "bad_user": user_id}

    async def get_token(self, code: str) -> dict:
        post_headers = {"content-type": "application/x-www-form-urlencoded"}
        post_data = {
            "client_id": self.client_id,
            "client_secret": self.bot_secret,
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
                        res_data["retry_after"]+0.5), "get_token")
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
                        res_data["retry_after"]), "get_user")
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
                    logger.debug("すでにロールは付与されています", "add_role")
                    return True
                try:
                    res_data = await temp.json()
                    logger.debug(res_data, "add_role")
                    if "retry_after" in res_data:
                        logger.trace("Rate Limited. Sleeping {}s".format(
                            res_data["retry_after"]), "add_role")
                        await asyncio.sleep(res_data["retry_after"])
                        continue
                    logger.debug("ロールを付与しました", "add_role")
                    return True
                except Exception as e:
                    logger.warn("エラーが発生しました: {}".format(e), "add_role")
                    return False

    async def join_guild(self, user_id: int, guild_id: int) -> bool:
        count = 0
        async with aiohttp.ClientSession() as session:
            while count < 10:
                try:
                    token_data = await db.get_user_token(user_id)
                    endpoint = "{}/guilds/{}/members/{}".format(
                        API_START_POINT_V10,
                        guild_id,
                        user_id)
                    put_headers = {"Content-Type": "application/json",
                                   "Authorization": f"Bot {self.token}"}
                    put_data = {"access_token": token_data["access_token"]}
                    count += 1
                    temp = await session.put(endpoint, headers=put_headers, json=put_data)
                    if temp.status == 201 or temp.status == 204:
                        logger.trace("ユーザー`{}`のリストアに成功しました".format(
                            user_id), "join_guild")
                        return True
                    res_data = await temp.json()
                    logger.debug(res_data, "join_guild")
                    if "retry_after" in res_data:
                        logger.trace("Rate Limited. Sleeping {}s".format(
                            res_data["retry_after"]+0.5), "join_guild")
                        await asyncio.sleep(res_data["retry_after"]+0.5)
                        continue
                    if "code" in res_data:
                        code = res_data["code"]
                        if code == 50025:
                            logger.info("ユーザー`{}`のユーザーはトークンが期限切れでした".format(
                                user_id), "join_guild")
                            update_res = (await self.update_token(user_id, no_skip=True))["code"]
                            if update_res == 0:
                                logger.debug("ユーザー`{}`のユーザーのトークンのアップデートに成功しました".format(
                                    user_id), "join_guild")
                                continue
                            elif update_res == 2 or update_res == 3:
                                logger.warn(
                                    "ユーザー`{}`のトークンは壊れている可能性があるので削除します".format(user_id))
                                await db.delete_user_token(user_id)
                                return False
                            elif update_res == 1:
                                logger.warn(
                                    "join_guild: トークンのアップデートをスキップしました", "join_guild")
                                return False
                        elif code == 30001:
                            logger.trace(
                                "user `{}` causes 30001 error".format(user_id), "join_guild")
                            return False
                        elif code == 40007:
                            logger.trace(
                                "user `{}` is banned from this server".format(user_id), "join_guild")
                            return False
                        logger.trace("join_guild: user: {}, code: {}".format(
                            user_id,
                            res_data
                        ), "join_guild")
                    logger.debug("join_guild: something went wrong with user: {}, response_data: {}".format(
                        user_id, res_data), "join_guild")
                    return False
                except TypeError:
                    logger.debug("トークンが削除されていました")
                    return False
                except Exception as e:
                    logger.warn("エラーが発生しました:{}".format(e), "join_guild")
                    return False
            logger.warn("ユーザー`{}`リストアの挑戦回数が10回を超えたので強制終了します".format(
                user_id), "join_guild")
            return False

    async def fetch_member(self, guild_id: int, user_id: int) -> dict:
        endpoint = "{}/guilds/{}/members/{}".format(
            API_START_POINT_V10, guild_id, user_id)
        get_headers = {"authorization": f"Bot {self.token}"}
        async with aiohttp.ClientSession() as session:
            while True:
                temp = await session.get(endpoint, headers=get_headers)
                logger.trace(temp.status, "fetch_member")
                if temp.status == 200:
                    return True
                elif temp.status == 404:
                    return False
                try:
                    res_data = await temp.json()
                    if "retry_after" in res_data:
                        logger.debug("")
                        await asyncio.sleep(res_data["retry_after"])
                        logger.trace("Rate Limited. Sleeping {}s".format(
                            res_data["retry_after"]+0.5), "update_token")
                        continue
                    return
                except Exception as e:
                    logger.debug("エラー: {}", format(e), "fetch_member")
                    return


CSF: TypeAlias = commands.CommandSyncFlags
gauth = GoogleAuth()
scope = ["https://www.googleapis.com/auth/drive"]
gauth.auth_method = "service"
gauth.credentials = ServiceAccountCredentials.from_json_keyfile_name(
    GDRIVE_CREDENTIALS_FILE, scope)
drive = GoogleDrive(gauth)
sqlmgr = SqlBackupManager(GDRIVE_SQL_DATA_FILE_ID, SQL_DATA_PATH, drive)
db: BackupDatabaseControl = BDBC(DATABASE_URL)
util = Utils(DATABASE_URL, BOT_TOKEN, BOT_ID, BOT_SECRET, REDIRECT_URI)
bot = CustomBot(invitation_url=BOT_INVITATION_URL,
                command_prefix="!", intents=disnake.Intents.all())


def backup_database():
    logger.debug("データベースをバックアップします", "backup_db")
    res = sqlmgr.backup_from_database()
    if res:
        logger.debug("[*] データベースのバックアップに成功しました", "backup_db")
    else:
        logger.info("データベースのバックアップに失敗しました", "backup_db")


class RestoreResult(TypedDict):
    success: int
    all: int


restoring = False


async def common_restore(dest_server_ids: List[int]) -> Dict[int, RestoreResult]:
    result_sum: Dict[int, RestoreResult] = dict()
    for guild_id in dest_server_ids:
        users: List[TokenData] = await db.get_user_tokens()
        # users: List[TokenData] = [db.get_user_token(764476174021689385)]
        res = []

        async def check_user(user: TokenData):
            if not await util.fetch_member(guild_id, user["user_id"]):
                res.append(await util.join_guild(user["user_id"], guild_id))
                logger.info("ユーザー `{}` はサーバー `{}` に入っていません".format(
                    user["user_id"], guild_id), "check_user")
        check_tasks = [check_user(user) for user in users]
        while check_tasks:
            await asyncio.gather(*check_tasks[:5])
            del check_tasks[:5]
            await asyncio.sleep(1)
        result_sum[guild_id]: RestoreResult = {
            "success": res.count(True), "all": len(res)}
        this_sum = result_sum[guild_id]
        logger.info(
            f"{guild_id}: {this_sum['success']}/{this_sum['all']}", "common_rst")
    return result_sum


async def auto_restore(dest_server_ids: List[int]) -> Dict[int, RestoreResult]:
    global restoring
    if restoring:
        logger.debug("自動バックアップがキャンセルされました", "auto_rst")
        return False
    restoring = True
    result_sum = await common_restore(dest_server_ids)
    restoring = False
    return result_sum


async def manual_restore(dest_server_ids: List[int]) -> Dict[int, RestoreResult]:
    result_sum = await common_restore(dest_server_ids)
    return result_sum
