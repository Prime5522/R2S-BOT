from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
import asyncio
from config import *
from plugins.fsub import get_fsub
from utils import b64_to_str, humanbytes
from Script import script
from plugins.send_file import reply_forward_once, delete_file
from database import db, get_db
from plugins.verification import handle_verify_case, av_verification
from plugins.clone import build_start_content, send_clone_entry


# ---- Get Caption (per owner) ----
async def get_caption(cur_db, user_id: int, file_name: str, file_size: str):
    user = await cur_db.get_user(user_id)
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
    cur_db = get_db(bot)
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

        caption = await get_caption(cur_db, owner_uid, file_name, file_size)
        owner = await cur_db.get_user(owner_uid)
        protect = owner.get("protect_content", False)

        return await bot.copy_message(
            chat_id=user_id,
            from_chat_id=DB_CHANNEL,
            message_id=file_id,
            caption=caption,
            protect_content=protect,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton('✛ Watch & Download ✛', callback_data=f'stream#{file_id}')]]
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
    cur_db = get_db(client)

    if IS_FSUB and not await get_fsub(client, message, owner_uid=None):
        return

    if not await cur_db.is_user_exist(user_id):
        await cur_db.add_user(user_id, message.from_user.first_name)
        try:
            await client.send_message(LOG_CHANNEL, script.LOG_TEXT.format(me2, user_id, mention))
        except Exception:
            pass

    start_pic, caption_text, reply_markup = await build_start_content(client, mention)

    if start_pic:
        return await message.reply_photo(
            photo=start_pic,
            caption=caption_text,
            reply_markup=reply_markup
        )

    return await message.reply_text(
        text=caption_text,
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )


# ---- /start Command ----
@Client.on_message(filters.command("start") & filters.incoming)
async def start(client: Client, message: Message):

    # Case 1: Normal /start
    if len(message.command) == 1:
        return await send_start_message(client, message)

    raw = message.command[1]

    # Deep-link: /start clone
    if raw == "clone":
        return await send_clone_entry(client, message, is_callback=False)

    # Normal start if no payload format matched
    if "_" not in raw and not raw.startswith("verify-"):
        return await send_start_message(client, message)

    # Case 2: Verification
    if raw.startswith("verify-"):
        return await handle_verify_case(client, message, raw)

    # Case 3: File Access
    if raw.startswith("file"):
        try:
            decoded = b64_to_str(raw.split("_", 1)[1])  # uid:fileid
            parts = decoded.split(":")
            if len(parts) != 2:
                return await send_start_message(client, message)

            owner_uid, file_id = parts
            owner_uid = int(owner_uid)
            file_id = int(file_id)

            if IS_FSUB and not await get_fsub(client, message, owner_uid=owner_uid):
                return

            verified = await av_verification(client, message, owner_uid=owner_uid, file_id=file_id)
            if not verified:
                return

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
