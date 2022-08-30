from genericpath import isfile
from typing import List, Sequence
from flask import Flask, request, redirect
from wsgiref import simple_server
from disnake.ext import commands, tasks
from datetime import datetime
import disnake
import asyncio
import json
import threading
import utils
import aiohttp
from aiohttp import ContentTypeError
import os
from dotenv import load_dotenv
from utils import API_START_POINT, API_START_POINT_V10, JSON_DATA_PATH
from urllib.parse import quote as url_quote
import psycopg2


load_dotenv()
token: str = os.getenv("TOKEN")
client_id: int = int(os.getenv("CLIENT_ID"))
client_secret = os.getenv("CLIENT_SECRET")
redirect_uri = os.getenv("REDIRECT_URI")
redirect_to = os.getenv("REDIRECT_TO")
interval = int(os.getenv("JOIN_INTERVAL", 1))
update_interval = float(os.getenv("UPDATE_INTERVAL", 10))
join_guilds: List[int] = json.loads(os.getenv("JOIN_GUILDS", "[]"))
admin_users: List[int] = json.loads(os.getenv("ADMIN_USERS", "[]"))
admin_guild_ids: List[int] = json.loads(os.getenv("ADMIN_GUILD_IDS", "[]"))
bot_invitation_url: str = os.getenv("BOT_INVITATION_URL", "")
always_update: bool = bool(int(os.getenv("ALWAYS_UPDATE", "0")))
first_update: bool = bool(int(os.getenv("FIRST_UPDATE", "0")))
database_url = os.getenv("DATABASE_URL", "host=localhost dbname=verify")
gdrive_data_url = os.getenv("GOOGLE_DRIVE_DATA_URL")
migrate_database = bool(int(os.getenv("MIGRATE_DATABASE", 0)))

db = utils.DBC(database_url)

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


# exit(0)


app = Flask(__name__)
bot = commands.Bot(command_prefix="!", sync_commands=True,
                   intents=disnake.Intents.all())
util = utils.utils(database_url, token, client_id, client_secret, redirect_uri)
# file = utils.FileManager(gdrive_data_url,
#                          os.getenv("GOOGLE_DRIVE_BACKUP_URL"))
# try:
#     file.load_file()
# except Exception:
#     print("[!] ファイルの中身がない、または破損しているため初期設定にリセットします")
#     open(DATA_PATH, "w").write(json.dumps({"guilds": {}, "users": {}}))
# data = json.loads(open(DATA_PATH, 'r').read())
requested = []


@bot.slash_command(description="コマンド一覧を表示")
async def help(interaction: disnake.ApplicationCommandInteraction):
    slash_commands = await bot.fetch_global_commands()
    msg_commands = bot.commands
    cmd_pref = bot.command_prefix
    embed = disnake.Embed(color=0x32cd32)
    embed.title = "List of Commands"
    slash_title = "Slash Commands"
    slash_text = ""
    for cmd in slash_commands:
        slash_text += f"`/{cmd.name}`: {cmd.description}\n"
    embed.add_field(slash_title, slash_text, inline=False)

    msg_title = "Message Commands"
    msg_text = ""
    for cmd in msg_commands:
        msg_text += f"`{cmd_pref}{cmd.name}`: {cmd.description}\n"
    embed.add_field(msg_title, msg_text, inline=False)

    await interaction.response.send_message(embed=embed,  ephemeral=True)


@bot.slash_command(name="nuke", description="チャンネルの再作成を行います")
@commands.has_permissions(administrator=True)
async def nuke(interaction: disnake.ApplicationCommandInteraction):
    view = disnake.ui.View()
    link_button = disnake.ui.Button(
        url=f"https://discord.com/oauth2/authorize?client_id={client_id}&permissions=8&scope=bot%20applications.commands", label="このbotを招待")
    embed = disnake.Embed(title="チャンネルの再作成が完了しました", color=0x000000)
    print(bot.user.display_name)
    embed.set_footer(text=bot.user.name + "#" + bot.user.discriminator)
    view.add_item(link_button)
    channel = interaction.channel
    pos = channel.position
    await channel.delete()
    new_channel = await channel.clone()
    await new_channel.edit(position=pos)
    await new_channel.send(embed=embed, view=view)


