import asyncio
import traceback
from config import BOT_USERNAME, DB_CHANNEL, LOG_CHANNEL
from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
from utils import str_to_b64
from database import db

BATCH_SLEEP = 2


# 🔥 Copy message to DB channel safely
async def copy_to_channel(bot: Client, message: Message, editable: Message):
    try:
        return await message.copy(DB_CHANNEL)
    except FloodWait as sl:
        await asyncio.sleep(sl.value)
        return await copy_to_channel(bot, message, editable)
    except Exception:
        await bot.send_message(
            chat_id=LOG_CHANNEL,
            text=f"#ERROR_COPY:\nChat: `{editable.chat.id}`\n\n**Traceback:**\n`{traceback.format_exc()}`"
        )
        return None


# 🔥 Save Batch Media
async def save_batch_media_in_channel(bot: Client, editable: Message, message_ids: list, owner_uid: int):
    try:
        message_ids_str = ""
        messages = await bot.get_messages(chat_id=editable.chat.id, message_ids=message_ids)

        for message in messages:
            sent_message = await copy_to_channel(bot, message, editable)
            if sent_message:
                message_ids_str += f"{sent_message.id} "
            await asyncio.sleep(BATCH_SLEEP)

        SaveMessage = await bot.send_message(
            chat_id=DB_CHANNEL,
            text=message_ids_str.strip(),
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Close", callback_data="closeMessage")]])
        )

        # ✅ Encode user_id + batch_msg_id
        unique_str = f"{owner_uid}:{SaveMessage.id}"

        # ✅ Direct bot link only
        share_link = f"https://t.me/{BOT_USERNAME}?start=file_{str_to_b64(unique_str)}"

        # ✅ DB থেকে user settings
        user = await db.get_user(owner_uid)
        short_link = await db.get_short_link(user, share_link)

        # --- Text বানাও ---
        text = (
            "ʜᴇʀᴇ ɪs ʏᴏᴜʀ ʙᴀᴛᴄʜ ꜰɪʟᴇ ʟɪɴᴋ❗\n\n"
            f"ᴏʀɢɪɴᴀʟ ʟɪɴᴋ: {share_link}\n"
        )
        if short_link != share_link:
            text += f"\nsʜᴏʀᴛᴇɴ ʟɪɴᴋ: {short_link}\n\n"
        else:
            text += "\n"
        text += "ᴊᴜsᴛ ᴄʟɪᴄᴋ ᴛʜᴇ ʟɪɴᴋ ᴛᴏ ɢᴇᴛ ʏᴏᴜʀ ꜰɪʟᴇ!"

        # --- Buttons বানাও ---
        buttons = [
            [InlineKeyboardButton("📂 ᴏʀɢɪɴᴀʟ ʟɪɴᴋ", url=share_link)],
            [
                InlineKeyboardButton("• ᴜᴘᴅᴀᴛᴇᴅ •", url="https://t.me/AV_BOTz_UPDATE"),
                InlineKeyboardButton("• sᴜᴘᴘᴏʀᴛ •", url="https://t.me/AV_SUPPORT_GROUP")
            ]
        ]
        if short_link != share_link:
            buttons.insert(0, [InlineKeyboardButton("🔗 sʜᴏʀᴛᴇɴ ʟɪɴᴋ", url=short_link)])

        await editable.edit(
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )

        # ✅ Log message
        await bot.send_message(
            chat_id=LOG_CHANNEL,
            text=f"#BATCH_SAVE:\n\nUser [{owner_uid}](tg://user?id={owner_uid}) Got Batch Link!",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📂 Open Link", url=share_link)]])
        )

    except Exception:
        await editable.edit("❌ Something Went Wrong while saving batch files!")
        await bot.send_message(
            chat_id=LOG_CHANNEL,
            text=f"#ERROR_BATCH:\nChat: `{editable.chat.id}`\n\n**Traceback:**\n`{traceback.format_exc()}`"
        )


# 🔥 Save Single Media
async def save_media_in_channel(bot: Client, editable: Message, message: Message):
    try:
        copied_msg = await message.copy(DB_CHANNEL)
        file_er_id = str(copied_msg.id)

        # ✅ fallback user info
        user_name = message.from_user.first_name if message.from_user else "Unknown"
        user_id = message.from_user.id if message.from_user else 0

        await copied_msg.reply_text(
            f"#PRIVATE_FILE:\n\n[{user_name}](tg://user?id={user_id}) Got File Link!",
            disable_web_page_preview=True
        )

        # ✅ owner id
        if message.from_user:
            owner_uid = message.from_user.id
        elif message.sender_chat:
            owner_uid = message.sender_chat.id
        else:
            owner_uid = 0

        # ✅ Encode user_id + file_id
        unique_str = f"{owner_uid}:{file_er_id}"

        # ✅ Direct bot link only
        share_link = f"https://t.me/{BOT_USERNAME}?start=file_{str_to_b64(unique_str)}"

        # ✅ DB থেকে user settings
        user = await db.get_user(owner_uid)
        short_link = await db.get_short_link(user, share_link)

        # --- Message বানাও ---
        text = (
            "ʜᴇʀᴇ ɪs ʏᴏᴜʀ ꜱʜᴀʀᴀʙʟᴇ ꜰɪʟᴇ ʟɪɴᴋ❗\n\n"
            f"ᴏʀɢɪɴᴀʟ ʟɪɴᴋ: {share_link}\n"
        )
        if short_link != share_link:
            text += f"\nsʜᴏʀᴛᴇɴ ʟɪɴᴋ: {short_link}\n\n"
        else:
            text += "\n"
        text += "ᴊᴜsᴛ ᴄʟɪᴄᴋ ᴛʜᴇ ʟɪɴᴋ ᴛᴏ ɢᴇᴛ ʏᴏᴜʀ ꜰɪʟᴇ!"

        # --- Buttons বানাও ---
        buttons = [
            [InlineKeyboardButton("📂 ᴏʀɢɪɴᴀʟ ʟɪɴᴋ", url=share_link)],
            [
                InlineKeyboardButton("• ᴜᴘᴅᴀᴛᴇᴅ •", url="https://t.me/AV_BOTz_UPDATE"),
                InlineKeyboardButton("• sᴜᴘᴘᴏʀᴛ •", url="https://t.me/AV_SUPPORT_GROUP")
            ]
        ]
        if short_link != share_link:
            buttons.insert(0, [InlineKeyboardButton("🔗 sʜᴏʀᴛᴇɴ ʟɪɴᴋ", url=short_link)])

        await editable.edit(
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )

    except FloodWait as sl:
        await asyncio.sleep(sl.value)
        return await save_media_in_channel(bot, editable, message)
    except Exception:
        await editable.edit("❌ Something Went Wrong while saving file!")
        await bot.send_message(
            chat_id=LOG_CHANNEL,
            text=f"#ERROR_FILE:\nChat: `{editable.chat.id}`\n\n**Traceback:**\n`{traceback.format_exc()}`",
            disable_web_page_preview=True
                                                )
