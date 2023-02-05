import os
import asyncio
import json
import disnake
import utils
import copy
import guild_backup
from disnake.ext import commands
from disnake.errors import NotFound
from dotenv import load_dotenv
from typing import List, TypedDict
from db import BDBC
from utils import API_START_POINT, Utils, backup_database, logger, ADMIN_USERS, GUILD_BACKUP_BASE_DIR
from urllib.parse import quote as url_quote
from snowflake import SnowflakeGenerator

load_dotenv()
dev_users: List[int] = json.loads(os.getenv("ADMIN_USERS", "[]"))
admin_guild_ids: List[int] = json.loads(os.getenv("ADMIN_GUILD_IDS", "[]"))
REDIRECT_URI = os.getenv("REDIRECT_URI")

servers_color = 0xff5555
gen = SnowflakeGenerator(0)
GUILD_VERIFIED_BASE_DIR="data/"


class GuildVerifiedData(TypedDict):
    guild_name: str
    guild_id: int
    verified_num: int


class GuildVerifiedDataList(TypedDict):
    title: str
    guild_num: int
    data: List[GuildVerifiedData]

servers_color = 0xff5555

class Others(commands.Cog):
    bot: utils.CustomBot
    db: BDBC

    def __init__(self, bot: commands.Bot, db: BDBC):
        self.bot = bot
        self.db = utils.db
        self._last_member = None

    @commands.slash_command(name="invite_url", description="BOTの招待リンクを表示")
    async def get_invite_url(self, inter: disnake.AppCmdInter):
        embed = disnake.Embed(title="BOTの招待リンク")
        embed.set_author(name=self.bot.user)
        view = disnake.ui.View()
        link_button = disnake.ui.Button(
            style=disnake.ButtonStyle.primary, label="ボットを招待", url=self.bot.invitation_url)
        view.add_item(link_button)
        await inter.response.defer()
        await inter.delete_original_response()
        await inter.channel.send(embed=embed, view=view)

    @commands.slash_command(description="コマンド一覧を表示")
    async def help(self, inter: disnake.AppCmdInter):
        slash_commands = await self.bot.fetch_global_commands()
        msg_commands = self.bot.commands
        cmd_pref = self.bot.command_prefix
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

        await inter.response.send_message(embed=embed,  ephemeral=True)

    @commands.slash_command(name="nuke", description="チャンネルの再作成を行います")
    @commands.has_permissions(manage_channels=True)
    async def nuke(self, inter: disnake.AppCmdInter):
        view = disnake.ui.View()
        link_button = disnake.ui.Button(
            url=f"https://discord.com/oauth2/authorize?client_id={self.bot.user.id}&permissions=8&scope=bot%20applications.commands", label="このbotを招待")
        embed = disnake.Embed(title="チャンネルの再作成が完了しました", color=0x000000)
        embed.set_footer(text=self.bot.user.name + "#" +
                         self.bot.user.discriminator)
        view.add_item(link_button)
        channel = inter.channel
        pos = channel.position
        await channel.delete()
        new_channel = await channel.clone()
        await new_channel.edit(position=pos)
        await new_channel.send(embed=embed, view=view)

    @commands.slash_command(name="leave", description="Botをサーバーから退出させます")
    async def leave(self, inter: disnake.AppCmdInter, guild_id: str = None):
        if not int(inter.author.id) in dev_users:
            await inter.response.send_message("開発者専用です", ephemeral=True)
        try:
            await inter.response.send_message(f"{guild_id}から退出します", ephemeral=True)
            await self.bot.get_guild(int(guild_id)).leave()
        except AttributeError:
            await inter.response.send_message(f"{guild_id}というidのサーバーは存在しません。", ephemeral=True)

    @commands.slash_command(name="stop", description="Bot緊急停止ボタン☢")
    async def stop(self, inter: disnake.AppCmdInter):
        if not int(inter.author.id) in dev_users:
            await inter.response.send_message("開発者専用", ephemeral=True)
            return
        await inter.response.send_message("Botを強制停止します...", ephemeral=True)
        await inter.bot.close()
        exit(1)

    @commands.slash_command(name="global_ban", description="開発者専用")
    async def global_ban(self, inter: disnake.AppCmdInter, user_id: int, reason=None):
        if not int(inter.author.id) in dev_users:
            await inter.response.send_message("開発者専用", ephemeral=True)
            return

        user = await self.bot.fetch_user(user_id)
        await inter.response.send_message("Global Banを開始します", ephemeral=True)
        count = 0
        result = ""
        guilds = self.bot.guilds

        for guild in guilds:
            if guild.me.guild_permissions.ban_members:
                try:
                    await guild.ban(user, reason=reason)
                    count += 1
                    result += f"成功 [ {guild.name} ][ {guild.id} ]\n"
                except Exception as e:
                    result += f"失敗 [ {guild.name} ][ {guild.id} ]\n"
                    logger.info("ban 失敗 理由:{}".format(e), "cog_glb_ban")

        e = disnake.Embed(title=f"{user} {user.id}", color=0xff0000).set_footer(
            text="Ban済みのサーバーも含まれます")
        e.add_field(name=f"Global Ban Result",
                    value=f"全てのサーバー　`{str(len(guilds))}`\nGban成功数 `{count}`")
        e.add_field(name="詳細", value=f"```\n{result}```")
        await inter.edit_original_message(embed=e, ephemeral=True)

    @commands.slash_command(name="global_unban", description="開発者専用")
    async def global_unban(self, inter: disnake.AppCmdInter, user_id: int, reason=None):
        if not int(inter.author.id) in dev_users:
            await inter.response.send_message("開発者専用", ephemeral=True)
            return
        user = await self.bot.fetch_user(user_id)
        await inter.response.send_message("Global Unban を開始します", ephemeral=True)
        count = 0
        result = ""
        guilds = self.bot.guilds

        for guild in guilds:
            if guild.me.guild_permissions.ban_members:
                try:
                    await guild.unban(user, reason=reason)
                    count += 1
                    result += f"成功 [ {guild.name} ][ {guild.id} ]\n"
                except Exception as e:
                    result += f"失敗 [ {guild.name} ][ {guild.id} ]\n"
                    logger.info("unban 失敗 理由:{}".format(e), "cog_glb_uban")

        e = disnake.Embed(title=f"{user} {user.id}", color=0xff0000).set_footer(
            text="Unban済みのサーバーも含まれます")
        e.add_field(name=f"Global Unban Result",
                    value=f"全てのサーバー　`{str(len(guilds))}`\nGunban成功数 `{count}`")
        e.add_field(name="詳細", value=f"```\n{result}```")
        await inter.edit_original_message(embed=e, ephemeral=True)

    @commands.command(name="addrole")
    async def add_role(self, ctx: disnake.MessageInteraction, member: disnake.Member, role: disnake.Role):
        if not ctx.author.guild_permissions.manage_roles:
            await ctx.send("あなたにこのコマンドを実行する権限はありません")
            return
        try:
            await member.add_roles(role)
            await ctx.send("ロールを付与しました")
        except Exception:
            await ctx.send("ロール付与に失敗しました")

    @commands.slash_command(name="purge", description="チャンネルのメッセージを全て削除します")
    async def purge_channel(self, inter: disnake.AppCmdInter, channel: disnake.TextChannel = None):
        if not (inter.author.guild_permissions.manage_channels or inter.author.id in dev_users):
            await inter.response.send_message("あなたにこのコマンドを実行する権限はありません", ephemeral=True)
            return
        await inter.response.defer()
        await inter.delete_original_message()
        channel = channel if channel else inter.channel
        await channel.purge()
        view = disnake.ui.View()
        link_button = disnake.ui.Button(
            url=f"https://discord.com/oauth2/authorize?client_id={self.bot.user.id}&permissions=8&scope=bot%20applications.commands", label="このbotを招待")
        embed = disnake.Embed(title="チャンネルのメッセージ全削除が完了しました", color=0x000000)
        embed.set_footer(text=self.bot.user.name + "#" +
                         self.bot.user.discriminator)
        view.add_item(link_button)

    @commands.slash_command(name="servers")
    async def server_utils(self, inter: disnake.AppCmdInter):
        pass

    @server_utils.sub_command(name="count", description="ボットが加入しているサーバー一覧を取得します")
    async def server_count(self, inter: disnake.AppCmdInter):
        if inter.author.id not in ADMIN_USERS:
            await inter.response.send_message("権限がありません", ephemeral=True)
            return
        count = len(self.bot.guilds)
        embed = disnake.Embed(
            title=f"このボットは**{count}**個のサーバーに加入しています", color=servers_color)
        await inter.response.send_message(embed=embed)

    @server_utils.sub_command(name="detail", description="ボットが加入しているサーバーの詳細を取得します")
    async def server_detail(self, inter: disnake.AppCmdInter):
        if inter.author.id not in ADMIN_USERS:
            await inter.response.send_message("権限がありません", ephemeral=True)
            return
        guilds = self.bot.guilds
        count = len(guilds)

        async def get_verified(guild: disnake.Guild) -> int:
            return len(await self.db.get_guild_verified(guild.id))

        verified_num_list = await asyncio.gather(*[get_verified(guild) for guild in guilds])
        title = "ボットが加入しているサーバー一覧"
        verified_data: GuildVerifiedDataList = {
            "title": title,
            "guild_num": count,
            "data": []
        }
        for guild, veri in zip(guilds, verified_num_list):
            verified_data["data"].append({
                "guild_name": guild.name,
                "guild_id": guild.id,
                "verified_num": veri
            })
        verified_data["data"].sort(
            key=lambda data: data["verified_num"], reverse=True)

        def format_res(data: GuildVerifiedData):
            text = f"""---------{data['guild_name']}
サーバーid: {data['guild_id']:20}[] 認証ユーザー数: {data['verified_num']}
"""
            return text
        content = f"""{title}(全{count}サーバー)
{
    ''.join(
        map(
            format_res,
            verified_data['data']
        )
    )
}"""
        id = next(gen)
        fname = f"{GUILD_VERIFIED_BASE_DIR}{id}.txt"
        jfname = f"{GUILD_VERIFIED_BASE_DIR}{id}.json"
        with open(fname, "w", encoding="utf-8") as fp:
            with open(jfname, "w", encoding="utf-8") as jfp:
                fp.write(content)
                json.dump(verified_data, jfp)
                guild_id = inter.guild.id

        await inter.response.send_message(files=[
            disnake.File(fname, f"{guild_id}.txt"),
            disnake.File(jfname, f"{guild_id}.json")
        ])

        os.remove(fname)
        os.remove(jfname)

    @commands.slash_command(name="servers")
    async def server_utils(self, inter: disnake.AppCmdInter):
        pass

    @server_utils.sub_command(name="count", description="ボットが加入しているサーバー一覧を取得します")
    async def server_count(self, inter: disnake.AppCmdInter):
        if inter.author.id not in ADMIN_USERS:
            await inter.response.send_message("権限がありません", ephemeral=True)
            return
        count = len(self.bot.guilds)
        embed = disnake.Embed(title=f"このボットは**{count}**個のサーバーに加入しています", color=servers_color)
        await inter.response.send_message(embed=embed)

    @server_utils.sub_command(name="detail", description="ボットが加入しているサーバーの詳細を取得します")
    async def server_detail(self, inter: disnake.AppCmdInter):
        if inter.author.id not in ADMIN_USERS:
            await inter.response.send_message("権限がありません", ephemeral=True)
            return
        guilds = self.bot.guilds
        count = len(guilds)

        async def get_verified(guild: disnake.Guild) -> int:
            return len(self.db.get_guild_verified(guild.id))

        verified_num_list = await asyncio.gather(*[get_verified(guild) for guild in guilds])

        embed = disnake.Embed(title="ボットが加入しているサーバー一覧", color=servers_color, description=f"全部で**{count}**個のサーバーです")

        for guild, veri in zip(guilds, verified_num_list):
            embed.add_field(f"{guild.name}:`{guild.id}`", f"認証している人数:**{veri}**人")

        await inter.response.send_message(embed=embed)