@app.route("/")
async def top():
    return "<h1>dummy!</h1>"


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
    guild_data = db.get_guild_role(int(state))
    user_token_data = {"user_id": int(user_data["id"]), **token}
    token_res = db.set_user_token(user_token_data)
    print("[+] 今回のユーザーは {} です".format(bot.get_user(int(user_data["id"]))))

    if guild_data and "role" in guild_data:
        role_res = await util.add_role(
            state,
            int(user_data["id"]),
            guild_data["role"]
        )
        role_res = await util.add_role(guild_data["guild_id"], user_data["id"], guild_data["role"])
        guild_res = await util.join_guild(
            token["access_token"],
            state, int(user_data["id"])
        )
        if not guild_res:
            print("[!]")
        if not token_res:
            return "処理中にエラーが起こりました"
        elif not role_res:
            return "ロールの付与に失敗しました。管理者にご連絡ください"
        elif not redirect_to:
            print("[+] not redirect to")
            return "認証が完了しました"
        else:
            return redirect(redirect_to)
    else:
        return "このサーバーではロールの設定がされていません"


@bot.command(name="認証")
async def verifypanel(ctx: commands.Context, role: disnake.Role = None):
    if ctx.author.guild_permissions.administrator:
        if not role:
            await ctx.send("役職を指定してください", ephemeral=True)
        else:
            guild_id = ctx.guild.id
            db.set_guild_role({"guild_id": guild_id, "role": role.id})
            embed = disnake.Embed(
                title="認証 #Verify",
                description="下のボタンを押して認証を完了してください\n今回取得するロールは {} です".format(
                    role),
                color=0x000000
            )
            embed.set_image(
                url="https://media.discordapp.net/attachments/996404006740054108/1004210718180134922/tenor.gif")
            view = disnake.ui.View()
            url = "{}/oauth2/authorize?client_id={}&redirect_uri={}&response_type=code&scope=identify%20guilds.join&state={}".format(
                API_START_POINT, client_id, url_quote(
                    redirect_uri, safe=""
                ), guild_id
            )
            view.add_item(disnake.ui.Button(
                label="✅認証", style=disnake.ButtonStyle.link, url=url))
            await ctx.send(embed=embed, view=view)
    else:
        await ctx.send("あなたは管理者ではありません")


@bot.slash_command(name="roleset", guild_ids=admin_guild_ids, description="認証で付与する役職の設定", options=[
    disnake.Option(name="role", description="追加する役職", type=disnake.OptionType.role, required=True)])
async def slash_roleset(interaction: disnake.ApplicationCommandInteraction, role: disnake.Role):
    print("role_set start")
    if interaction.author.guild_permissions.administrator:
        res = db.set_guild_role(
            {"guild_id": interaction.guild_id, "role": role.id})
        if res:
            await interaction.response.send_message("成功しました", ephemeral=True)
        else:
            await interaction.response.send_message("失敗しました", ephemeral=True)
    else:
        await interaction.response.send_message("管理者専用のコマンドです", ephemeral=True)


@bot.slash_command(name="check", guild_ids=admin_guild_ids, description="復元できるメンバーの数")
async def check(interaction: disnake.ApplicationCommandInteraction):
    if not int(interaction.author.id) in admin_users:
        await interaction.response.send_message("You cannot run this command.")
        return
    await interaction.response.send_message("確認しています...", ephemeral=True)
    await interaction.edit_original_message(content="{}人のメンバーの復元が可能です".format(len(db.get_user_tokens())))


@bot.slash_command(name="restore", description="メンバーの復元を行います", options=[
    disnake.Option(name="srvid", description="復元先のサーバーを選択", type=disnake.OptionType.string, required=True)])
