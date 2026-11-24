"""
✨ বটের কমান্ড মেনু (টেলিগ্রামের "/" মেনু) সেট করার হেল্পার।
ক্লোন তৈরি হওয়ার সাথে সাথেই ওই ক্লোন বটে কমান্ডগুলো নিজে থেকে সেট হয়ে যায়:
  • সবার জন্য  → PUBLIC কমান্ড
  • ওনার + মডারেটর → STAFF কমান্ড (broadcast, ban, unban, banlist সহ)
"""
import logging

from pyrogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat

logger = logging.getLogger(__name__)

# ✨ সব কমান্ড সবার মেনুতে দেখানো হয়। অ্যাডমিন-কমান্ড সাধারণ ইউজার দিলে সুন্দর
# "Access Denied" ওয়ার্নিং পায় (plugins/moderation.py দেখুন)।
CLONE_COMMANDS = [
    ("start", "sᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ 🚀"),
    ("clone", "ᴄʀᴇᴀᴛᴇ ʏᴏᴜʀ ᴏᴡɴ ᴄʟᴏɴᴇ ʙᴏᴛ 🤖"),
    ("batch", "ᴜᴘʟᴏᴀᴅ ᴍᴀɴʏ ғɪʟᴇs ᴀs ᴏɴᴇ ʙᴀᴛᴄʜ ʟɪɴᴋ 📦"),
    ("done", "ғɪɴɪsʜ ʙᴀᴛᴄʜ & ɢᴇᴛ ᴛʜᴇ ʟɪɴᴋ 🔗"),
    ("settings", "ᴏᴘᴇɴ sᴇᴛᴛɪɴɢs ᴘᴀɴᴇʟ (ᴏᴡɴᴇʀ) ⚙️"),
    ("broadcast", "ʙʀᴏᴀᴅᴄᴀsᴛ ᴀ ᴍᴇssᴀɢᴇ (ᴏᴡɴᴇʀ) 📢"),
    ("pin_broadcast", "ʙʀᴏᴀᴅᴄᴀsᴛ & ᴘɪɴ (ᴏᴡɴᴇʀ) 📌"),
    ("ban", "ʙᴀɴ ᴀ ᴜsᴇʀ (ᴏᴡɴᴇʀ) 🚫"),
    ("unban", "ᴜɴʙᴀɴ ᴀ ᴜsᴇʀ (ᴏᴡɴᴇʀ) ✅"),
    ("banlist", "sʜᴏᴡ ʙᴀɴɴᴇᴅ ᴜsᴇʀs (ᴏᴡɴᴇʀ) 📋"),
]

MAIN_COMMANDS = [
    ("start", "sᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ 🚀"),
    ("clone", "ᴄʀᴇᴀᴛᴇ ʏᴏᴜʀ ᴏᴡɴ ᴄʟᴏɴᴇ ʙᴏᴛ 🤖"),
    ("settings", "ᴏᴘᴇɴ ʏᴏᴜʀ sᴇᴛᴛɪɴɢs ⚙️"),
    ("batch", "ᴜᴘʟᴏᴀᴅ ᴍᴀɴʏ ғɪʟᴇs ᴀs ᴏɴᴇ ʙᴀᴛᴄʜ ʟɪɴᴋ 📦"),
    ("done", "ғɪɴɪsʜ ʙᴀᴛᴄʜ & ɢᴇᴛ ᴛʜᴇ ʟɪɴᴋ 🔗"),
    ("broadcast", "ʙʀᴏᴀᴅᴄᴀsᴛ ᴀ ᴍᴇssᴀɢᴇ (ᴀᴅᴍɪɴ) 📢"),
    ("pin_broadcast", "ʙʀᴏᴀᴅᴄᴀsᴛ & ᴘɪɴ (ᴀᴅᴍɪɴ) 📌"),
    ("ban", "ʙᴀɴ ᴀ ᴜsᴇʀ (ᴀᴅᴍɪɴ) 🚫"),
    ("unban", "ᴜɴʙᴀɴ ᴀ ᴜsᴇʀ (ᴀᴅᴍɪɴ) ✅"),
    ("banlist", "sʜᴏᴡ ʙᴀɴɴᴇᴅ ᴜsᴇʀs (ᴀᴅᴍɪɴ) 📋"),
    ("stats", "ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs (ᴀᴅᴍɪɴ) 📊"),
    ("restart", "ʀᴇsᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ (ᴀᴅᴍɪɴ) 🔄"),
]


def _commands_for(client):
    return CLONE_COMMANDS if getattr(client, "is_clone", False) else MAIN_COMMANDS


def _to_commands(items):
    return [BotCommand(c, d) for c, d in items]


async def set_public_commands(client):
    try:
        await client.set_bot_commands(_to_commands(_commands_for(client)), scope=BotCommandScopeDefault())
    except Exception as e:
        logger.warning(f"set public commands failed: {e}")


async def set_staff_commands(client, user_id: int):
    try:
        await client.set_bot_commands(_to_commands(_commands_for(client)), scope=BotCommandScopeChat(chat_id=int(user_id)))
        return True
    except Exception as e:
        # ইউজার এখনো বটে /start না দিলে টেলিগ্রাম এটা নেয় না — /start দিলে নিচের ensure_ দিয়ে আবার সেট হবে
        logger.info(f"set staff commands for {user_id} deferred: {e}")
        return False


async def clear_staff_commands(client, user_id: int):
    try:
        await client.delete_bot_commands(scope=BotCommandScopeChat(chat_id=int(user_id)))
    except Exception:
        pass


async def ensure_staff_commands(client, user_id: int):
    """স্টাফ ইউজার /start দিলে একবার কমান্ড মেনু নিশ্চিত করে (সেশনে একবারই)"""
    synced = getattr(client, "_cmd_synced", None)
    if synced is None:
        synced = client._cmd_synced = set()
    if int(user_id) in synced:
        return
    if await set_staff_commands(client, user_id):
        synced.add(int(user_id))
