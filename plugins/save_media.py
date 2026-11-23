import asyncio
import traceback
from urllib.parse import quote

from config import DB_CHANNEL, LOG_CHANNEL, WEBSITE_URL
from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
from utils import str_to_b64, humanbytes
from database import get_db

BATCH_SLEEP = 2


def effective_owner(bot: Client, uid: int) -> int:
    """
    ক্লোন বটে সেটিংস (ক্যাপশন, শর্টনার, ভেরিফাই, অটো-ডিলিট...) সবসময় ক্লোনের
    বর্তমান ওনারের — যে-ই ফাইল আপলোড করুক। এতে মালিকানা ট্রান্সফার/মডারেটর ঠিকমতো কাজ করে।
    """
    if getattr(bot, "is_clone", False) and getattr(bot, "owner_id", None):
        return int(bot.owner_id)
    return int(uid)


def _caption_html(msg: Message):
    cap = getattr(msg, "caption", None)
    if not cap:
        return None
    try:
        return cap.html
    except Exception:
        return str(cap)


def extract_media_info(msg: Message):
    """
    ফাইলের তথ্য। has_name=False মানে ফাইলের নিজের কোনো নাম নেই — তখন ইউজার ফাইলের
    সাথে যে ক্যাপশন দিয়েছে সেটাই ডেলিভারির সময় ক্যাপশন হিসেবে যাবে।
    """
    media, default_name, size = None, None, 0
    if msg.document:
        media, default_name = msg.document, "Document"
    elif msg.video:
        media, default_name = msg.video, "Video.mp4"
    elif msg.audio:
        media, default_name = msg.audio, "Audio.mp3"
    elif msg.photo:
        media, default_name = msg.photo, "Photo.jpg"
    if not media:
        return None

    real_name = None if msg.photo else getattr(media, "file_name", None)
    return {
        "file_id": media.file_id,
        "file_name": real_name or default_name,
        "has_name": bool(real_name),
        "file_size": humanbytes(getattr(media, "file_size", 0)),
        "caption": _caption_html(msg),
    }


def make_link(bot_username: str, code: str) -> str:
    """https://t.me/<bot>?start=<পরিষ্কার-কোড> — কোনো file_ প্রিফিক্স বা = প্যাডিং নেই"""
    return f"https://t.me/{bot_username}?start={code}"


def legacy_permanent_link(owner_uid: int, db_msg_id: int) -> str:
    # ওয়েবসাইট (Permanent Link) আগের ফরম্যাটেই কাজ করে — সেটা ভাঙা হয়নি
    return f"{WEBSITE_URL}?AVBOTZ=file_{str_to_b64(f'{owner_uid}:{db_msg_id}')}"


def build_share_buttons(is_clone: bool, share_link: str, short_link: str):
    buttons = [[InlineKeyboardButton("📂 Original Link", url=share_link)]]
    if not is_clone:
        buttons.append([
            InlineKeyboardButton("• Updates •", url="https://t.me/PrimeXBots"),
            InlineKeyboardButton("• Support •", url="https://t.me/Prime_Support_group"),
        ])
    if short_link != share_link:
        buttons.insert(0, [InlineKeyboardButton("🔗 Shortened Link", url=short_link)])
    # ✨ Share বাটন (সবার নিচে): টেলিগ্রামের শেয়ার-পিকার খোলে
    to_share = short_link or share_link
    buttons.append([InlineKeyboardButton("📤 Share", url=f"https://t.me/share/url?url={quote(to_share, safe='')}")])
    return InlineKeyboardMarkup(buttons)


async def copy_to_channel(bot: Client, message: Message, editable: Message):
    try:
        return await message.copy(DB_CHANNEL)
    except FloodWait as sl:
        await asyncio.sleep(sl.value)
        return await copy_to_channel(bot, message, editable)
    except Exception:
        try:
            await bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"#ERROR_COPY:\nChat: `{editable.chat.id}`\n\n**Traceback:**\n`{traceback.format_exc()}`"
            )
        except Exception:
            pass
        return None