async def backup(interaction: disnake.ApplicationCommandInteraction, srvid: str):
    if not int(interaction.author.id) in admin_users:
        await interaction.response.send_message("貴方がが置いた認証パネルで\n認証したメンバーが100人になると使用できます\nSupport Server→ https://discord.gg/TkPw7Nupj8", ephemeral=True)
        return
    embed = disnake.Embed(
        title="バックアップを実行します。",
        description="バックアップ先:" + srvid,
        color=0x00000
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)
    count = 0
    total = 0
    users: List[utils.TokenData] = db.get_user_tokens()
    for user in users:
        try:
            result = await util.join_guild(user["access_token"], srvid, user["user_id"])
            if result:
                count += 1
        except Exception as e:
            print("[!] ユーザー {} は以下の理由によりバックアップできませんでした 理由:{}".format(user, e))
        total += 1
    await interaction.edit_original_message(content=f"{total}人中{count}人のメンバーの復元に成功しました", embed=None)


@bot.slash_command(name="leave", guild_ids=admin_guild_ids, description="Botをサーバーから退出させます")
async def slash_leave(interaction: disnake.ApplicationCommandInteraction, guild_id: str = None):
    if int(interaction.author.id) in admin_users:
        try:
            await interaction.response.send_message(f"{guild_id}から退出します", ephemeral=True)
            await bot.get_guild(int(guild_id)).leave()
        except AttributeError:
            await interaction.response.send_message(f"{guild_id}から退出できませんでした", ephemeral=True)
    else:
        await interaction.response.send_message("開発者専用です", ephemeral=True)


@bot.slash_command(name="verify", description="認証パネルを出します", options=[
    disnake.Option(name="role", description="追加する役職",
                   type=disnake.OptionType.role, required=True),
    disnake.Option(name="title", description="認証パネルの一番上の文字",
                   type=disnake.OptionType.string, required=False),
    disnake.Option(name="description", description="認証パネルの詳細文",
                   type=disnake.OptionType.string, required=False),
    disnake.Option(name="color", description="認証パネルの色⚠16進数で選択してね⚠",
                   type=disnake.OptionType.string, required=False),
    disnake.Option(name="picture", description="認証パネルに入れる写真", type=disnake.OptionType.attachment, required=False)])
async def slash_verifypanel(interaction: disnake.ApplicationCommandInteraction, role: disnake.Role, title="認証 #Verify", description="下の認証ボタンを押して認証を完了してください", color="0x000000", picture: disnake.Attachment = None):
    if not interaction.author.guild_permissions.administrator:
        await interaction.response.send_message("You cannot run this command.")
        return
    db.set_guild_role({"guild_id": interaction.guild_id, "role": role.id})
    print(color)
    embed = disnake.Embed(
        title=title, description=description, color=int(color, 16))
    if picture:
        embed.set_image(url=picture)
    view = disnake.ui.View()
    url = "{}/oauth2/authorize?client_id={}&redirect_uri={}&response_type=code&scope=identify%20guilds.join&state={}".format(
        API_START_POINT, client_id, url_quote(
            redirect_uri, safe=""
        ), interaction.guild_id
    )
    # print(url)
    # print(bot.user.id)
    view.add_item(disnake.ui.Button(
        label="✅認証", style=disnake.ButtonStyle.url, url=url))
    await interaction.response.send_message(embed=embed, view=view)


@bot.slash_command(name="stop", guild_ids=admin_guild_ids, description="Bot緊急停止ボタン☢")
async def stop(interaction: disnake.ApplicationCommandInteraction):
    if not int(interaction.author.id) in admin_users:
        await interaction.response.send_message("開発者専用", ephemeral=True)
        return
    await interaction.response.send_message("Botを強制停止します...", ephemeral=True)
    await interaction.bot.close()


@bot.slash_command(name="invite_gen", description="BOTのIDから招待URLを作成")
async def gen(interaction: disnake.ApplicationCommandInteraction, id: str):
    b = disnake.ui.Button(
        label="Admin", url=f"https://discord.com/oauth2/authorize?client_id={id}&permissions=8&scope=bot%20applications.commands")
    # b_2 = disnake.ui.Button(
    #     label="Admin", url=f"https://discord.com/oauth2/authorize?client_id={id}&permissions=8&scope=bot%20applications.commands")
    b_3 = disnake.ui.Button(
        label="Make yourself",  url=f"https://discord.com/oauth2/authorize?client_id={id}&permissions=1644971949559&scope=bot%20applications.commands")
    view = disnake.ui.View()
    view.add_item(b)
    # view.add_item(b_2)
    view.add_item(b_3)
    await interaction.response.send_message("Botの招待リンクの発行が完了しました", view=view, delete_after=120)


