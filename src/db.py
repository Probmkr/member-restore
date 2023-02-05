
from typing import TypeAlias, List, TypedDict, Any
from datetime import datetime
from pydrive2.drive import GoogleDrive
from dotenv import load_dotenv
from mylogger import Logger
from psycopg.rows import dict_row
import time
import traceback
import psycopg
import psycopg.rows
import psycopg.errors
import subprocess
import os


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
GDRIVE_SQL_DATA_FILE_NAME = os.getenv("GDRIVE_SQL_DATA_FILE_NAME", "sql_backup.dump")
logger = Logger()

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
    verified_server_id: int


class GuildRole(TypedDict):
    guild_id: int
    role: int


class BackupDatabaseControl:
    def __init__(self, dsn: str):
        self.dsn = dsn
        if not self.check_table_exists("user_token"):
            logger.warn("user_token データベースがないので作ります", "database")
            self.execute(open("sqls/010-user-token.sql", "r").read())
        if not self.check_table_exists("guild_role"):
            logger.warn("guild_role データベースがないので作ります", "database")
            self.execute(open("sqls/020-guild-role.sql", "r").read())

    async def get_async_dict_conn(self) -> psycopg.AsyncConnection[psycopg.rows.DictRow]:
        return await psycopg.AsyncConnection.connect(self.dsn, row_factory=dict_row)

    def get_dict_conn(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    async def get_user_tokens(self) -> List[TokenData] | bool:
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute("select * from user_token")
                    res: List[TokenData] = await cur.fetchall()
                    return res
            except Exception as e:
                logger.warn(traceback.format_exc(), "database")
                return False

    async def get_user_token(self, user_id: int) -> TokenData | None | bool:
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "select * from user_token where user_id = %s",
                        (user_id, )
                    )
                    res: TokenData = await cur.fetchone()
                    return res
            except IndexError:
                return None
            except Exception as e:
                logger.warn(traceback.format_exc(), "database")
                return False

    async def update_user_token(self, token_data: TokenData) -> bool:
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        update user_token set
                        access_token = %(access_token)s,
                        expires_in = %(expires_in)s,
                        refresh_token = %(refresh_token)s,
                        scope = %(scope)s,
                        token_type = %(token_type)s,
                        last_update = %(last_update)s,
                        verified_server_id = %(verified_server_id)s
                        where user_id = %(user_id)s
                        """,
                        {
                            "access_token": token_data["access_token"],
                            "expires_in": token_data["expires_in"],
                            "refresh_token": token_data["refresh_token"],
                            "scope": token_data["scope"],
                            "token_type": token_data["token_type"],
                            "last_update": token_data["last_update"],
                            "user_id": token_data["user_id"],
                            "verified_server_id": token_data["verified_server_id"]
                        }
                    )
                    return True
            except Exception as e:
                logger.warn(traceback.format_exc(), "database")
                conn.rollback()
                return False

    async def delete_user_token(self, user_id: int) -> TokenData | bool:
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    token_data = await self.get_user_token(user_id)
                    await cur.execute(
                        "delete from user_token where user_id = %s",
                        (user_id, )
                    )
                    return token_data
            except Exception as e:
                logger.warn(traceback.format_exc(), "database")
                conn.rollback()
                return False

    async def add_user_token(self, token_data: TokenData) -> bool:
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        insert into user_token values (
                            %(user_id)s,
                            %(access_token)s,
                            %(expires_in)s,
                            %(refresh_token)s,
                            %(scope)s,
                            %(token_type)s,
                            %(last_update)s,
                            %(verified_server_id)s
                        )
                        """,
                        {
                            "user_id": token_data["user_id"],
                            "access_token": token_data["access_token"],
                            "expires_in": token_data["expires_in"],
                            "refresh_token": token_data["refresh_token"],
                            "scope": token_data["scope"],
                            "token_type": token_data["token_type"],
                            "last_update": token_data["last_update"],
                            "verified_server_id": token_data["verified_server_id"]
                        }
                    )
                    return True
            except Exception as e:
                logger.warn(traceback.format_exc(), "database")
                conn.rollback()
                return False

    async def set_user_token(self, token_data: TokenData) -> bool:
        exists = await self.get_user_token(token_data["user_id"])
        if exists:
            return await self.update_user_token(token_data)
        elif exists == None:
            return await self.add_user_token(token_data)
        else:
            return False

    async def get_guild_roles(self) -> List[GuildRole] | bool:
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute("select * from guild_role")
                    res: List[GuildRole] = await cur.fetchall()
                    return res
            except Exception as e:
                logger.warn(traceback.format_exc(), "database")
                return False

    async def get_guild_role(self, guild_id: int) -> GuildRole | None | bool:
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "select * from guild_role where guild_id = %s",
                        (guild_id, )
                    )
                    res: TokenData = await cur.fetchone()
                    return res
            except IndexError:
                return None
            except Exception as e:
                logger.warn(traceback.format_exc(), "database")
                return False

    async def update_guild_role(self, guild_role: GuildRole) -> bool:
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
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
                logger.warn(traceback.format_exc(), "database")
                conn.rollback()
                return False

    async def delete_guild_role(self, guild_id: int) -> GuildRole | bool:
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    guild_role = await self.get_guild_role(guild_id)
                    await cur.execute(
                        "delete from guild_role where guild_id = %s",
                        (guild_id, )
                    )
                    return guild_role
            except Exception as e:
                logger.warn(traceback.format_exc(), "database")
                conn.rollback()
                return False

    async def add_guild_role(self, guild_role: GuildRole) -> bool:
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
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
                logger.warn(traceback.format_exc(), "database")
                conn.rollback()
                return False

    async def set_guild_role(self, guild_role: GuildRole) -> bool:
        exists = await self.get_guild_role(guild_role["guild_id"])
        if exists:
            return await self.update_guild_role(guild_role)
        elif exists == None:
            return await self.add_guild_role(guild_role)
        else:
            return False

    async def get_guild_verified(self, guild_id: int) -> List[TokenData]:
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        select * from user_token
                        where verified_server_id = %s
                        """,
                        (guild_id,)
                    )
                    return await cur.fetchall()
            except Exception as e:
                logger.warn(traceback.format_exc(), "database")
                return False

    def check_table_exists(self, table_name: str) -> bool:
        with self.get_dict_conn() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "select exists (select from pg_tables where schemaname = 'public' and tablename = %s)",
                        (table_name, )
                    )
                    res = cur.fetchone()
                    return res
            except Exception as e:
                logger.warn(traceback.format_exc(), "database")
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


BDBC: TypeAlias = BackupDatabaseControl


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
            time.sleep(1)
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
            logger.error("その id のファイルは存在しません", "sql_manager")
            return False
        self.use_file()
        remote_file.SetContentFile(self.local_backup_file)
        self.user_file_done()
        remote_file["tilte"] = GDRIVE_SQL_DATA_FILE_NAME
        remote_file.Upload()
        return True

    def backup_from_database(self) -> bool:
        self.dump()
        return self.backup_from_local_file()

    def restore_from_remote_file(self):
        logger.info("ドライブからデータベース情報を取得します", "sql_manager")
        remote_file = self.drive.CreateFile({"id": self.remote_backup_file})
        self.use_file()
        remote_file.GetContentFile(self.local_backup_file)
        self.user_file_done()
        self.restore()
        return True