async def save_batch_media_in_channel(bot: Client, editable: Message, message_ids: list, owner_uid: int):
    cur_db = get_db(bot)
    is_clone = getattr(bot, "is_clone", False)
    bot_username = getattr(bot, "username", None) or (await bot.get_me()).username
    db_msg_id = None

    try:
        messages = await bot.get_messages(chat_id=editable.chat.id, message_ids=message_ids)

        if is_clone:
            items = []
            for m in messages:
                info = extract_media_info(m)
                if info:
                    items.append(info)
            if not items:
                return await editable.edit("❌ No valid media files found in your batch!")
            code = await cur_db.create_link(owner_uid, items=items)
        else:
            sent_ids = []
            for message in messages:
                sent_message = await copy_to_channel(bot, message, editable)
                if sent_message:
                    sent_ids.append(str(sent_message.id))
                await asyncio.sleep(BATCH_SLEEP)
            if not sent_ids:
                return await editable.edit("❌ No valid media files found in your batch!")

            SaveMessage = await bot.send_message(
                chat_id=DB_CHANNEL,
                text=" ".join(sent_ids),
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Close", callback_data="close_data")]])
            )
            db_msg_id = SaveMessage.id
            code = await cur_db.create_link(owner_uid, db_msg_id=db_msg_id)

        user = await cur_db.get_user(owner_uid)
        if user.get("permanent_link_mode", False) and not is_clone:
            share_link = legacy_permanent_link(owner_uid, db_msg_id)
        else:
            share_link = make_link(bot_username, code)

        short_link = await cur_db.get_short_link(user, share_link)

        text = (
            "<b>📦 Here is your batch file link!</b>\n\n"
            f"<b>Original Link:</b> {share_link}\n"
        )
        if short_link != share_link:
            text += f"\n<b>Shortened Link:</b> {short_link}\n"
        text += "\nClick the link to get your files!"

        await editable.edit(
            text,
            reply_markup=build_share_buttons(is_clone, share_link, short_link),
            disable_web_page_preview=True
        )

        if not is_clone:
            try:
                await bot.send_message(
                    chat_id=LOG_CHANNEL,
                    text=f"#BATCH_SAVE:\n\nUser [{owner_uid}](tg://user?id={owner_uid}) Got Batch Link!",
                    disable_web_page_preview=True,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📂 Open Link", url=share_link)]])
                )
            except Exception:
                pass

    except Exception:
        await editable.edit("❌ Something went wrong while saving batch files!")
        try:
            await bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"#ERROR_BATCH:\nChat: `{editable.chat.id}`\n\n**Traceback:**\n`{traceback.format_exc()}`"
            )
        except Exception:
            pass


async def save_media_in_channel(bot: Client, editable: Message, message: Message):
    cur_db = get_db(bot)
    is_clone = getattr(bot, "is_clone", False)
    bot_username = getattr(bot, "username", None) or (await bot.get_me()).username

    try:
        if message.from_user:
            uploader_uid = message.from_user.id
            user_name = message.from_user.first_name
        elif message.sender_chat:
            uploader_uid = message.sender_chat.id
            user_name = message.sender_chat.title or "Channel"
        else:
            uploader_uid = 0
            user_name = "Unknown"
        owner_uid = effective_owner(bot, uploader_uid)

        db_msg_id = None
        if is_clone:
            info = extract_media_info(message)
            if not info:
                return await editable.edit("❌ Unsupported file type!")
            code = await cur_db.create_link(owner_uid, items=[info])
        else:
            copied_msg = await message.copy(DB_CHANNEL)
            db_msg_id = copied_msg.id
            try:
                await copied_msg.reply_text(
                    f"#PRIVATE_FILE:\n\n[{user_name}](tg://user?id={owner_uid}) Got File Link!",
                    disable_web_page_preview=True
                )
            except Exception:
                pass
            code = await cur_db.create_link(owner_uid, db_msg_id=db_msg_id)

        user = await cur_db.get_user(owner_uid)
        if user.get("permanent_link_mode", False) and not is_clone:
            share_link = legacy_permanent_link(owner_uid, db_msg_id)
        else:
            share_link = make_link(bot_username, code)

        short_link = await cur_db.get_short_link(user, share_link)

        text = (
            "<b>📂 Here is your shareable file link!</b>\n\n"
            f"<b>Original Link:</b> {share_link}\n"
        )
        if short_link != share_link:
            text += f"\n<b>Shortened Link:</b> {short_link}\n"
        text += "\nClick the link to get your file!"

        await editable.edit(
            text,
            reply_markup=build_share_buttons(is_clone, share_link, short_link),
            disable_web_page_preview=True
        )

    except FloodWait as sl:
        await asyncio.sleep(sl.value)
        return await save_media_in_channel(bot, editable, message)
    except Exception:
        await editable.edit("❌ Something went wrong while saving the file!")
        try:
            await bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"#ERROR_FILE:\nChat: `{editable.chat.id}`\n\n**Traceback:**\n`{traceback.format_exc()}`",
                disable_web_page_preview=True
            )
        except Exception:
            pass