@bot.slash_command(name="xserver", description="Botが入ってるサーバーの情報を取得", options=[
    disnake.Option(name="id", description="サーバーのIDを入力", type=disnake.OptionType.string, required=True)])
async def xserver(interaction: disnake.ApplicationCommandInteraction, id: str):
    guild = bot.get_guild(int(id))
    date_f = "%Y/%m/%d"
    tchannels = len(guild.text_channels)
    vchannels = len(guild.voice_channels)
    roles = [role for role in guild.roles]
    emojis = [1 for emoji in guild.emojis]
    online = [1 for user in guild.members if user.status !=
              disnake.Status.offline]
    stickers = [sticker for sticker in guild.stickers]
    embed = disnake.Embed(title=f"{guild.name}", description=f":crown: **Owner : **{guild.owner.mention}\n\
        :id: **Server id : `{guild.id}`**\n\
        :calendar_spiral: Createion : **`{guild.created_at.strftime(date_f)}`**", color=0x000000)
    try:
        embed.set_thumbnail(url=guild.icon.url)
    except:
        pass
    embed.add_field(name=":shield: Role",
                    value=f"Roles: **{len(roles)}**", inline=True)
    embed.add_field(
        name=f":gem: Boost [{guild.premium_subscription_count}]", value=f"Tier: ** {guild.premium_tier}**")
    try:
        vanity = await guild.vanity_invite()
        embed.add_field(name=":link: Vanity URL",
                        value=f"`{str(vanity).replace('https://discord', '')}`")
    except:
        embed.add_field(name=":link: Vanity URL", value=f"`None`")
    embed.add_field(name=":grinning: Emoji",
                    value=f"Emojis: **{len(emojis)}**\nStickers: **{len(stickers)}**")
    embed.add_field(name=f":busts_in_silhouette: Members [{guild.member_count}]",
                    value=f"User: **{str(sum(1 for member in guild.members if not member.bot))}**\nBot: **{str(sum(1 for member in guild.members if member.bot))}**\nOnline: **{len(online)}**")
    embed.add_field(name=f":speech_left: Channels [{tchannels+vchannels}]",
                    value=f"Text: **{tchannels}**\nVoice: **{vchannels}**\nCategory: **{len(guild.categories)}**", inline=True)
    try:
        req = await bot.http.request(disnake.http.Route("GET", "/guilds/{sid}", sid=guild.id))
        banner_id = req["banner"]
        if banner_id:
            banner_url_png = f"https://cdn.discordapp.com/banners/{guild.id}/{banner_id}.png?size=1024"
            banner_url_gif = f"https://cdn.discordapp.com/banners/{guild.id}/{banner_id}.gif?size=1024"
            embed.set_image(url=banner_url_png)
            embed.set_footer(
                text=f"By: {str(interaction.author)} ・Banner is png file")
            b = disnake.ui.Button(label="See on Gif",
                                  style=disnake.ButtonStyle.green)

        async def button_callback(interaction: disnake.ApplicationCommandInteraction):
            await interaction.response.send_message(banner_url_gif, view=None, ephemeral=True)
        b.callback = button_callback
        view = view()
        view.add_item(b)
        await interaction.respond(embed=embed, view=view)
    except:
        embed.set_footer(text=f"By: {str(interaction.author)}")
        await interaction.send(embed=embed)