class Backup(commands.Cog):
    bot: commands.Bot
    db: BDBC
    util: Utils

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = utils.db
        self.util = utils.util
        self._last_member = None

    @commands.slash_command(description="親コマンド")
    async def backup(self, inter: disnake.AppCmdInter):
        pass

    @backup.sub_command(name="roleset", description="認証で付与する役職の設定", options=[
        disnake.Option(name="role", description="追加する役職", type=disnake.OptionType.role, required=True)])
    async def slash_roleset(self, inter: disnake.AppCmdInter, role: disnake.Role):
        if inter.author.guild_permissions.administrator:
            res = await self.db.set_guild_role(
                {"guild_id": inter.guild_id, "role": role.id})
            if res:
                await inter.response.send_message("成功しました", ephemeral=True)
            else:
                await inter.response.send_message("失敗しました", ephemeral=True)
        else:
            await inter.response.send_message("管理者専用のコマンドです", ephemeral=True)

    @backup.sub_command(name="check", description="復元できるメンバーの数")
    async def check(self, inter: disnake.AppCmdInter):
        if not int(inter.author.id) in dev_users:
            await inter.response.send_message("You cannot run this command.")
            return
        await inter.response.send_message("確認しています...", ephemeral=True)
        await inter.edit_original_message(content="{}人のメンバーの復元が可能です".format(len(await self.db.get_user_tokens())))

    @backup.sub_command(name="restore", description="メンバーの復元を行います", options=[
        disnake.Option("guild_id", "サーバーのidを入力してください",
                       disnake.OptionType.string, True)
    ])
    async def restore(self, inter: disnake.AppCmdInter, guild_id):
        logger.debug(type(guild_id), "cog_rst")
        try:
            guild_id = int(guild_id)
        except ValueError:
            await inter.response.send_message("正確な数字を入力してください", ephemeral=True)
            return
        guild = None
        try:
            guild = await self.bot.fetch_guild(guild_id)
        except NotFound:
            await inter.response.send_message("正確なサーバーidを入力してください", ephemeral=True)
            return
        if not inter.author.id in dev_users:
            await inter.response.send_message("貴方が置いた認証パネルで\n認証したメンバーが100人になると使用できます\nSupport Server→ https://discord.gg/TkPw7Nupj8", ephemeral=True)
            return
        embed = disnake.Embed(
            title="リストアを実行します",
            description="リストア先サーバーの名前: {}".format(guild.name),
            color=0x000000
        )
        new_embed = copy.deepcopy(embed)
        new_embed.title = "リストア完了"
        await inter.response.send_message(embed=embed, ephemeral=True)
        res = (await utils.manual_restore([guild_id]))[guild_id]
        # res = {"all": 100, "success": 99}
        # res = False

        if res == False:
            new_embed.add_field("結果", "自動リストア中なので実行に失敗しました")
        else:
            new_embed.add_field(
                "結果", f"{res['all']}人中{res['success']}人のメンバーの復元に成功しました")
        await inter.edit_original_message(embed=new_embed)

    @backup.sub_command(name="verify", description="認証パネルを出します", options=[
        disnake.Option(name="role", description="追加する役職",
                       type=disnake.OptionType.role, required=True),
        disnake.Option(name="title", description="認証パネルの一番上の文字",
                       type=disnake.OptionType.string, required=False),
        disnake.Option(name="description", description="認証パネルの詳細文",
                       type=disnake.OptionType.string, required=False),
        disnake.Option(name="color", description="認証パネルの色⚠16進数で選択してね⚠",
                       type=disnake.OptionType.string, required=False),
        disnake.Option(name="picture", description="認証パネルに入れる写真", type=disnake.OptionType.attachment, required=False)])
    async def verifypanel(self, inter: disnake.AppCmdInter, role: disnake.Role, title="ロールを取得！", description="下の認証ボタンを押してロールを取得してください", color="0x000000", picture: disnake.Attachment = None):
        if not (inter.author.guild_permissions.administrator or inter.author.id in dev_users):
            await inter.response.send_message("管理者専用です", ephemeral=True)
            return
        await inter.response.defer()
        await self.db.set_guild_role({"guild_id": inter.guild_id, "role": role.id})
        embed = disnake.Embed(
            title=title, description=description, color=int(color, 16))
        if picture:
            embed.set_image(url=picture)
        view = disnake.ui.View()
        url = "{}/oauth2/authorize?client_id={}&redirect_uri={}&response_type=code&scope=identify%20guilds.join&state={}".format(
            API_START_POINT, self.bot.user.id, url_quote(
                REDIRECT_URI, safe=""
            ), inter.guild_id
        )
        view.add_item(disnake.ui.Button(
            label="✅認証", style=disnake.ButtonStyle.url, url=url))
        await inter.delete_original_message()
        await inter.channel.send(embed=embed, view=view)


