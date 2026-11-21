import asyncio
import traceback
from config import DB_CHANNEL, LOG_CHANNEL, WEBSITE_URL
from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
from utils import str_to_b64, humanbytes
from database import get_db

BATCH_SLEEP = 2


def extract_media_info(msg: Message):
    if msg.document:
        return {
            "file_id": msg.document.file_id,
            "file_name": msg.document.file_name or "Document",
            "file_size": humanbytes(msg.document.file_size),
        }
    if msg.video:
        return {
            "file_id": msg.video.file_id,
            "file_name": msg.video.file_name or "Video.mp4",
            "file_size": humanbytes(msg.video.file_size),
        }
    if msg.audio:
        return {
            "file_id": msg.audio.file_id,
            "file_name": msg.audio.file_name or "Audio.mp3",
            "file_size": humanbytes(msg.audio.file_size),
        }
    if msg.photo:
        return {
            "file_id": msg.photo.file_id,
            "file_name": "Photo.jpg",
            "file_size": humanbytes(msg.photo.file_size),
        }
    return None


def build_share_buttons(is_clone: bool, share_link: str, short_link: str):
    buttons = [[InlineKeyboardButton("📂 Original Link", url=share_link)]]
    if not is_clone:
        buttons.append([
            InlineKeyboardButton("• Updates •", url="https://t.me/PrimeXBots"),
            InlineKeyboardButton("• Support •", url="https://t.me/Prime_Support_group"),
        ])
    if short_link != share_link:
        buttons.insert(0, [InlineKeyboardButton("🔗 Shortened Link", url=short_link)])
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
            stored_id = await cur_db.save_clone_file(owner_uid, items)
            unique_str = f"{owner_uid}:{stored_id}"
        else:
            message_ids_str = ""
            for message in messages:
                sent_message = await copy_to_channel(bot, message, editable)
                if sent_message:
                    message_ids_str += f"{sent_message.id} "
                await asyncio.sleep(BATCH_SLEEP)

            SaveMessage = await bot.send_message(
                chat_id=DB_CHANNEL,
                text=message_ids_str.strip(),
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Close", callback_data="close_data")]])
            )
            unique_str = f"{owner_uid}:{SaveMessage.id}"

        user = await cur_db.get_user(owner_uid)
        use_permanent_link = user.get("permanent_link_mode", False)

        if use_permanent_link and not is_clone:
            share_link = f"{WEBSITE_URL}?AVBOTZ=file_{str_to_b64(unique_str)}"
        else:
            share_link = f"https://t.me/{bot_username}?start=file_{str_to_b64(unique_str)}"

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
            owner_uid = message.from_user.id
            user_name = message.from_user.first_name
        elif message.sender_chat:
            owner_uid = message.sender_chat.id
            user_name = message.sender_chat.title or "Channel"
        else:
            owner_uid = 0
            user_name = "Unknown"

        if is_clone:
            info = extract_media_info(message)
            if not info:
                return await editable.edit("❌ Unsupported file type!")
            stored_id = await cur_db.save_clone_file(owner_uid, [info])
            unique_str = f"{owner_uid}:{stored_id}"
        else:
            copied_msg = await message.copy(DB_CHANNEL)
            file_er_id = str(copied_msg.id)
            try:
                await copied_msg.reply_text(
                    f"#PRIVATE_FILE:\n\n[{user_name}](tg://user?id={owner_uid}) Got File Link!",
                    disable_web_page_preview=True
                )
            except Exception:
                pass
            unique_str = f"{owner_uid}:{file_er_id}"

        user = await cur_db.get_user(owner_uid)
        use_permanent_link = user.get("permanent_link_mode", False)

        if use_permanent_link and not is_clone:
            share_link = f"{WEBSITE_URL}?AVBOTZ=file_{str_to_b64(unique_str)}"
        else:
            share_link = f"https://t.me/{bot_username}?start=file_{str_to_b64(unique_str)}"

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