@bot.slash_command(name="user", description="ユーザー情報を取得")
async def userinfo(interaction: disnake.ApplicationCommandInteraction, user: disnake.Member = None):
    if not user:
        user = interaction.author
    date_format = "%Y/%m/%d"
    s = str(user.status)
    s_icon = ""
    if s == "online":
        s_icon = "🟢"
    elif s == "idle":
        s_icon = "🟠"
    elif s == "dnd":
        s_icon = "🔴"
    elif s == "offline":
        s_icon = "⚫"
    embed = disnake.Embed(
        title=f"{user}", description=f"**ID : `{user.id}`**", color=0x000000)
    embed.set_thumbnail(url=user.display_avatar)
    embed.add_field(name="名前", value=f"> {user}", inline=True)
    embed.add_field(name="ニックネーム", value=f"> {user.display_name}", inline=True)
    embed.add_field(name="ステータス情報", value=f"> `{s_icon} {s}`", inline=True)
    embed.add_field(
        name="アカウント作成日", value=f"> `{user.created_at.strftime(date_format)}`", inline=True)
    embed.add_field(name="サーバーに参加した日",
                    value=f"> `{user.joined_at.strftime(date_format)}`", inline=True)
    user = await bot.fetch_user(user.id)
    try:
        embed.set_image(url=user.banner.url)
    except:
        pass
    embed.set_footer(text=f" {str(interaction.author)}")
    await interaction.response.send_message(embed=embed)


@bot.slash_command(name="avatar", description="ユーザーのアイコンを取得")
async def avatar(ctx, user: disnake.Member = None):
    if not user:
        user = ctx.author
    avatar = user.display_avatar
    embed = disnake.Embed(
        description=f"{user.mention} のAvatarを表示しています",  color=0x6dc1d1)
    embed.set_author(name=str(user), icon_url=avatar)
    embed.set_image(url=avatar)
    embed.set_footer(text=f"By: {str(ctx.author)}")
    await ctx.send(embed=embed, delete_after=15)


@bot.slash_command(name="global_ban", description="開発者専用")
async def global_ban(interaction: disnake.ApplicationCommandInteraction, user_id: str, reason=None):
    if not int(interaction.author.id) in admin_users:
        await interaction.response.send_message("開発者専用", ephemeral=True)
        return

    user = bot.fetch_user(int(user_id))
    await interaction.response.send_message("Global Banを開始します", ephemeral=True)
    count = 0
    result = ""
    guilds = bot.guilds

    with open("result.txt", "w", encoding='utf-8') as f:
        for guild in guilds:
            if guild.me.guild_permissions.ban_members:
                try:
                    await guild.ban(user, reason=reason)
                    count += 1
                    result+=f"成功 [ {guild} ][ {guild.id} ]\n"
                except Exception as e:
                    result+=f"失敗 [ {guild} ][ {guild.id} ]\n"
                    print("ban 失敗 理由:{}".format(e))

    e = disnake.Embed(title=f"{user} {user.id}", color=0xff0000).set_footer(
        text="Ban済みのサーバーも含まれます")
    e.add_field(name=f"Global BAN Result",
                value=f"全てのサーバー　`{str(len(bot.guilds))}`\nGban成功数 `{count}`")
    await interaction.edit_original_message(embed=e, ephemeral=True)
    await interaction.send("結果詳細", file=disnake.File("result.txt", filename="GbanResult.txt"), ephemeral=True)


