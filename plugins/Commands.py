from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
import asyncio, pytz
from datetime import datetime
from config import *
from plugins.fsub import get_fsub
from utils import b64_to_str, humanbytes
from Script import script
from plugins.send_file import reply_forward_once, delete_file
from database import db
from plugins.verification import handle_verify_case, av_verification   # ✅ new verification handler


# ---- Get Caption (owner ke hisaab se) ----
async def get_caption(user_id: int, file_name: str, file_size: str):
    user = await db.get_user(user_id)
    caption = user.get("custom_caption")

    if caption:
        try:
            return caption.format(file_name=file_name, file_size=file_size)
        except Exception:
            return f"📂 {file_name}"
    else:
        return f"📂 {file_name}"


# ---- Forward/Copy File ----
async def media_forward(bot: Client, user_id: int, file_id: int, owner_uid: int):
    try:
        file_msg = await bot.get_messages(DB_CHANNEL, file_id)

        if file_msg.document:
            file_name = file_msg.document.file_name
            file_size = humanbytes(file_msg.document.file_size)
        elif file_msg.video:
            file_name = file_msg.video.file_name
            file_size = humanbytes(file_msg.video.file_size)
        elif file_msg.audio:
            file_name = file_msg.audio.file_name
            file_size = humanbytes(file_msg.audio.file_size)
        else:
            file_name = "Unknown"
            file_size = "0 B"

        # ✅ Always take caption & protect_content from file OWNER
        caption = await get_caption(owner_uid, file_name, file_size)
        owner = await db.get_user(owner_uid)
        protect = owner.get("protect_content", False)

        return await bot.copy_message(
            chat_id=user_id,
            from_chat_id=DB_CHANNEL,
            message_id=file_id,
            caption=caption,
            protect_content=protect,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton('✛ ᴡᴀᴛᴄʜ & ᴅᴏᴡɴʟᴏᴀᴅ ✛', callback_data=f'stream#{file_id}')]]
            )
        )

    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await media_forward(bot, user_id, file_id, owner_uid)


# ---- Helper: Start Message ----
async def send_start_message(client: Client, message: Message):
    user_id = message.from_user.id
    mention = message.from_user.mention
    me2 = (await client.get_me()).mention

    if IS_FSUB and not await get_fsub(client, message, owner_uid=None):
        return

    if not await db.is_user_exist(user_id):
        await db.add_user(user_id, message.from_user.first_name)
        await client.send_message(LOG_CHANNEL, script.LOG_TEXT.format(me2, user_id, mention))

    buttons = [
        [
            InlineKeyboardButton("• ᴜᴘᴅᴀᴛᴇᴅ •", url="https://t.me/AV_BOTz_UPDATE"),
                InlineKeyboardButton("• sᴜᴘᴘᴏʀᴛ •", url="https://t.me/AV_SUPPORT_GROUP")
        ],[
            InlineKeyboardButton('• ʜᴇʟᴘ •', callback_data='help'),
            InlineKeyboardButton('• ᴀʙᴏᴜᴛ •', callback_data='about')
        ]
    ]

    return await message.reply_photo(
        photo=PICS,
        caption=script.START_TXT.format(message.from_user.mention, me2),
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ---- /start Command ----
@Client.on_message(filters.command("start") & filters.incoming)
async def start(client: Client, message: Message):

    # ✅ Case 1: Normal /start
    if len(message.command) == 1:
        return await send_start_message(client, message)

    raw = message.command[1]

    # Agar "_" hi nahi hai → normal start msg
    if "_" not in raw and not raw.startswith("verify-"):
        return await send_start_message(client, message)

    # ✅ Case 2: Verification
    if raw.startswith("verify-"):
        return await handle_verify_case(client, message, raw)

    # ✅ Case 3: File Access
    if raw.startswith("file"):
        try:
            decoded = b64_to_str(raw.split("_", 1)[1])  # uid:fileid
            parts = decoded.split(":")
            if len(parts) != 2:
                return await send_start_message(client, message)

            owner_uid, file_id = parts
            owner_uid = int(owner_uid)
            file_id = int(file_id)

            # Owner ke FSUB channels check karo
            if IS_FSUB and not await get_fsub(client, message, owner_uid=owner_uid):
                return

            # Verification check (अगर जरूरी है तो)
            verified = await av_verification(client, message, owner_uid=owner_uid, file_id=file_id)
            if not verified:
                return

            # DB_CHANNEL se message lo
            GetMessage = await client.get_messages(chat_id=DB_CHANNEL, message_ids=file_id)

            # --- Batch Case ---
            if GetMessage.text and all(x.isdigit() for x in GetMessage.text.split()):
                message_ids = GetMessage.text.split(" ")
                await message.reply_text(f"**📦 Total Files:** `{len(message_ids)}`")

                sent_msgs = []
                for msg_id in message_ids:
                    m = await media_forward(
                        client,
                        user_id=message.from_user.id,
                        file_id=int(msg_id),
                        owner_uid=owner_uid
                    )
                    sent_msgs.append(m)

                warn_msg = await reply_forward_once(message)

                for i, m in enumerate(sent_msgs):
                    send_info = True if i == 0 else False
                    asyncio.create_task(delete_file(client, message.from_user.id, m.id, send_info=send_info))
                asyncio.create_task(delete_file(client, message.from_user.id, warn_msg.id, send_info=False))

            # --- Single File Case ---
            else:
                sent_message = await media_forward(
                    client,
                    user_id=message.from_user.id,
                    file_id=file_id,
                    owner_uid=owner_uid
                )
                warn_msg = await reply_forward_once(message)

                asyncio.create_task(delete_file(client, message.from_user.id, sent_message.id, send_info=True))
                asyncio.create_task(delete_file(client, message.from_user.id, warn_msg.id, send_info=False))

        except Exception:
            return await send_start_message(client, message)
