from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
import asyncio
from config import *
from plugins.fsub import get_fsub
from utils import b64_to_str, humanbytes, is_bot_staff, looks_like_link_code
from Script import script
from plugins.send_file import schedule_autodelete
from bot_commands import ensure_staff_commands
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


async def get_caption(cur_db, user_id: int, file_name: str, file_size: str,
                      user_caption: str = None, has_name: bool = True):
    """
    ফাইলের নাম থাকলে আগের মতোই (ওনারের কাস্টম টেমপ্লেট / "📂 নাম")।
    ফাইলের নাম না থাকলে (যেমন নামহীন ভিডিও/ফটো) — ইউজার লিংক বানানোর সময় যে
    ক্যাপশন দিয়েছিল সেটাই ক্যাপশন হিসেবে যাবে।
    """
    user = await cur_db.get_user(user_id)
    template = user.get("custom_caption")

    if not has_name and user_caption:
        if template:
            try:
                return template.format(file_name=user_caption, file_size=file_size)[:1024]
            except Exception:
                return user_caption[:1024]
        return user_caption[:1024]

    if template:
        try:
            return template.format(file_name=file_name, file_size=file_size)
        except Exception:
            return f"📂 {file_name}"
    return f"📂 {file_name}"


async def media_forward(bot: Client, user_id: int, file_id: int, owner_uid: int, channel_id: int = None):
    cur_db = get_db(bot)
    try:
        from_chat = channel_id or DB_CHANNEL
        file_msg = await bot.get_messages(from_chat, file_id)

        has_name = True
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
            file_name = None
            file_size = humanbytes(file_msg.photo.file_size)
        else:
            file_name = "Unknown"
            file_size = "0 B"

        if not file_name:
            has_name = False
            file_name = "Photo.jpg" if file_msg.photo else "File"

        user_caption = None
        if file_msg.caption:
            try:
                user_caption = file_msg.caption.html
            except Exception:
                user_caption = str(file_msg.caption)

        caption = await get_caption(cur_db, owner_uid, file_name, file_size, user_caption, has_name)
        owner = await cur_db.get_user(owner_uid)
        protect = owner.get("protect_content", False)

        # স্ট্রিম বাটন শুধু মূল বটের (ক্লোনের স্টোরেজ চ্যানেলে নয়)
        base_rows = [] if channel_id else [[InlineKeyboardButton('✛ Watch & Download ✛', callback_data=f'stream#{file_id}')]]
        return await bot.copy_message(
            chat_id=user_id,
            from_chat_id=from_chat,
            message_id=file_id,
            caption=caption,
            protect_content=protect,
            reply_markup=build_file_delivery_markup(bot, base_rows)
        )

    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await media_forward(bot, user_id, file_id, owner_uid, channel_id)


async def send_cached_clone_item(bot: Client, user_id: int, item: dict, owner_uid: int, cur_db):
    caption = await get_caption(
        cur_db, owner_uid,
        item.get("file_name", "File"), item.get("file_size", "0 B"),
        user_caption=item.get("caption"), has_name=item.get("has_name", True),
    )
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

    # ✨ ওনার/মডারেটর /start দিলে তার জন্য কমান্ড মেনু (ban, broadcast...) নিশ্চিত করা হয়
    if is_bot_staff(client, user_id):
        asyncio.create_task(ensure_staff_commands(client, user_id))

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


async def resolve_start_payload(cur_db, raw: str):
    """
    /start এর আর্গুমেন্ট থেকে ফাইলের তথ্য বের করে। রিটার্ন:
      {"owner_uid", "items", "db_msg_id", "payload"}  অথবা None
    নতুন লিংক  : ছোট কোড (Xk3J9aBq...)
    পুরনো লিংক : file_<base64>  — আগের শেয়ার করা সব লিংক আগের মতোই কাজ করবে
    """
    if raw.startswith("file_"):
        decoded = b64_to_str(raw.split("_", 1)[1])
        parts = decoded.split(":", 1)
        if len(parts) != 2:
            return None
        owner_uid_str, id_str = parts
        owner_uid = int(owner_uid_str)
        if id_str.startswith("c_"):
            doc = await cur_db.get_clone_file(id_str)
            if not doc or not doc.get("items"):
                return {"owner_uid": owner_uid, "items": [], "db_msg_id": None, "payload": id_str}
            return {"owner_uid": owner_uid, "items": doc["items"], "db_msg_id": None, "payload": id_str}
        if id_str.isdigit():
            return {"owner_uid": owner_uid, "items": None, "db_msg_id": int(id_str), "payload": id_str}
        return None

    if looks_like_link_code(raw):
        doc = await cur_db.get_link(raw)
        if not doc:
            return None
        return {
            "owner_uid": int(doc["owner_uid"]),
            "items": doc.get("items"),
            "db_msg_id": doc.get("db_msg_id"),
            "channel_id": doc.get("channel_id"),
            "msg_ids": doc.get("msg_ids"),
            "payload": raw,
        }
    return None


