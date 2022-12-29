import os
import json
import disnake
from disnake.ext import commands
from dotenv import load_dotenv
from typing import List
from db import BDBC, TokenData
from utils import API_START_POINT, Utils, backup_database, logger
from urllib.parse import quote as url_quote
from var import LCT

load_dotenv()
dev_users: List[int] = json.loads(os.getenv("ADMIN_USERS", "[]"))
admin_guild_ids: List[int] = json.loads(os.getenv("ADMIN_GUILD_IDS", "[]"))
redirect_uri = os.getenv("REDIRECT_URI")


class Others(commands.Cog):
    bot: commands.Bot

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_member = None

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
    @commands.has_permissions(administrator=True)
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

    @commands.slash_command(name="leave", guild_ids=admin_guild_ids, description="Botをサーバーから退出させます")
    async def leave(self, inter: disnake.AppCmdInter, guild_id: str = None):
        if not int(inter.author.id) in dev_users:
            await inter.response.send_message("開発者専用です", ephemeral=True)
        try:
            await inter.response.send_message(f"{guild_id}から退出します", ephemeral=True)
            await self.bot.get_guild(int(guild_id)).leave()
        except AttributeError:
            await inter.response.send_message(f"{guild_id}というidのサーバーは存在しません。", ephemeral=True)

    @commands.slash_command(name="stop", guild_ids=admin_guild_ids, description="Bot緊急停止ボタン☢")
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
                    logger.info("ban 失敗 理由:{}".format(e), LCT.bot_others)

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
                    logger.info("unban 失敗 理由:{}".format(e), LCT.bot_others)

        e = disnake.Embed(title=f"{user} {user.id}", color=0xff0000).set_footer(
            text="Unban済みのサーバーも含まれます")
        e.add_field(name=f"Global Unban Result",
                    value=f"全てのサーバー　`{str(len(guilds))}`\nGunban成功数 `{count}`")
        e.add_field(name="詳細", value=f"```\n{result}```")
        await inter.edit_original_message(embed=e, ephemeral=True)

    @commands.slash_command(name="invite_gen", description="BOTのIDから招待URLを作成")
    async def gen(self, inter: disnake.AppCmdInter, id: str):
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
        await inter.response.send_message("Botの招待リンクの発行が完了しました", view=view, delete_after=120)

    @commands.command(name="addrole")
    async def add_role(self, ctx: disnake.Message, member: disnake.Member, role: disnake.Role):
        if not ctx.author.guild_permissions.manage_roles:
            await ctx.send("あなたにはこのコマンドを実行する権限はありません")
            return
        try:
            await member.add_roles(role)
            await ctx.send("ロールを付与しました")
        except Exception:
            await ctx.send("ロール付与に失敗しました")


class Backup(commands.Cog):
    bot: commands.Bot
    db: BDBC
    util: Utils

    def __init__(self, bot: commands.Bot, db: BDBC, util: Utils):
        self.bot = bot
        self.db = db
        util = util
        self._last_member = None

    @commands.slash_command(description="親コマンド")
    async def backup(self, inter: disnake.AppCmdInter):
        pass

    @backup.sub_command(name="roleset", guild_ids=admin_guild_ids, description="認証で付与する役職の設定", options=[
        disnake.Option(name="role", description="追加する役職", type=disnake.OptionType.role, required=True)])
    async def slash_roleset(self, inter: disnake.AppCmdInter, role: disnake.Role):
        if inter.author.guild_permissions.administrator:
            res = self.db.set_guild_role(
                {"guild_id": inter.guild_id, "role": role.id})
            if res:
                await inter.response.send_message("成功しました", ephemeral=True)
                backup_database()
            else:
                await inter.response.send_message("失敗しました", ephemeral=True)
        else:
            await inter.response.send_message("管理者専用のコマンドです", ephemeral=True)

    @backup.sub_command(name="check", guild_ids=admin_guild_ids, description="復元できるメンバーの数")
    async def check(self, inter: disnake.AppCmdInter):
        if not int(inter.author.id) in dev_users:
            await inter.response.send_message("You cannot run this command.")
            return
        await inter.response.send_message("確認しています...", ephemeral=True)
        await inter.edit_original_message(content="{}人のメンバーの復元が可能です".format(len(self.db.get_user_tokens())))

    @backup.sub_command(name="restore", description="メンバーの復元を行います", options=[
        disnake.Option(name="srvid", description="復元先のサーバーを選択", type=disnake.OptionType.string, required=True)])
    async def restore(self, inter: disnake.AppCmdInter, guild_id: str):
        if not int(inter.author.id) in dev_users:
            await inter.response.send_message("貴方がが置いた認証パネルで\n認証したメンバーが100人になると使用できます\nSupport Server→ https://discord.gg/TkPw7Nupj8", ephemeral=True)
            return
        embed = disnake.Embed(
            title="バックアップを実行します。",
            description="バックアップ先:" + guild_id,
            color=0x00000
        )
        await inter.response.send_message(embed=embed, ephemeral=True)
        count = 0
        total = 0
        users: List[TokenData] = self.db.get_user_tokens()
        for user in users:
            try:
                result = await self.util.join_guild(user["access_token"], guild_id, user["user_id"])
                if result:
                    count += 1
            except Exception as e:
                logger.info("ユーザー {} は以下の理由によりバックアップできませんでした 理由:{}".format(user, e), LCT.bot_backup)
            total += 1
        await inter.edit_original_message(content=f"{total}人中{count}人のメンバーの復元に成功しました", embed=None)

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
        self.db.set_guild_role({"guild_id": inter.guild_id, "role": role.id})
        embed = disnake.Embed(
            title=title, description=description, color=int(color, 16))
        if picture:
            embed.set_image(url=picture)
        view = disnake.ui.View()
        url = "{}/oauth2/authorize?client_id={}&redirect_uri={}&response_type=code&scope=identify%20guilds.join&state={}".format(
            API_START_POINT, self.bot.user.id, url_quote(
                redirect_uri, safe=""
            ), inter.guild_id
        )
        view.add_item(disnake.ui.Button(
            label="✅認証", style=disnake.ButtonStyle.url, url=url))
        await inter.delete_original_message()
        await inter.channel.send(embed=embed, view=view)
        backup_database()
