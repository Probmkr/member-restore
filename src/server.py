from typing import List
from flask import Flask, request, redirect
from wsgiref import simple_server
from disnake.ext import tasks
from datetime import datetime
from utils import DATABASE_URL, JSON_DATA_PATH, Utils, LCT
from db import BDBC, TokenData
from dotenv import load_dotenv
from cogs import Others, Backup
import disnake
import asyncio
import json
import threading
import utils
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
gdrive_data_url = os.getenv("GOOGLE_DRIVE_DATA_URL")
migrate_database = bool(int(os.getenv("MIGRATE_DATABASE", 0)))
first_restore: bool = bool(int(os.getenv("FIRST_RESTORE", 0)))

db: BDBC = utils.db
logger = utils.logger

if first_restore:
    logger.info("最初のデータベースのリストアをします", LCT.server)
    utils.sqlmgr.restore_from_remote_file()


if migrate_database:
    utils.load_data_file(gdrive_data_url)


app = Flask(__name__)
bot = utils.bot
util = Utils(DATABASE_URL, token, client_id, client_secret, redirect_uri)
bot.add_cog(Others(bot))
bot.add_cog(Backup(bot, db, util))


def web_server_handler():
    port = int(os.getenv('PORT', 8080))

    class customlog(simple_server.WSGIRequestHandler):
        def log_message(self, format, *args):
            print("{} > {}".format(self.client_address[0], format % args))
    server = simple_server.make_server(
        '0.0.0.0', port, app, handler_class=customlog)
    logger.info(f"{port}番ポートでWebページの起動に成功しました", LCT.server)
    server.serve_forever()
    # app.run(port=port)


@app.route("/after")
async def after():
    logger.debug("-------/after-------")
    code = str(request.args.get('code'))
    state = str(request.args.get('state'))
    if not code or not state:
        logger.debug("リクエストURLが不正です", LCT.after)
        return "認証をやり直してください"
    token = await util.get_token(code)
    if "access_token" not in token:
        logger.error("トークンの取得に失敗しました\nトークン: {}".format(token), LCT.after)
        return "認証をやり直してください"

    user_data: utils.DiscordUser = await util.get_user(token["access_token"])
    token["last_update"] = datetime.utcnow().timestamp()
    guild_id = int(state)
    guild_data = db.get_guild_role(guild_id)
    logger.debug(guild_data, LCT.after)
    guild: disnake.Guild = await bot.fetch_guild(guild_id)
    user_id = int(user_data["id"])
    member: disnake.Member = await guild.fetch_member(user_id)
    user_token_data: TokenData = {"user_id": user_id, **token}
    token_res = db.set_user_token(user_token_data)
    logger.info("今回のユーザーは {} です".format(bot.get_user(user_id)), LCT.after)
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
            await member.add_roles(role)
        except Exception as e:
            logger.warn(e, LCT.after)
        guild_res = await util.join_guild(
            token["access_token"],
            state, user_id
        )
        if not guild_res:
            logger.error("ユーザーをサーバーに追加できませんでした", LCT.after)
        if not token_res:
            return "処理中にエラーが起こりました"
        elif not redirect_to:
            logger.debug("not redirect to", LCT.after)
            return "認証が完了しました"
        else:
            return redirect(redirect_to)
    elif not redirect_to:
        logger.debug("not redirect to", LCT.after)
        return "認証が完了しました"
    else:
        return redirect(redirect_to)


@tasks.loop(minutes=interval)
async def loop():
    logger.info("自動バックアップを実行します", LCT.server)
    for guild in join_guilds:
        users: List[utils.TokenData] = db.get_user_tokens()
        join_tasks = []
        for user in users:
            join_tasks.append(util.join_guild(
                user["access_token"], guild, user["user_id"]))
        res = await asyncio.gather(*join_tasks)
        logger.info(f"{guild}: {res.count(True)}/{len(res)}", LCT.server)


@tasks.loop(minutes=update_interval)
async def update_loop():
    logger.info("全てのユーザーのトークンを更新します", LCT.server)
    tokens_data = db.get_user_tokens()
    update_tasks = [util.update_token(
        token_data, no_check_time=always_update) for token_data in tokens_data]
    # result = await util.update_tokens(dont_check_time=always_update)
    results = await asyncio.gather(*update_tasks)
    codes = [result["code"] for result in results]
    bad_users = [result["bad_user"]
                 for result in results if "bad_user" in result]
    logger.info("全て: {}, 成功: {}, 失敗: {}, スキップ: {}".format(
        len(codes), codes.count(0), codes.count(2)+codes.count(3), codes.count(1)), LCT.server)
    # report_bad_users({"bad_users"})


def report_bad_users(result: utils.BadUsers):
    bad_users = result["bad_users"]
    none_users = []
    for i in bad_users:
        user = bot.get_user(i)
        logger.warn("トークン破損:`{}`".format(bot.get_user(i)), LCT.server)
        if not user:
            none_users.append(i)
    logger.warn("のトークンが破損しているので再認証してもらう必要があります" if bad_users else "トークンの破損しているユーザーはいませんでした", LCT.server)
    del_users = result["del_users"]
    for i in del_users:
        user = bot.get_user(i)
        logger.warn("トークンなし:`{}`".format(bot.get_user(i)), LCT.server)
        db.delete_user_token(i)
    utils.backup_database()
    logger.warn("のトークンはエラーを引き起こすので削除しました\nこちらも同様に再認証してもらう必要があります" if del_users else "エラーを引き起こすユーザーはいませんでした", LCT.server)


@bot.event
async def on_ready():
    await bot.change_presence(status="/help")
    loop.start()
    update_loop.start()
    logger.info("Botが起動しました", LCT.server)
    threading.Thread(target=web_server_handler, daemon=True).start()

bot.run(token)
