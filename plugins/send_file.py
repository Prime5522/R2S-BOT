import asyncio
import logging

from config import DEFAULT_AUTO_DELETE_TIME
from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from utils import format_duration

logger = logging.getLogger(__name__)

# {time} লেখা থাকলে সেখানে অটো-ডিলিটের সময় বসে যাবে (যেমন "5 minutes")
DEFAULT_AUTODELETE_MSG = (
    "<b>♻️ ꜰɪʟᴇs ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ɪɴ {time} ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛ ɪssᴜᴇs. "
    "ᴘʟᴇᴀsᴇ ғᴏʀᴡᴀʀᴅ ᴀɴᴅ sᴀᴠᴇ ᴛʜᴇᴍ. 🗑</b>"
)

DELETED_INFO_TEXT = (
    "❌ ʏᴏᴜʀ ꜰɪʟᴇs ʜᴀᴠᴇ ʙᴇᴇɴ ᴅᴇʟᴇᴛᴇᴅ ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛ ɪssᴜᴇs. "
    "ᴏᴘᴇɴ ᴛʜᴇ ʟɪɴᴋ ᴀɢᴀɪɴ ᴛᴏ ɢᴇᴛ ᴛʜᴇᴍ. 🗑"
)

MIN_AUTODELETE_SECONDS = 10
MAX_AUTODELETE_SECONDS = 86400  # টেলিগ্রাম ৪৮ ঘণ্টার পুরনো মেসেজ ডিলিট করতে দেয় না, তাই সর্বোচ্চ ২৪ ঘণ্টা


def get_autodelete_config(settings: dict):
    """ওনারের সেটিং থেকে (enabled, seconds, message_template) রিটার্ন করে"""
    enabled = settings.get("auto_delete", True)
    seconds = settings.get("auto_delete_time") or DEFAULT_AUTO_DELETE_TIME
    template = settings.get("auto_delete_msg") or DEFAULT_AUTODELETE_MSG
    return bool(enabled), int(seconds), template


def render_autodelete_msg(template: str, seconds: int) -> str:
    return template.replace("{time}", format_duration(seconds))


async def delete_file(bot: Client, chat_id: int, msg_id: int, send_info: bool = True, delay: int = 300):
    await asyncio.sleep(delay)
    try:
        await bot.delete_messages(chat_id, msg_id)
        if send_info:
            await bot.send_message(chat_id, DELETED_INFO_TEXT)
    except Exception as e:
        print(f"Delete failed: {e}")


async def schedule_autodelete(bot: Client, message: Message, sent_msgs: list, settings: dict):
    """
    ✨ ফাইল পাঠানোর পর কল হয়: ওনারের Auto Delete সেটিং অনুযায়ী
    ওয়ার্নিং মেসেজ পাঠায় আর নির্ধারিত সময় পর ফাইলগুলো ডিলিট করে।
    অফ থাকলে কিছুই করে না (ফাইল থেকে যাবে)।
    """
    enabled, seconds, template = get_autodelete_config(settings)
    if not enabled:
        return

    chat_id = message.chat.id
    text = render_autodelete_msg(template, seconds)
    warn_msg = None
    while True:
        try:
            warn_msg = await message.reply_text(text, disable_web_page_preview=True)
            break
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            # কাস্টম মেসেজের HTML ভুল হলে ডিফল্ট মেসেজ পাঠাবে
            try:
                warn_msg = await message.reply_text(
                    render_autodelete_msg(DEFAULT_AUTODELETE_MSG, seconds),
                    disable_web_page_preview=True,
                )
            except Exception:
                pass
            break

    for i, m in enumerate(s for s in sent_msgs if s):
        asyncio.create_task(delete_file(bot, chat_id, m.id, send_info=(i == 0), delay=seconds))
    if warn_msg:
        asyncio.create_task(delete_file(bot, chat_id, warn_msg.id, send_info=False, delay=seconds))