async def deliver_files(client: Client, message: Message, raw: str):
    cur_db = get_db(client)
    is_clone = getattr(client, "is_clone", False)

    target = await resolve_start_payload(cur_db, raw)
    if target is None:
        if looks_like_link_code(raw) or raw.startswith("file_"):
            return await message.reply_text("❌ File not found or has been removed.")
        return await send_start_message(client, message)

    # ক্লোন বটে সেটিংস সবসময় ক্লোনের বর্তমান ওনারের
    owner_uid = int(client.owner_id) if is_clone and getattr(client, "owner_id", None) else target["owner_uid"]

    if IS_FSUB and not await get_fsub(client, message, owner_uid=owner_uid):
        return

    verified = await av_verification(client, message, owner_uid=owner_uid, file_id=target["payload"])
    if not verified:
        return

    # ✨ ক্লোন বট হলে ফাইল পাঠানোর ঠিক আগে ২ সেকেন্ডের লোডিং স্ক্রিন দেখাবে
    if is_clone:
        await show_clone_loading_screen(client, message)

    owner_settings = await cur_db.get_user(owner_uid)
    chat_id = message.from_user.id

    # ---- ✨ ক্লোন: ওনারের স্টোরেজ চ্যানেল থেকে (বট বদলালেও লিংক বাঁচে) ----
    if target.get("msg_ids"):
        msg_ids = list(target["msg_ids"])
        if len(msg_ids) > 1:
            await message.reply_text(f"**📦 Total Files:** `{len(msg_ids)}`")
        sent_msgs = []
        try:
            for mid in msg_ids:
                m = await media_forward(client, user_id=chat_id, file_id=int(mid),
                                        owner_uid=owner_uid, channel_id=int(target["channel_id"]))
                sent_msgs.append(m)
        except Exception as e:
            print(f"[storage] delivery failed: {e!r}")
            if not sent_msgs:
                return await message.reply_text(
                    "⚠️ This file is temporarily unavailable.\nPlease contact the bot owner."
                )
        return await schedule_autodelete(client, message, sent_msgs, owner_settings)

    # ---- ক্লোন: ক্যাশ করা ফাইল আইটেম ----
    if target["items"] is not None:
        items = target["items"]
        if not items:
            return await message.reply_text("❌ File not found or has been removed.")
        if len(items) > 1:
            await message.reply_text(f"**📦 Total Files:** `{len(items)}`")

        sent_msgs = []
        for item in items:
            m = await send_cached_clone_item(client, chat_id, item, owner_uid, cur_db)
            sent_msgs.append(m)
        return await schedule_autodelete(client, message, sent_msgs, owner_settings)

    # ---- মূল বট: DB_CHANNEL থেকে ----
    file_id = int(target["db_msg_id"])
    GetMessage = await client.get_messages(chat_id=DB_CHANNEL, message_ids=file_id)

    if GetMessage.text and all(x.isdigit() for x in GetMessage.text.split()):
        message_ids = GetMessage.text.split(" ")
        await message.reply_text(f"**📦 Total Files:** `{len(message_ids)}`")

        sent_msgs = []
        for msg_id in message_ids:
            m = await media_forward(client, user_id=chat_id, file_id=int(msg_id), owner_uid=owner_uid)
            sent_msgs.append(m)
        return await schedule_autodelete(client, message, sent_msgs, owner_settings)

    sent_message = await media_forward(client, user_id=chat_id, file_id=file_id, owner_uid=owner_uid)
    await schedule_autodelete(client, message, [sent_message], owner_settings)


@Client.on_message(filters.command("start") & filters.incoming)
async def start(client: Client, message: Message):

    if len(message.command) == 1:
        return await send_start_message(client, message)

    raw = message.command[1]

    if raw == "clone":
        return await send_clone_entry(client, message, is_callback=False)

    if raw.startswith("verify-"):
        return await handle_verify_case(client, message, raw)

    try:
        return await deliver_files(client, message, raw)
    except Exception as e:
        print(f"[start] delivery error: {e!r}")
        return await send_start_message(client, message)
