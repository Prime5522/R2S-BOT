from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
import asyncio
from config import *
from plugins.fsub import get_fsub
from utils import b64_to_str, humanbytes
from Script import script
from plugins.send_file import reply_forward_once, delete_file
from database import get_db
from plugins.verification import handle_verify_case, av_verification
from plugins.clone import build_start_content, send_clone_entry, send_start_reply_safely


async def show_clone_loading_screen(client: Client, message: Message):
    """
    ✨ ক্লোন বট থেকে ফাইল ডেলিভারির ঠিক আগে ২ সেকেন্ডের একটা ছোট্ট, প্রিমিয়াম
    লুকিং লোডিং স্ক্রিন দেখায় (Source Code বাটনসহ), তারপর নিজে থেকেই মুছে যায়।
    """
    btn = None
    if CLONE_SOURCE_CODE_URL:
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("👨‍💻 Source Code", url=CLONE_SOURCE_CODE_URL)]])

    frames = [
        "⏳ <b>Fetching your file...</b>\n▰▱▱▱▱▱▱▱▱▱ 10%",
        "⏳ <b>Fetching your file...</b>\n▰▰▰▰▰▱▱▱▱▱ 50%",
        "⏳ <b>Fetching your file...</b>\n▰▰▰▰▰▰▰▰▰▰ 100%",
    ]
    try:
        loading_msg = await message.reply_text(frames[0], reply_markup=btn)
        for frame in frames[1:]:
            await asyncio.sleep(0.7)
            try:
                await loading_msg.edit_text(frame, reply_markup=btn)
            except Exception:
                pass
        await asyncio.sleep(0.6)
        await loading_msg.delete()
    except Exception:
        pass  # লোডিং স্ক্রিন ব্যর্থ হলেও ফাইল ডেলিভারি আটকাবে না


def build_file_delivery_markup(bot: Client, base_rows: list = None):
    """
    ✨ ফাইল ডেলিভারি বাটন: ক্লোন ওনার Manage Clone প্যানেল থেকে যে বাটন(গুলো)
    সেট করেছে, সেগুলো প্রতিটা ফাইল ডেলিভারির নিচে (base_rows — যেমন main
    বটের স্ট্রিম বাটন — এর পরে) জুড়ে দেয়। কিছু সেট না থাকলে শুধু base_rows-ই যাবে।
    """
    rows = list(base_rows or [])
    custom_rows = getattr(bot, "custom_file_buttons", None) or []
    for row in custom_rows:
        btn_row = [InlineKeyboardButton(b["text"], url=b["url"]) for b in row if b.get("text") and b.get("url")]
        if btn_row:
            rows.append(btn_row)
    return InlineKeyboardMarkup(rows) if rows else None


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
        elif file_msg.photo:
            file_name = "Photo.jpg"
            file_size = humanbytes(file_msg.photo.file_size)
        else:
            file_name = "Unknown"
            file_size = "0 B"

        caption = await get_caption(cur_db, owner_uid, file_name, file_size)
        owner = await cur_db.get_user(owner_uid)
        protect = owner.get("protect_content", False)

        base_rows = [[InlineKeyboardButton('✛ Watch & Download ✛', callback_data=f'stream#{file_id}')]]
        return await bot.copy_message(
            chat_id=user_id,
            from_chat_id=DB_CHANNEL,
            message_id=file_id,
            caption=caption,
            protect_content=protect,
            reply_markup=build_file_delivery_markup(bot, base_rows)
        )

    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await media_forward(bot, user_id, file_id, owner_uid)


async def send_cached_clone_item(bot: Client, user_id: int, item: dict, owner_uid: int, cur_db):
    caption = await get_caption(cur_db, owner_uid, item.get("file_name", "File"), item.get("file_size", "0 B"))
    owner = await cur_db.get_user(owner_uid)
    protect = owner.get("protect_content", False)
    while True:
        try:
            return await bot.send_cached_media(
                chat_id=user_id,
                file_id=item["file_id"],
                caption=caption,
                protect_content=protect,
                reply_markup=build_file_delivery_markup(bot),
            )
        except FloodWait as e:
            await asyncio.sleep(e.value)


async def send_start_message(client: Client, message: Message):
    user_id = message.from_user.id
    mention = message.from_user.mention
    me2 = getattr(client, "mention", None) or (await client.get_me()).mention
    cur_db = get_db(client)

    if IS_FSUB and not getattr(client, "is_clone", False):
        if not await get_fsub(client, message, owner_uid=None):
            return

    if not await cur_db.is_user_exist(user_id):
        await cur_db.add_user(user_id, message.from_user.first_name)
        if not getattr(client, "is_clone", False):
            try:
                await client.send_message(LOG_CHANNEL, script.LOG_TEXT.format(me2, user_id, mention))
            except Exception:
                pass

    start_pic, start_pic_bytes, caption_text, reply_markup = await build_start_content(client, mention)
    return await send_start_reply_safely(client, message, start_pic, start_pic_bytes, caption_text, reply_markup)


@Client.on_message(filters.command("start") & filters.incoming)
async def start(client: Client, message: Message):

    if len(message.command) == 1:
        return await send_start_message(client, message)

    raw = message.command[1]

    if raw == "clone":
        return await send_clone_entry(client, message, is_callback=False)

    if "_" not in raw and not raw.startswith("verify-"):
        return await send_start_message(client, message)

    if raw.startswith("verify-"):
        return await handle_verify_case(client, message, raw)

    if raw.startswith("file"):
        try:
            decoded = b64_to_str(raw.split("_", 1)[1])
            parts = decoded.split(":", 1)
            if len(parts) != 2:
                return await send_start_message(client, message)

            owner_uid_str, file_id_str = parts
            owner_uid = int(owner_uid_str)

            if IS_FSUB and not await get_fsub(client, message, owner_uid=owner_uid):
                return

            verified = await av_verification(
                client,
                message,
                owner_uid=owner_uid,
                file_id=int(file_id_str) if file_id_str.isdigit() else 0,
            )
            if not verified:
                return

            cur_db = get_db(client)

            # ✨ ক্লোন বট হলে ফাইল পাঠানোর ঠিক আগে ২ সেকেন্ডের লোডিং স্ক্রিন দেখাবে
            if getattr(client, "is_clone", False):
                await show_clone_loading_screen(client, message)

            if file_id_str.startswith("c_"):
                file_doc = await cur_db.get_clone_file(file_id_str)
                if not file_doc or not file_doc.get("items"):
                    return await message.reply_text("❌ File not found or has been removed.")

                items = file_doc["items"]
                if len(items) > 1:
                    await message.reply_text(f"**📦 Total Files:** `{len(items)}`")

                sent_msgs = []
                for item in items:
                    m = await send_cached_clone_item(client, message.from_user.id, item, owner_uid, cur_db)
                    sent_msgs.append(m)

                warn_msg = await reply_forward_once(message)
                for i, m in enumerate(sent_msgs):
                    asyncio.create_task(delete_file(client, message.from_user.id, m.id, send_info=(i == 0)))
                asyncio.create_task(delete_file(client, message.from_user.id, warn_msg.id, send_info=False))
                return

            file_id = int(file_id_str)
            GetMessage = await client.get_messages(chat_id=DB_CHANNEL, message_ids=file_id)

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
                    asyncio.create_task(delete_file(client, message.from_user.id, m.id, send_info=(i == 0)))
                asyncio.create_task(delete_file(client, message.from_user.id, warn_msg.id, send_info=False))
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