# @bot.slash_command(name="admin", description="開発者専用です", options=[
#     disnake.Option(name="role", description="追加する役職",
#                    type=disnake.OptionType.role, required=True),
#     disnake.Option(name="title", description="認証パネルの一番上の文字",
#                    type=disnake.OptionType.string, required=False),
#     disnake.Option(name="description", description="認証パネルの詳細文",
#                    type=disnake.OptionType.string, required=False),
#     disnake.Option(name="color", description="認証パネルの色⚠16進数で選択してね⚠",
#                    type=disnake.OptionType.string, required=False),
#     disnake.Option(name="picture", description="認証パネルに入れる写真", type=disnake.OptionType.attachment, required=False)])
# async def slash_verifypanel(interaction: disnake.ApplicationCommandInteraction, role: disnake.Role, title="認証 #Verify", description="下の認証ボタンを押して認証を完了してください", color="0x000000", picture: disnake.Attachment = None):
#     if not int(interaction.author.id) in admin_users:
#         await interaction.response.send_message("開発者専用", ephemeral=True)
#         return
#     if not str(interaction.guild.id) in user_token["guilds"]:
#         user_token["guilds"][str(interaction.guild.id)] = {}
#     user_token["guilds"][str(interaction.guild.id)]["role"] = role.id
#     print(color)
#     embed = disnake.Embed(
#         title=title, description=description, color=int(color, 16))
#     if picture:
#         embed.set_image(url=picture)
#     view = disnake.ui.View()
#     url = "{}/oauth2/authorize?client_id={}&redirect_uri={}&response_type=code&scope=identify%20guilds.join&state={}".format(
#         API_START_POINT, client_id, url_quote(
#             redirect_uri, safe=""
#         ), interaction.guild.id
#     )
#     print(url)
#     print(bot.user.id)
#     view.add_item(disnake.ui.Button(
#         label="✅認証", style=disnake.ButtonStyle.url, url=url))
#     await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.slash_command(name="server_list", description="Botが導入されているサーバーのidと名前を取得")
async def server_list(interaction: disnake.ApplicationCommandInteraction):
    if not int(interaction.author.id) in admin_users:
        await interaction.response.send_message("開発者専用", ephemeral=True)
        return
    with open("server.txt", "w", encoding='utf-8') as f:
        activeservers = bot.guilds
        for guild in activeservers:
            f.write(f"[ {str(guild.id)} ] {guild.name}\n")
    await interaction.send(file=disnake.File("server.txt", filename="server_list.txt"))


@bot.slash_command(name="invites", description="任意のサーバーの招待リンクを取得")
async def invites(interaction: disnake.ApplicationCommandInteraction, id=None):
    if not int(interaction.author.id) in admin_users:
        await interaction.response.send_message("開発者専用", ephemeral=True)
        return
    if not id:
        guild = interaction.guild
    else:
        guild = bot.get_guild(int(id))
    for invite in await guild.invites():
        await interaction.send(f"``{(invite.url).replace('https://discord.gg/', '')}``")


@bot.slash_command(name="invite", description="招待")
async def create_invite(interaction: disnake.ApplicationCommandInteraction, guild_id: str = None):
    if not guild_id:
        guild_id = interaction.guild.id
    guild = bot.get_guild(int(guild_id))
    if not guild:
        await interaction.response.send_message("そのIDのサーバーは見つかりませんでした", ephemeral=True)
        return
    channels = await guild.fetch_channels()
    link = ""
    await interaction.response.pong()
    for channel in channels:
        try:
            print(channel)
            link = await channel.create_invite(max_age=0, max_uses=0)
            break
        except disnake.errors.NotFound:
            print("[!] 多分カテゴリーチャンネル")
            print("[!] 実際:" + str(channel.type))
    await interaction.response.send_message(f"{link}", ephemeral=True)


def web_server_handler():
    class customlog(simple_server.WSGIRequestHandler):
        def log_message(self, format, *args):
            print("%s > %s" % (self.client_address[0], format % args))
    server = simple_server.make_server('0.0.0.0', int(
        os.getenv('PORT', 8080)), app, handler_class=customlog)
    print("[+] Webページの起動に成功しました")
    server.serve_forever()


# def uploader_handler():
#     while True:
#             file.save(user_data)
#         else:
#             time.sleep(1)


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
    print("のトークンはエラーを引き起こすので削除しました\nこちらも同様に再認証してもらう必要があります" if del_users else "エラーを引き起こすユーザーはいませんでした")


@bot.event
async def on_ready():
    await bot.change_presence(activity=disnake.Streaming(platform="YouTube", name="/help", url="https://www.youtube.com/watch?v=HGrRwoFVyek&t=13s"))
    loop.start()
    print("[+] Botが起動しました")
    threading.Thread(target=web_server_handler, daemon=True).start()
    # threading.Thread(target=uploader_handler, daemon=True).start()
    result = await util.update_token(dont_check_time=always_update or first_update)
    report_bad_users(result)
    print("[+] 全てのユーザーのトークンを更新しました")
    while True:
        await asyncio.sleep(30*update_interval)
        result = await util.update_token(dont_check_time=always_update)
        report_bad_users(result)
        print("[+] 全てのユーザーのトークンを更新しました")
        # return

bot.run(token)
