
from typing import TypeAlias, List, TypedDict, Any
import datetime
from datetime import datetime as dt
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
import bcrypt


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
GDRIVE_SQL_DATA_FILE_NAME = os.getenv(
    "GDRIVE_SQL_DATA_FILE_NAME", "sql_backup.dump")
logger = Logger()
LETOA_EXPIRES = 60 * 60 * 24 * 30


def warn_log(log_type: str = "other"):
    logger.warn(traceback.format_exc(), log_type)


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
    last_update: dt
    verified_server_id: int


class GuildRole(TypedDict):
    guild_id: int
    role: int


class BackupDatabaseControl:
    def __init__(self, dsn: str):
        self.dsn = dsn
        if not self.check_table_exists("user_token"):
            logger.warn("user_token データベースがないので作ります", "db_init")
            self.execute(open("sqls/010-user-token.sql", "r").read())
        if not self.check_table_exists("guild_role"):
            logger.warn("guild_role データベースがないので作ります", "db_init")
            self.execute(open("sqls/020-guild-role.sql", "r").read())

    async def get_async_dict_conn(self) -> psycopg.AsyncConnection[psycopg.rows.DictRow]:
        return await psycopg.AsyncConnection.connect(self.dsn, row_factory=dict_row)

    def get_dict_conn(self) -> psycopg.Connection[psycopg.rows.DictRow]:
        return psycopg.connect(self.dsn, row_factory=dict_row)

    async def fetch_user_tokens(self) -> List[TokenData] | bool:
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute("select * from user_token")
                    res: List[TokenData] = await cur.fetchall()
                    return res
            except:
                warn_log("database")
                return False

    async def fetch_user_token(self, user_id: int) -> TokenData | None | bool:
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
            except:
                warn_log("database")
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
            except:
                warn_log("database")
                conn.rollback()
                return False

    async def delete_user_token(self, user_id: int) -> TokenData | bool:
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    token_data = await self.fetch_user_token(user_id)
                    await cur.execute(
                        "delete from user_token where user_id = %s",
                        (user_id, )
                    )
                    return token_data
            except:
                warn_log("database")
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
            except:
                warn_log("database")
                conn.rollback()
                return False

    async def set_user_token(self, token_data: TokenData) -> bool:
        exists = await self.fetch_user_token(token_data["user_id"])
        if exists:
            return await self.update_user_token(token_data)
        elif exists == None:
            return await self.add_user_token(token_data)
        else:
            return False

    async def fetch_guild_roles(self) -> List[GuildRole] | bool:
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute("select * from guild_role")
                    res: List[GuildRole] = await cur.fetchall()
                    return res
            except:
                warn_log("database")
                return False

    async def fetch_guild_role(self, guild_id: int) -> GuildRole | None | bool:
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
            except:
                warn_log("database")
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
            except:
                warn_log("database")
                conn.rollback()
                return False

    async def delete_guild_role(self, guild_id: int) -> GuildRole | bool:
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    guild_role = await self.fetch_guild_role(guild_id)
                    await cur.execute(
                        "delete from guild_role where guild_id = %s",
                        (guild_id, )
                    )
                    return guild_role
            except:
                warn_log("database")
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
            except:
                warn_log("database")
                conn.rollback()
                return False

    async def set_guild_role(self, guild_role: GuildRole) -> bool:
        exists = await self.fetch_guild_role(guild_role["guild_id"])
        if exists:
            return await self.update_guild_role(guild_role)
        elif exists == None:
            return await self.add_guild_role(guild_role)
        else:
            return False

    async def fetch_guild_verified(self, guild_id: int) -> List[TokenData]:
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
            except:
                warn_log("database")
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
                    return res["exists"]
            except:
                warn_log("database")
                return False

    def execute(self, sql: str) -> Any:
        with self.get_dict_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return cur.description

    def execute_param(self, sql: str, param: dict) -> Any:
        with self.get_dict_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, param)
                return cur.description


class LoginResult(TypedDict):
    """LoginResult is a TypedDict for `ADBC.login`

    Attributes
    ----------
    result : bool
        Boolean result
    code : int
        Numeric error code.
        0 : success
        1 : incorrect user_id or password
        2 : no such account
        8 : something went wrong
    """
    result: bool
    code: int


class BackupAccount(TypedDict):
    user_secret_id: int
    user_id: str
    user_discord_id: int
    user_password: bytes
    user_type_id: int
    created_date: dt


class UserType(TypedDict):
    type_id: int
    type_name: str
    type_name_jp: str


class UserLogins(TypedDict):
    user_id: str
    user_discord_id: int
    loged_out: bool
    login_time: dt
    logout_time: dt


