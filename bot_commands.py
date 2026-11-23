"""
✨ বটের কমান্ড মেনু (টেলিগ্রামের "/" মেনু) সেট করার হেল্পার।
ক্লোন তৈরি হওয়ার সাথে সাথেই ওই ক্লোন বটে কমান্ডগুলো নিজে থেকে সেট হয়ে যায়:
  • সবার জন্য  → PUBLIC কমান্ড
  • ওনার + মডারেটর → STAFF কমান্ড (broadcast, ban, unban, banlist সহ)
"""
import logging

from pyrogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat

logger = logging.getLogger(__name__)

PUBLIC = [
    ("start", "Start the bot"),
    ("batch", "Upload many files as one batch link"),
    ("done", "Finish batch & get the link"),
    ("clone", "Create your own clone bot"),
]

STAFF = PUBLIC + [
    ("settings", "Open the settings panel"),
    ("broadcast", "Broadcast a message (reply to it)"),
    ("pin_broadcast", "Broadcast & pin (reply to it)"),
    ("ban", "Ban a user"),
    ("unban", "Unban a user"),
    ("banlist", "Show all banned users"),
]

MAIN_ADMIN = STAFF + [
    ("stats", "Bot statistics"),
    ("restart", "Restart the bot"),
]


def _to_commands(items):
    return [BotCommand(c, d) for c, d in items]


async def set_public_commands(client):
    try:
        await client.set_bot_commands(_to_commands(PUBLIC), scope=BotCommandScopeDefault())
    except Exception as e:
        logger.warning(f"set public commands failed: {e}")


async def set_staff_commands(client, user_id: int):
    items = STAFF if getattr(client, "is_clone", False) else MAIN_ADMIN
    try:
        await client.set_bot_commands(_to_commands(items), scope=BotCommandScopeChat(chat_id=int(user_id)))
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
