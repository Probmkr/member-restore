from typing import List
from flask import Flask, request, redirect
from wsgiref import simple_server
from disnake.ext import commands, tasks
from datetime import datetime
from utils import JSON_DATA_PATH
from db import DBC, TokenData
from dotenv import load_dotenv
from cogs import Others, Backup
import disnake
import asyncio
import json
import threading
import utils
import aiohttp
import os
import psycopg2


load_dotenv()
token: str = os.getenv("TOKEN")
client_id: int = int(os.getenv("CLIENT_ID"))
client_secret = os.getenv("CLIENT_SECRET")
redirect_uri = os.getenv("REDIRECT_URI")
redirect_to = os.getenv("REDIRECT_TO")
interval = int(os.getenv("JOIN_INTERVAL", 1))
update_interval = float(os.getenv("UPDATE_INTERVAL", 10))
backup_interval = float(os.getenv("BACKUP_INTERVAL", 5))
join_guilds: List[int] = json.loads(os.getenv("JOIN_GUILDS", "[]"))
bot_invitation_url: str = os.getenv("BOT_INVITATION_URL", "")
always_update: bool = bool(int(os.getenv("ALWAYS_UPDATE", 0)))
first_update: bool = bool(int(os.getenv("FIRST_UPDATE", 0)))
database_url = os.getenv("DATABASE_URL", "host=localhost dbname=verify")
gdrive_data_url = os.getenv("GOOGLE_DRIVE_DATA_URL")
migrate_database = bool(int(os.getenv("MIGRATE_DATABASE", 0)))
first_restore: bool = bool(int(os.getenv("FIRST_RESTORE", 0)))


db = DBC(database_url)

# sqlmgr = SqlBackupManager(GDRIVE_SQL_DATA_ID, SQL_DATA_PATH, utils.drive)


if first_restore:
    print("[+] 最初のデータベースのリストアをします")
    utils.sqlmgr.restore_from_remote_file()


if migrate_database:
    utils.load_data_file(gdrive_data_url)


if os.path.isfile(JSON_DATA_PATH):
    print("[!] data.json をデータベースに移行します")
    user_token = json.load(open(JSON_DATA_PATH, "r"))
    users = user_token["users"]
    guilds = user_token["guilds"]
    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            for user_id in users:
                user = users[user_id]
                # insert_user_sql = "insert into user_token values (%s, %s, %s, %s, %s, %s, %s)"
                # insert_user_param = (user_id, user["access_token"], user["expires_in"],
                #                     user["refresh_token"], user["scope"], user["token_type"], user["last_update"])
                # cur.execute(insert_user_sql, insert_user_param)
                res = db.add_user_token(
                    {"user_id": int(user_id), **users[user_id]})
                if not res:
                    print("[!] ユーザー:{} を追加することができませんでした".format(user_id))
            cur.execute("select * from user_token")
            for i in cur.fetchall():
                print(i)

            for guild_id in guilds:
                guild = guilds[guild_id]
                # insert_guild_sql = "insert into guild_role values (%s, %s)"
                # insert_guild_param = (guild_id, guild["role"])
                # cur.execute(insert_guild_sql, insert_guild_param)
                res = db.add_guild_role(
                    {"guild_id": int(guild_id), **guilds[guild_id]})
                if not res:
                    print("[!] サーバー:{} のロール情報を追加することができませんでした".format(guild_id))
            cur.execute("select * from guild_role")
            for i in cur.fetchall():
                print(i)
    os.remove(JSON_DATA_PATH)
    utils.backup_database()


# exit(0)


app = Flask(__name__)
bot = commands.Bot(command_prefix="!", intents=disnake.Intents.all())
bot.add_cog(Others(bot))
util = utils.Utils(database_url, token, client_id, client_secret, redirect_uri)
bot.add_cog(Backup(bot, db, util))
# file = utils.FileManager(gdrive_data_url,
#                          os.getenv("GOOGLE_DRIVE_BACKUP_URL"))
# try:
#     file.load_file()
# except Exception:
#     print("[!] ファイルの中身がない、または破損しているため初期設定にリセットします")
#     open(DATA_PATH, "w").write(json.dumps({"guilds": {}, "users": {}}))
# data = json.loads(open(DATA_PATH, 'r').read())
requested = []


