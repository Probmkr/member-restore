import json
import disnake
import os
import aiohttp
import base64
import asyncio
from io import BytesIO
from disnake import Colour, Embed, File


backup_base = "guild_backup"


def toPerm(dic):
    return disnake.Permissions(**dic)


def toPermo(dic):
    return disnake.PermissionOverwrite(**dic)


def keyErrDetect(x, y):
    try:
        x[y]
    except:
        return True
    return False


class newRole:
    def __init__(self, r, oid):
        self.r = r
        self.perms = toPerm(r["permissions"])
        self.name = r["name"]
        self.rgb = r["color"]
        self.hoist = r["hoist"]
        self.old_id = oid

    async def create(self, g):
        newr: disnake.Role = await g.create_role(hoist=self.hoist, name=self.name, colour=Colour.from_rgb(
            self.rgb[0], self.rgb[1], self.rgb[2]), permissions=self.perms)
        self.id = newr.id
        self.role = newr

    def to_dict(self):
        r = self.r
        v = self.perms
        return {
            "name": r["name"],
            "color": r["color"],
            "hoist": r["hoist"],
            "permissions": {
                "add_reactions": v.add_reactions,
                "administrator": v.administrator,
                "attach_files": v.attach_files,
                "ban_members": v.ban_members,
                "change_nickname": v.change_nickname,
                "connect": v.connect,
                "create_forum_threads": v.create_forum_threads,
                "create_instant_invite": v.create_instant_invite,
                "create_private_threads": v.create_private_threads,
                "create_public_threads": v.create_public_threads,
                "deafen_members": v.deafen_members,
                "embed_links": v.embed_links,
                "external_emojis": v.external_emojis,
                "external_stickers": v.external_stickers,
                "kick_members": v.kick_members,
                "manage_channels": v.manage_channels,
                "manage_emojis": v.manage_emojis,
                "manage_emojis_and_stickers": v.manage_emojis_and_stickers,
                "manage_events": v.manage_events,
                "manage_guild": v.manage_guild,
                "manage_messages": v.manage_messages,
                "manage_nicknames": v.manage_nicknames,
                "manage_permissions": v.manage_permissions,
                "manage_roles": v.manage_roles,
                "manage_threads": v.manage_threads,
                "manage_webhooks": v.manage_webhooks,
                "mention_everyone": v.mention_everyone,
                "moderate_members": v.moderate_members,
                "move_members": v.move_members,
                "mute_members": v.mute_members,
                "priority_speaker": v.priority_speaker,
                "read_message_history": v.read_message_history,
                "read_messages": v.read_messages,
                "request_to_speak": v.request_to_speak,
                "send_messages": v.send_messages,
                "send_messages_in_threads": v.send_messages_in_threads,
                "send_tts_messages": v.send_tts_messages,
                "speak": v.speak,
                "start_embedded_activities": v.start_embedded_activities,
                "stream": v.stream,
                "use_application_commands": v.use_application_commands,
                "use_embedded_activities": v.use_embedded_activities,
                "use_external_emojis": v.use_external_emojis,
                "use_external_stickers": v.use_external_stickers,
                "use_slash_commands": v.use_slash_commands,
                "use_voice_activation": v.use_voice_activation,
                "view_audit_log": v.view_audit_log,
                "view_channel": v.view_channel,
                "view_guild_insights": v.view_guild_insights
            }
        }


async def toarg(obj):
    res = {
        "files": [],
        "username": obj["author"]["name"],
        "avatar_url": obj["author"]["icon"],
        "embeds": list(map(lambda x: Embed.from_dict(x), obj["embeds"]))
    }
    async with aiohttp.ClientSession() as sess:
        for url in obj["attachments"]:
            async with sess.get(url) as resp:
                res["files"].append(File(BytesIO(await resp.read()), url.split("/")[-1]))
    return [obj["content"], res]


