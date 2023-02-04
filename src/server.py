from typing import List
from flask import Flask, request, redirect
from wsgiref import simple_server
from disnake.ext import tasks
from datetime import datetime
from utils import DATABASE_URL, JSON_DATA_PATH, Utils
from db import BDBC, TokenData
from dotenv import load_dotenv
from cogs import *
import disnake
import json
import threading
import utils
import os


load_dotenv()
token: str = os.getenv("TOKEN")
client_id: int = int(os.getenv("CLIENT_ID"))
client_secret = os.getenv("CLIENT_SECRET")
redirect_uri = os.getenv("REDIRECT_URI")
redirect_to = os.getenv("REDIRECT_TO")
join_guilds: List[int] = json.loads(os.getenv("JOIN_GUILDS", "[]"))
interval = int(os.getenv("JOIN_INTERVAL", 1))
update_interval = float(os.getenv("UPDATE_INTERVAL", 10))
backup_interval = float(os.getenv("BACKUP_INTERVAL", 5))
always_update: bool = bool(int(os.getenv("ALWAYS_UPDATE", 0)))
first_update: bool = bool(int(os.getenv("FIRST_UPDATE", 0)))
gdrive_data_url = os.getenv("GOOGLE_DRIVE_DATA_URL")
migrate_database = bool(int(os.getenv("MIGRATE_DATABASE", 0)))
first_restore: bool = bool(int(os.getenv("FIRST_RESTORE", 0)))

db: BDBC = utils.db
logger = utils.logger

if first_restore:
    logger.info("最初のデータベースのリストアをします", "first_rst")
    utils.sqlmgr.restore_from_remote_file()


if migrate_database:
    utils.load_data_file(gdrive_data_url)


app = Flask(__name__)
bot = utils.bot
util = Utils(DATABASE_URL, token, client_id, client_secret, redirect_uri)
bot.add_cog(Others(bot))
bot.add_cog(Backup(bot, db, util))
bot.add_cog(GuildBackup(bot))


def web_server_handler():
    port = int(os.getenv('PORT', 8080))

    class customlog(simple_server.WSGIRequestHandler):
        def log_message(self, format, *args):
            logger.debug("{} > {}".format(
                self.client_address[0], format % args), "web")
    server = simple_server.make_server(
        '0.0.0.0', port, app, handler_class=customlog)
    logger.info(f"{port}番ポートでWebページの起動に成功しました", "web")
    server.serve_forever()
    # app.run(port=port)


@app.route("/after")
async def after():
    logger.info("-------/after-------", "after")
    code = str(request.args.get('code'))
    state = str(request.args.get('state'))
    if not code or not state:
        logger.info("不正なリクエストURL", "after")
        return "認証をやり直してください"
    token = await util.get_token(code)
    if "access_token" not in token:
        logger.error("トークンの取得に失敗しました\nトークン: {}".format(token), "after")
        return "認証をやり直してください"

    user_data: utils.DiscordUser = await util.get_user(token["access_token"])
    token["last_update"] = datetime.utcnow().timestamp()
    try:
        guild_id = int(state)
    except ValueError:
        logger.info("不正なstateパラメータ")
        return "不正なパラメータです"
    guild_data = db.get_guild_role(guild_id)
    logger.debug(guild_data, "after")
    user_id = int(user_data["id"])
    user_token_data: TokenData = {"user_id": user_id, **token}
    token_res = db.set_user_token(user_token_data)
    logger.info("今回のユーザーは {} です".format(bot.get_user(user_id)), "after")
    utils.backup_database()

    if guild_data and "role" in guild_data:
        role_res = await util.add_role(guild_data["guild_id"], user_data["id"], guild_data["role"])
        guild_res = await util.join_guild(user_id, state)
        if not guild_res:
            logger.error("ユーザーをサーバーに追加できませんでした", "after")
        if not role_res:
            logger.error("ロールを追加できませんでした", "after")
        if not token_res:
            return "処理中にエラーが起こりました"
        elif not redirect_to:
            logger.debug("not redirect to", "after")
            return "認証が完了しました"
        else:
            return redirect(redirect_to)
    elif not redirect_to:
        logger.debug("not redirect to", "after")
        return "認証が完了しました"
    else:
        return redirect(redirect_to)


@tasks.loop(minutes=interval)
async def loop():
    logger.info("自動バックアップを実行します", "rst_loop")
    await utils.auto_restore(join_guilds, util)


def report_bad_users(result: utils.BadUsers):
    bad_users = result["bad_users"]
    none_users = []
    for i in bad_users:
        user = bot.get_user(i)
        logger.warn("トークン破損:`{}`".format(bot.get_user(i)), "bad_users")
        if not user:
            none_users.append(i)
    logger.warn(
        "のトークンが破損しているので再認証してもらう必要があります" if bad_users else "トークンの破損しているユーザーはいませんでした", "bad_users")
    del_users = result["del_users"]
    for i in del_users:
        user = bot.get_user(i)
        logger.warn("トークンなし:`{}`".format(bot.get_user(i)), "bad_users")
        db.delete_user_token(i)
    utils.backup_database()
    logger.warn(
        "のトークンはエラーを引き起こすので削除しました\nこちらも同様に再認証してもらう必要があります" if del_users else "エラーを引き起こすユーザーはいませんでした", "server")


@bot.event
async def on_ready():
    await bot.change_presence(status="/help")
    loop.start()
    # update_loop.start()
    logger.info("Botが起動しました", "on_ready")
    threading.Thread(target=web_server_handler, daemon=True).start()

disnake.ApplicationCommandInteractionData
@bot.event
async def on_interaction(inter: disnake.Interaction):
    if inter.type == disnake.InteractionType.application_command:
        inter: disnake.AppCmdInter = inter
        logger.debug("user:`{}` id:`{}` used command `/{}`".format(inter.author, inter.author.id, inter.data.name), "on_inter")

bot.run(token)

# 1045993969118617681