def web_server_handler():
    port = int(os.getenv('PORT', 8080))

    class customlog(simple_server.WSGIRequestHandler):
        def log_message(self, format, *args):
            print("%s > %s" % (self.client_address[0], format % args))
    server = simple_server.make_server(
        '0.0.0.0', port, app, handler_class=customlog)
    print(f"[+] {port}番ポートでWebページの起動に成功しました")
    server.serve_forever()
    # app.run(port=port)


@app.route("/after")
async def after():
    print("[+] -------/after-------")
    # debug = request.args.get("debug")
    # print("debug:", debug)
    # if debug:
    #     return str(eval(debug))
    # print("[+] get data")
    code = str(request.args.get('code'))
    if code not in requested:
        requested.append(code)
    else:
        return "You are already requested"
    state = str(request.args.get('state'))
    if not code or not state:
        print("[!] リクエストURLが不正です")
        return "認証をやり直してください"
    token = await util.get_token(code)
    if "access_token" not in token:
        print("[!] トークンの取得に失敗しました")
        print("[!] トークン: %s" % token)
        return "認証をやり直してください"

    user_data: utils.DiscordUser = await util.get_user(token["access_token"])
    token["last_update"] = datetime.utcnow().timestamp()
    guild_id = int(state)
    guild_data = db.get_guild_role(guild_id)
    print(guild_data)
    guild: disnake.Guild = bot.get_guild(guild_id)
    user_id = int(user_data["id"])
    member: disnake.Member = guild.get_member(user_id)
    user_token_data: TokenData = {"user_id": user_id, **token}
    token_res = db.set_user_token(user_token_data)
    print("[+] 今回のユーザーは {} です".format(bot.get_user(user_id)))
    utils.backup_database()

    if guild_data and "role" in guild_data:
        # role_res = await util.add_role(
        #     state,
        #     user_id,
        #     guild_data["role"]
        # )
        # role_res = await util.add_role(guild_data["guild_id"], user_data["id"], guild_data["role"])
        role = guild.get_role(guild_data["role"])
        try:
            await member.add_roles()
        except Exception as e:
            print(e)
            return "ロールの付与に失敗しました。管理者にご連絡ください"
        guild_res = await util.join_guild(
            token["access_token"],
            state, user_id
        )
        if not guild_res:
            print("[!] ユーザーをサーバーに追加できませんでした")
        if not token_res:
            return "処理中にエラーが起こりました"
        elif not redirect_to:
            print("[+] not redirect to")
            return "認証が完了しました"
        else:
            return redirect(redirect_to)
    else:
        print("[+] not with role")
        return "認証が完了しました"


@tasks.loop(minutes=interval)
async def loop():
    print("[+] 自動バックアップを実行します")
    async with aiohttp.ClientSession() as session:
        for guild in join_guilds:
            users: List[utils.TokenData] = db.get_user_tokens()
            for user in users:
                await util.join_guild(user["access_token"], guild, user)


def report_bad_users(result: utils.BadUsers):
    bad_users = result["bad_users"]
    none_users = []
    for i in bad_users:
        user = bot.get_user(i)
        print("トークン破損:`{}`".format(bot.get_user(i)))
        if not user:
            none_users.append(i)
    print("のトークンが破損しているので再認証してもらう必要があります" if bad_users else "トークンの破損しているユーザーはいませんでした")
    del_users = result["del_users"]
    for i in del_users:
        user = bot.get_user(i)
        print("トークンなし:`{}`".format(bot.get_user(i)))
        db.delete_user_token(i)
    utils.backup_database()
    print("のトークンはエラーを引き起こすので削除しました\nこちらも同様に再認証してもらう必要があります" if del_users else "エラーを引き起こすユーザーはいませんでした")


@bot.event
async def on_ready():
    await bot.change_presence(status="/help")
    loop.start()
    print("[+] Botが起動しました")
    threading.Thread(target=web_server_handler, daemon=True).start()
    result = await util.update_token(dont_check_time=always_update or first_update)
    report_bad_users(result)
    print("[+] 全てのユーザーのトークンを更新しました")
    while True:
        await asyncio.sleep(update_interval)
        result = await util.update_token(dont_check_time=always_update)
        report_bad_users(result)
        print("[+] 全てのユーザーのトークンを更新しました")
        # return

bot.run(token)