async def chcreate(target: disnake.Guild, cho, roles: disnake.Role):
    permo = {}
    for p in cho["perms"]:
        try:
            if not p["everyone"]:
                per = p.copy()
                per.pop("id")
                per.pop("everyone")
                permo[roles[str(p["id"])]] = disnake.PermissionOverwrite(**per)
            else:
                per = p.copy()
                per.pop("id")
                per.pop("everyone")
                permo[roles["everyone"]
                      ] = disnake.PermissionOverwrite(**per)
        except:
            None
            continue
    if cho["type"] == 0 or cho["type"] == 5:
        gch = await target.create_text_channel(cho["name"], overwrites=permo, nsfw=cho["nsfw"], slowmode_delay=cho["delay"], news=cho["type"] == 5)
        wh = await gch.create_webhook(name="復元用")
        for m in cho["messages"][::-1]:
            try:
                margs = await toarg(m)
                await wh.send(margs[0], **margs[1])
            except Exception as e:
                print(e.__class__.__name__ + ": " + str(e))
    elif cho["type"] == 4:
        return await target.create_category_channel(cho["name"], overwrites=permo)
    elif cho["type"] == 2:
        return await target.create_voice_channel(cho["name"], overwrites=permo)
    elif cho["type"] == 13:
        try:
            return await target.create_stage_channel(cho["name"], overwrites=permo)
        except disnake.errors.HTTPException:
            return await target.create_voice_channel(cho["name"], overwrites=permo)
    elif cho["type"] == 15:
        return await target.create_forum_channel(cho["name"], overwrites=permo, slowmode_delay=cho["delay"], nsfw=cho["nsfw"])


def memberOrRole(target):
    if type(target) is disnake.Member:
        return "M"
    elif type(target) is disnake.Role:
        return "R"


def isset(v):
    if v:
        return True
    else:
        return False


async def convemj(emoji: disnake.Emoji):
    res = {
        "name": emoji.name,
        "content": base64.b64encode(await emoji.read()).decode()
    }
    return res


def convmsg(msg: disnake.Message):
    res = {
        "content": msg.content,
        "attachments": list(map(lambda x: x.url, msg.attachments)),
        "author": {
            "name": msg.author.name,
        },
        "embeds": list(map(lambda x: x.to_dict(), msg.embeds))
    }
    try:
        res["author"]["icon"] = msg.author.avatar.url
    except:
        res["author"]["icon"] = None
    return res


async def convchannel(channel: disnake.TextChannel, features=[]):
    res = {
        "name": channel.name,
        "topic": getattr(channel, "topic", False),
        "type": channel.type.value,
        "perms": [],
        "position": channel.position,
        "hasCategory": isset(channel.category),
        "messages": []
    }
    try:
        res["nsfw"] = channel.nsfw
    except:
        None
    try:
        res["delay"] = channel.slowmode_delay
    except:
        None
    if channel.type.value == 0 and "messages" in features:
        for message in await channel.history(limit=50).flatten():
            res["messages"].append(convmsg(message))
    if channel.type.value == 4:
        res["channels"] = []
        for c in channel.channels:
            res["channels"].append(await convchannel(c, features))
        [res["channels"].append(x) for x in res["channels"]
         if x not in res["channels"]]

    for k, v in channel.overwrites.items():
        if memberOrRole(k) != "R":
            continue
        res["perms"].append({
            "id": str(k.id),
            "everyone": k.is_default(),
            "add_reactions": v.add_reactions,
            "administrator": v.administrator,
            "attach_files": v.attach_files,
            "ban_members": v.ban_members,
            "change_nickname": v.change_nickname,
            "connect": v.connect,
            "create_forum_threads": v.create_forum_threads,
            "create_instant_invite": v.create_instant_invite,
            "create_private_threads": v.create_private_threads,
            "create_public_threads": v.create_public_threads,
            "deafen_members": v.deafen_members,
            "embed_links": v.embed_links,
            "external_emojis": v.external_emojis,
            "external_stickers": v.external_stickers,
            "kick_members": v.kick_members,
            "manage_channels": v.manage_channels,
            "manage_emojis": v.manage_emojis,
            "manage_emojis_and_stickers": v.manage_emojis_and_stickers,
            "manage_events": v.manage_events,
            "manage_guild": v.manage_guild,
            "manage_messages": v.manage_messages,
            "manage_nicknames": v.manage_nicknames,
            "manage_permissions": v.manage_permissions,
            "manage_roles": v.manage_roles,
            "manage_threads": v.manage_threads,
            "manage_webhooks": v.manage_webhooks,
            "mention_everyone": v.mention_everyone,
            "moderate_members": v.moderate_members,
            "move_members": v.move_members,
            "mute_members": v.mute_members,
            "priority_speaker": v.priority_speaker,
            "read_message_history": v.read_message_history,
            "read_messages": v.read_messages,
            "request_to_speak": v.request_to_speak,
            "send_messages": v.send_messages,
            "send_messages_in_threads": v.send_messages_in_threads,
            "send_tts_messages": v.send_tts_messages,
            "speak": v.speak,
            "start_embedded_activities": v.start_embedded_activities,
            "stream": v.stream,
            "use_application_commands": v.use_application_commands,
            "use_embedded_activities": v.use_embedded_activities,
            "use_external_emojis": v.use_external_emojis,
            "use_external_stickers": v.use_external_stickers,
            "use_slash_commands": v.use_slash_commands,
            "use_voice_activation": v.use_voice_activation,
            "view_audit_log": v.view_audit_log,
            "view_channel": v.view_channel,
            "view_guild_insights": v.view_guild_insights
        })
    return res

