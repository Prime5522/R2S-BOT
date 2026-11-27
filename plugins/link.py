from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
import asyncio
from urllib.parse import quote

from config import VERIFY, HOW_TO_VERIFY, LOG_CHANNEL, DB_CHANNEL, IS_FSUB
from utils import str_to_b64, check_verification, get_token
from database import get_db
from Script import script
from plugins.fsub import get_fsub
from plugins.save_media import save_media_in_channel, extract_media_info, make_link, effective_owner
from plugins.batch import add_to_batch


@Client.on_message((filters.document | filters.video | filters.audio | filters.photo) & ~filters.chat(DB_CHANNEL))
async def main(bot: Client, message):
    db = get_db(bot)

    if message.from_user:
        user_id = message.from_user.id
        mention = message.from_user.mention
    elif message.sender_chat:
        user_id = message.sender_chat.id
        mention = message.sender_chat.title if message.sender_chat.title else "Anonymous"
    else:
        return

    me2 = getattr(bot, "mention", None) or (await bot.get_me()).mention

    if IS_FSUB and not getattr(bot, "is_clone", False):
        if not await get_fsub(bot, message, owner_uid=None):
            return

    if not await db.is_user_exist(user_id):
        await db.add_user(user_id, mention)
        if not getattr(bot, "is_clone", False):
            try:
                await bot.send_message(
                    LOG_CHANNEL,
                    script.LOG_TEXT.format(me2, user_id, mention)
                )
            except Exception:
                pass

    if message.chat.type == enums.ChatType.PRIVATE:
        # ✨ আর কোনো "Batch / Direct" অপশন আসে না:
        #   • /batch চালু থাকলে → ব্যাচে যোগ হবে
        #   • নইলে → সাথে সাথে ডাইরেক্ট লিংক
        user = await db.get_user(user_id)
        if user.get("batch_mode"):
            return await add_to_batch(bot, message, db, user_id)

        editable = await message.reply_text("⏳ Generating your link...", quote=True)
        await save_media_in_channel(bot, editable, message)
        try:
            await message.delete()
        except Exception:
            pass

    elif message.chat.type == enums.ChatType.CHANNEL:
        if message.forward_from_chat or message.forward_from:
            return

        try:
            uploader_uid = message.from_user.id if message.from_user else (message.sender_chat.id if message.sender_chat else 0)
            owner_uid = effective_owner(bot, uploader_uid)
            bot_username = getattr(bot, "username", None) or (await bot.get_me()).username

            if getattr(bot, "is_clone", False):
                info = extract_media_info(message)
                if not info:
                    return
                code = await db.create_link(owner_uid, items=[info])
            else:
                forwarded_msg = await message.forward(DB_CHANNEL)
                code = await db.create_link(owner_uid, db_msg_id=forwarded_msg.id)

            share_link = make_link(bot_username, code)

            await bot.edit_message_reply_markup(
                message.chat.id,
                message.id,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Get Shareable Link", url=share_link)],
                    [InlineKeyboardButton("📤 Share", url=f"https://t.me/share/url?url={quote(share_link, safe='')}")],
                ])
            )

        except Exception as err:
            print(f"Error while processing channel message: {err}")
