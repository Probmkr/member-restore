from typing import Any, List, Dict, TypedDict, TypeAlias
import asyncio
import aiomysql
from datetime import datetime


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
    def __init__(self, *, host: str = "localhsot", user: Any | None = None, password: str = None, db: Any | None = None, port: int = 3306):
        self.host = host
        self.user = user
        self.password = password
        self.db = db
        self.port = port
        asyncio.run(self.async_init())

    async def async_init(self):
        if not self.check_table_exists("user_token"):
            print("[!] user_token データベースがないので作ります")
            self.execute(open("sqls/010-user-token.sql", "r").read())
        if not self.check_table_exists("guild_role"):
            print("[!] guild_role データベースがないので作ります")
            self.execute(open("sqls/020-guild-role.sql", "r").read())

    async def get_dict_conn(self) -> aiomysql.Connection:
        return aiomysql.connect(host=self.host, user=self.user, password=self.password, db=self.db, port=self.port, cursorclass=aiomysql.DictCursor)

    async def get_user_tokens(self) -> List[TokenData] | bool:
        async with self.get_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute("select * from user_token")
                    res: List[TokenData] = await cur.fetchall()
                    return res
            except Exception as e:
                # print(e)
                return False

    async def get_user_token(self, user_id: int) -> TokenData | None | bool:
        async with self.get_dict_conn() as conn:
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
                # print(e)
                return False

    async def update_user_token(self, token_data: TokenData) -> bool:
        async with self.get_dict_conn() as conn:
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

    async def delete_user_token(self, user_id: int) -> TokenData | bool:
        async with self.get_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    token_data = self.get_user_token(user_id)
                    await cur.execute(
                        "delete from user_token where user_id = %s",
                        (user_id, )
                    )
                    return token_data
            except Exception as e:
                # print(e)
                conn.rollback()
                return False

    async def add_user_token(self, token_data: TokenData) -> bool:
        async with self.get_dict_conn() as conn:
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

    async def set_user_token(self, token_data: TokenData) -> bool:
        exists = self.get_user_token(token_data["user_id"])
        if exists:
            return self.update_user_token(token_data)
        elif exists == None:
            return self.add_user_token(token_data)
        else:
            return False

    async def get_guild_roles(self) -> List[GuildRole] | bool:
        async with self.get_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute("select * from guild_role")
                    res: List[GuildRole] = await cur.fetchall()
                    return res
            except Exception as e:
                # print(e)
                return False

    async def get_guild_role(self, guild_id: int) -> GuildRole | None | bool:
        async with self.get_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "select * from guild_role where guild_id = %s",
                        (guild_id, )
                    )
                    res: TokenData = await cur.fetchone
                    return res
            except IndexError:
                return None
            except Exception as e:
                # print(e)
                return False

    async def update_guild_role(self, guild_role: GuildRole) -> bool:
        async with self.get_dict_conn() as conn:
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
                print(e)
                conn.rollback()
                return False

    async def delete_guild_role(self, guild_id: int) -> GuildRole | bool:
        async with self.get_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    guild_role = self.get_guild_role(guild_id)
                    await cur.execute(
                        "delete from guild_role where guild_id = %s",
                        (guild_id, )
                    )
                    return guild_role
            except Exception as e:
                # print(e)
                conn.rollback()
                return False

    async def add_guild_role(self, guild_role: GuildRole) -> bool:
        async with self.get_dict_conn() as conn:
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
                print(e)
                conn.rollback()
                return False

    async def set_guild_role(self, guild_role: GuildRole) -> bool:
        exists = self.get_guild_role(guild_role["guild_id"])
        print(exists)
        print(bool(exists))
        if exists:
            return self.update_guild_role(guild_role)
        elif exists == None:
            return self.add_guild_role(guild_role)
        else:
            return False

    async def check_table_exists(self, table_name: str) -> bool:
        async with self.get_dict_conn() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "select exists (select from pg_tables where schemaname = 'public' and tablename = %s)",
                        (table_name, )
                    )
                    res = await cur.fetchone()[0]
                    return res
            except Exception as e:
                # print(e)
                return False

    async def execute(self, sql: str) -> Any:
        async with self.get_dict_conn() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql)
                return cur.description

    async def execute_param(self, sql: str, param: dict) -> Any | Exception:
        async with self.get_dict_conn() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, param)
                return cur.description


DBC: TypeAlias = DatabaseControl