disnake.Role
async def parseguild(g: disnake.Guild, features: list[str]):
    res = {
        "features": features
    }
    if "info" in features:
        res["info"] = {
            "name": g.name,
            "description": g.description
        }
        if isset(g.icon):
            res["info"]["icon"] = base64.b64encode(await g.icon.read()).decode()
    if "emojis" in features:
        res["emojis"] = []
        for e in g.emojis:
            res["emojis"].append(await convemj(e))
    if "bans" in features:
        res["bans"] = []
        for bm in await g.bans(limit=None).flatten():
            res["bans"].append({
                "id": bm.user.id,
                "reason": bm.reason
            })
    if "channels" in features:
        res["channels"] = []
        for c in g.channels:
            res["channels"].append(await convchannel(c, features))
    if "roles" in features:
        res["roles"] = {}
        for r in reversed(g.roles):
            if r.is_bot_managed():
                continue
            v = r.permissions
            res["roles"][str(r.id)] = {
                "name": r.name,
                "everyone": r.is_default(),
                "hoist": r.hoist,
                "color": [r.color.r, r.color.g, r.color.b],
                "permissions": {
                    "add_reactions": v.add_reactions,
                    "administrator": v.administrator,
                    "attach_files": v.attach_files,
                    "ban_members": v.ban_members,
                    "change_nickname": v.change_nickname,
                    "connect": v.connect,
                    "create_forum_threads": v.create_forum_threads,
                    "create_instant_invite": v.create_instant_invite,
                    "create_private_threads": v.create_private_threads,
                    "create_public_threads": v.create_public_threads,
                    "deafen_members": v.deafen_members,
                    "embed_links": v.embed_links,
                    "external_emojis": v.external_emojis,
                    "external_stickers": v.external_stickers,
                    "kick_members": v.kick_members,
                    "manage_channels": v.manage_channels,
                    "manage_emojis": v.manage_emojis,
                    "manage_emojis_and_stickers": v.manage_emojis_and_stickers,
                    "manage_events": v.manage_events,
                    "manage_guild": v.manage_guild,
                    "manage_messages": v.manage_messages,
                    "manage_nicknames": v.manage_nicknames,
                    "manage_permissions": v.manage_permissions,
                    "manage_roles": v.manage_roles,
                    "manage_threads": v.manage_threads,
                    "manage_webhooks": v.manage_webhooks,
                    "mention_everyone": v.mention_everyone,
                    "moderate_members": v.moderate_members,
                    "move_members": v.move_members,
                    "mute_members": v.mute_members,
                    "priority_speaker": v.priority_speaker,
                    "read_message_history": v.read_message_history,
                    "read_messages": v.read_messages,
                    "request_to_speak": v.request_to_speak,
                    "send_messages": v.send_messages,
                    "send_messages_in_threads": v.send_messages_in_threads,
                    "send_tts_messages": v.send_tts_messages,
                    "speak": v.speak,
                    "start_embedded_activities": v.start_embedded_activities,
                    "stream": v.stream,
                    "use_application_commands": v.use_application_commands,
                    "use_embedded_activities": v.use_embedded_activities,
                    "use_external_emojis": v.use_external_emojis,
                    "use_external_stickers": v.use_external_stickers,
                    "use_slash_commands": v.use_slash_commands,
                    "use_voice_activation": v.use_voice_activation,
                    "view_audit_log": v.view_audit_log,
                    "view_channel": v.view_channel,
                    "view_guild_insights": v.view_guild_insights
                }
            }
    return res