class GuildBackup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(description="サーバーバックアップに関する親コマンドです")
    async def guild_backup(self, inter: disnake.AppCmdInter):
        pass

    @guild_backup.sub_command(description="サーバーをバックアップします(メンバー以外)")
    async def backup(self, inter: disnake.AppCmdInter):
        await inter.response.defer()
        if not inter.author.guild_permissions.administrator:
            return await inter.send("権限が不足しています。")
        await guild_backup.backup(inter)

    @guild_backup.sub_command(description="リストアします", options=[
        disnake.Option(
            name="id",
            description="Backup ID",
            type=disnake.OptionType.string, required=True
        )
    ])
    async def restore(self, inter: disnake.ApplicationCommandInteraction, id):
        await inter.response.defer()
        if not inter.author.guild_permissions.administrator:
            return await inter.send("権限が不足しています。")
        await guild_backup.restorehandle(inter, id)

    @guild_backup.sub_command(description="バックアップしたサーバーのjsonファイルを取得します")
    async def get_json(self, inter: disnake.AppCmdInter, id):
        await inter.response.defer(ephemeral=True)
        if inter.author.id not in ADMIN_USERS:
            await inter.edit_original_message("これは開発者専用コマンドです")
            logger.debug(ADMIN_USERS)
            return
        file = f"{GUILD_BACKUP_BASE_DIR}{id}.json"
        if not os.path.isfile(file):
            await inter.edit_original_message("不正なidです")
            return
        with open(file, "r") as fp:
            await inter.edit_original_message(file=disnake.File(fp, description="サーバーバックアップのjsonファイル"))

    @commands.Cog.listener()
    async def on_dropdown(self, inter: disnake.MessageInteraction):
        await inter.response.defer()
        if not inter.author.guild_permissions.administrator:
            return await inter.send("権限が不足しています。")
        await guild_backup.backuphandle(inter)
        await inter.edit_original_response(components=guild_backup.BackupSelect())
