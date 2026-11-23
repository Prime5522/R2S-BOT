"""
✨ /batch সিস্টেম
- ফাইল সরাসরি পাঠালে → সাথে সাথে ডাইরেক্ট লিংক (কোনো অপশন আসে না)।
- /batch দিলে ব্যাচ মোড চালু → একাধিক ফাইল পাঠান → /done বা বাটনে একটাই ব্যাচ লিংক।
"""
import asyncio

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import get_db
from plugins.save_media import save_batch_media_in_channel, effective_owner


def batch_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Get Batch Link", callback_data="getBatchLink")],
        [InlineKeyboardButton("❌ Cancel Batch", callback_data="batch_cancel")],
    ])


async def add_to_batch(bot: Client, message: Message, cur_db, user_id: int):
    """ব্যাচ মোডে একটা ফাইল যোগ করে এবং স্ট্যাটাস মেসেজ আপডেট করে"""
    await cur_db.add_media(user_id, message.id)
    await cur_db.add_user_file(user_id, message.id)
    count = len(await cur_db.get_media(user_id))

    user = await cur_db.get_user(user_id)
    old_status = user.get("batch_status_id")
    if old_status:
        try:
            await bot.delete_messages(message.chat.id, old_status)
        except Exception:
            pass

    status = await message.reply_text(
        f"✅ <b>File added to batch!</b>\n\n📦 Total files: <code>{count}</code>\n\n"
        "Send more files, or tap the button below (or send /done) to get your link.",
        reply_markup=batch_markup(),
        quote=True,
    )
    await cur_db.update_user_info(user_id, {"batch_status_id": status.id})


async def finish_batch(client: Client, user_id: int, chat_id: int) -> bool:
    cur_db = get_db(client)
    ids = await cur_db.get_media(user_id)
    if not ids:
        return False

    user = await cur_db.get_user(user_id)
    status_id = user.get("batch_status_id")
    file_msg_ids = list(await cur_db.get_user_files(user_id))

    editable = await client.send_message(chat_id, "⏳ Please wait, generating batch link...")
    await save_batch_media_in_channel(
        bot=client,
        editable=editable,
        message_ids=ids,
        owner_uid=effective_owner(client, user_id),
    )
    await cur_db.clear_media(user_id)
    await cur_db.clear_user_files(user_id)
    await cur_db.update_user_info(user_id, {"batch_mode": False, "batch_status_id": None})

    async def cleanup():
        # আগের মতোই: লিংক হওয়ার ৩০ সেকেন্ড পর ইউজারের পাঠানো ফাইল ও স্ট্যাটাস মেসেজ মুছে যায়
        await asyncio.sleep(30)
        to_delete = list(file_msg_ids)
        if status_id:
            to_delete.append(status_id)
        for mid in to_delete:
            try:
                await client.delete_messages(chat_id, mid)
            except Exception:
                pass

    asyncio.create_task(cleanup())
    return True


@Client.on_message(filters.command("batch") & filters.private)
async def batch_command(client: Client, message: Message):
    user_id = message.from_user.id
    cur_db = get_db(client)
    if not await cur_db.is_user_exist(user_id):
        await cur_db.add_user(user_id, message.from_user.first_name)

    await cur_db.clear_media(user_id)
    await cur_db.clear_user_files(user_id)
    await cur_db.update_user_info(user_id, {"batch_mode": True, "batch_status_id": None})

    await message.reply_text(
        "📦 <b>Batch Mode ON</b>\n\n"
        "Now send me all the files you want in <b>one</b> link (documents, videos, audios, photos).\n\n"
        "When you're finished, send /done — or tap the button that appears under the last file.\n"
        "Send /cancel to cancel.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Batch", callback_data="batch_cancel")]]),
    )


@Client.on_message(filters.command("done") & filters.private)
async def batch_done_command(client: Client, message: Message):
    user_id = message.from_user.id
    cur_db = get_db(client)
    user = await cur_db.get_user(user_id)
    if not user.get("batch_mode"):
        return await message.reply_text("⚠️ You're not in batch mode. Send /batch first, then your files.")
    if not await finish_batch(client, user_id, message.chat.id):
        return await message.reply_text("⚠️ You haven't added any files yet. Send some files first.")


@Client.on_message(filters.command("cancel") & filters.private)
async def batch_cancel_command(client: Client, message: Message):
    # ইনপুট-পেন্ডিং থাকলে clone.py-র হ্যান্ডলার আগেই ধরে নেয়; এখানে শুধু ব্যাচ বাতিল
    user_id = message.from_user.id
    cur_db = get_db(client)
    user = await cur_db.get_user(user_id)
    if not user.get("batch_mode"):
        return
    await _cancel_batch(client, cur_db, user_id, message.chat.id)
    await message.reply_text("❌ Batch cancelled.")


async def _cancel_batch(client, cur_db, user_id: int, chat_id: int):
    user = await cur_db.get_user(user_id)
    status_id = user.get("batch_status_id")
    await cur_db.clear_media(user_id)
    await cur_db.clear_user_files(user_id)
    await cur_db.update_user_info(user_id, {"batch_mode": False, "batch_status_id": None})
    if status_id:
        try:
            await client.delete_messages(chat_id, status_id)
        except Exception:
            pass


# group=-1 + stop_propagation: callback.py-র সাধারণ হ্যান্ডলারের আগে এগুলো ধরা পড়ে
@Client.on_callback_query(filters.regex(r"^getBatchLink$"), group=-1)
async def get_batch_link_cb(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    cur_db = get_db(client)
    if not await cur_db.get_media(user_id):
        await query.answer("⚠️ Batch list is empty!", show_alert=True)
        return query.stop_propagation()
    await query.answer()
    await finish_batch(client, user_id, query.message.chat.id)
    query.stop_propagation()


@Client.on_callback_query(filters.regex(r"^batch_cancel$"), group=-1)
async def batch_cancel_cb(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    cur_db = get_db(client)
    await _cancel_batch(client, cur_db, user_id, query.message.chat.id)
    await query.answer("❌ Batch cancelled")
    try:
        await query.message.edit_text("❌ Batch cancelled.")
    except Exception:
        pass
    query.stop_propagation()
  