async def backup(interaction: disnake.AppCmdInter):
    ar = disnake.ui.ActionRow()
    ar.add_string_select(custom_id="features_select", options=[
        disnake.SelectOption(
            label="Messages", description="バックアップにメッセージを含めるかの設定", value="messages", emoji="💬"),
        disnake.SelectOption(
            label="GuildInfo", description="バックアップにアイコンや名前などのサーバー情報を含めるかの設定", value="info", emoji="❓"),
        disnake.SelectOption(
            label="Channel", description="バックアップにチャンネルを含めるかの設定", value="channels", emoji="#⃣"),
        disnake.SelectOption(
            label="Roles", description="バックアップにロールを含めるかの設定", value="roles", emoji="👥"),
        disnake.SelectOption(
            label="Bans", description="バックアップにBANされたメンバーを含めるかの設定", value="bans", emoji="🚫"),
        disnake.SelectOption(
            label="Emojis", description="バックアップに絵文字を含めるかの設定", value="emojis", emoji="😊")
    ], min_values=1, max_values=6)
    await interaction.send(components=ar)


async def backuphandle(interaction: disnake.MessageInteraction):
    if not interaction.component.custom_id == "features_select":
        return
    ginfo = await parseguild(interaction.guild, interaction.values)
    fp = open(f"{backup_base}/{interaction.guild.id}.json", "w", encoding="utf-8")
    json.dump(ginfo, fp, ensure_ascii=False)
    fp.close()
    await interaction.send(f"セーブに成功しました。\nバックアップid: {interaction.guild.id}", ephemeral=True)


async def restore(f: dict, g: disnake.Guild, features=[]):
    newRoles = {}
    if "info" in features:
        try:
            await g.edit(name=f["info"]["name"], description=f["info"]
                         ["description"])
            if not keyErrDetect(f["info"], "icon"):
                await g.edit(icon=base64.b64decode(f["info"]["icon"]))
        except:
            None
    if "emojis" in features:
        for e in g.emojis:
            await e.delete()
        for ed in f["emojis"]:
            await g.create_custom_emoji(
                name=ed["name"], image=base64.b64decode(ed["content"]))
    if "bans" in features:
        for bm in f["bans"]:
            await g.ban(disnake.Object(bm["id"]), reason=bm["reason"])
    if "roles" in features:
        everyone = next(
            filter(lambda r: r["everyone"], list(f["roles"].values())), None)
        await g.default_role.edit(permissions=toPerm(
            everyone["permissions"]))
        for r in g.roles:
            try:
                await r.delete()
            except:
                None
        for id, r in f["roles"].items():
            if not r["everyone"]:
                newr = newRole(r, id)
                await newr.create(g)
                newRoles[newr.old_id] = newr.role
            else:
                newRoles["everyone"] = g.default_role
    if "channels" in features:
        uncategorized = list(
            filter(lambda x: x["hasCategory"] == False, f["channels"]))
        categories = list((filter(lambda x: x["type"] == 4, f["channels"])))
        categories = list(sorted(categories, key=lambda category: category["position"]))
        async def del_channel(channel: disnake.abc.GuildChannel):
            try:
                await channel.delete()
            except:
                pass

        await asyncio.gather(*[del_channel(c) for c in g.channels])

        for c in uncategorized:
            if c["type"] == 4:
                continue
            await chcreate(g, c, newRoles)

        for category in categories:
            cch = await chcreate(g, category, newRoles)
            for ch in category["channels"]:
                await chcreate(cch, ch, newRoles)


async def restorehandle(interaction: disnake.AppCmdInter, id: str):
    if not os.path.isfile(f"backup/{id}.json"):
        return await interaction.send("無効なバックアップIDです。")
    await interaction.send("リストアしています... (完了には時間がかかる場合があります。)")
    fp = open(f"{backup_base}/{id}.json", "r", encoding="utf-8")
    inf = json.load(fp)
    fp.close()
    await restore(inf, interaction.guild, inf["features"])