class AccountDatabaseControl:
    salt: bytes

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.create_table("letoa_user_types", "030-account-type.sql")
        self.create_table("letoa_user", "031-backup-account.sql")
        self.create_table("letoa_logins", "032-login.sql")
        self.user_types: dict[int, UserType] = {
            1: {"type_id": 1, "type_name": "normal_backup", "type_name_jp": "ノーマル"},
            2: {"type_id": 2, "type_name": "pro", "type_name_jp": "プロ"},
            3: {"type_id": 3, "type_name": "ultimate", "type_name_jp": "アルティメット"},
            4: {"type_id": 4, "type_name": "developer", "type_name_jp": "デベロッパー"},
            5: {"type_id": 5, "type_name": "admin", "type_name_jp": "最高権限者"},
        }
        self.salt = bcrypt.gensalt(10)

    async def get_async_dict_conn(self) -> psycopg.AsyncConnection[psycopg.rows.DictRow]:
        return await psycopg.AsyncConnection.connect(self.dsn, row_factory=dict_row)

    def get_dict_conn(self) -> psycopg.Connection[psycopg.rows.DictRow]:
        return psycopg.connect(self.dsn, row_factory=dict_row)

    async def fetch_account(self, letoa_user_id: str = None, user_secret_id: int = None) -> bool | BackupAccount | None:
        common_sql = "select * from letoa_user where"
        try:
            if letoa_user_id:
                async with await self.get_async_dict_conn() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "{} user_id = %s".format(common_sql),
                            (letoa_user_id,)
                        )
                        return await cur.fetchone()
            elif user_secret_id:
                async with await self.get_async_dict_conn() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "{} user_secret_id = %s".format(common_sql),
                            (letoa_user_id,)
                        )
                        return await cur.fetchone()
            else:
                raise Exception("user_id または user_secret_id が指定されていません")
        except:
            warn_log("acc_db")
            return False

    async def fetch_accounts_from_discord_id(self, discord_user_id: int) -> bool | List[BackupAccount] | None:
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """select * from letoa_user where
                        user_discord_id = %s""",
                        (discord_user_id,)
                    )
                    return await cur.fetchall()
            except:
                warn_log("acc_db")
                return False

    async def register_account(self, letoa_user_id: str, discord_user_id: int, plain_password: str) -> bool:
        if await self.fetch_account(letoa_user_id=letoa_user_id):
            return False
        hashed = bcrypt.hashpw(plain_password.encode("utf-8"), self.salt)
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """insert into letoa_user
                        (user_id, user_discord_id, user_password) values (%s, %s, %s)""",
                        (letoa_user_id, discord_user_id, hashed)
                    )
                    return True
            except:
                warn_log("acc_db")
                return False

    async def delete_account(self, user_id: str):
        pass

    async def check_password(self, user_id: str, plain_password: str) -> bool:
        user = await self.fetch_account(user_id)
        if not user:
            return False
        result = bcrypt.checkpw(
            plain_password.encode("utf-8"), user["user_password"])
        return result

    async def fetch_login(self, letoa_user_id: int) -> bool:
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    expire_line = dt.now() - datetime.timedelta(seconds=LETOA_EXPIRES)
                    await cur.execute(
                        """select * from letoa_logins
                        where user_id = %s
                        and loged_out = FALSE
                        and login_time > %s""",
                        (letoa_user_id, expire_line)
                    )
                    res: UserLogins = await cur.fetchone()
                    if not res:
                        return None
                    else:
                        return res
            except:
                warn_log("acc_db")
                return False

    async def login(self, letoa_user_id: str, discord_user_id: int, plain_password: str) -> LoginResult:
        if not await self.fetch_account(letoa_user_id):
            return {"result": False, "code": 2}
        if not await self.check_password(letoa_user_id, plain_password):
            return {"result": False, "code": 1}
        await self.logout(letoa_user_id)
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """insert into letoa_logins
                        (user_id, user_discord_id)
                        values (%s, %s)""",
                        (letoa_user_id, discord_user_id)
                    )
                    return {"result": True, "code": 0}
            except:
                warn_log("acc_db")
                return {"result": False, "code": 8}

    async def logout(self, letoa_user_id: int) -> bool:
        if not await self.fetch_login(letoa_user_id):
            return False
        async with await self.get_async_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """update letoa_logins
                        set loged_out = TRUE
                        where discord_user_id = %s""",
                        (letoa_user_id,)
                    )
                    await cur.execute
                    return True
            except:
                warn_log("acc_db")
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
                    return res["exists"]
            except:
                warn_log("acc_db")
                return False

    def create_table(self, table_name: str, table_sql_file: str):
        if not self.check_table_exists(table_name):
            logger.warn(f"{table_name} データベースがないので作ります", "acc_db_init")
            self.execute(open(f"sqls/{table_sql_file}").read())

    def execute(self, sql: str) -> Any:
        with self.get_dict_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return cur.description

    def execute_param(self, sql: str, param: dict) -> Any:
        with self.get_dict_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, param)
                return cur.description


BDBC: TypeAlias = BackupDatabaseControl

ADBC: TypeAlias = AccountDatabaseControl


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
