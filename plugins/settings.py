from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from database import db, get_db   # আপনার db wrapper

# ------------------------ /settings ------------------------
@Client.on_message(filters.command("settings") & filters.private)
async def settings_command(client: Client, message: Message):
    db = get_db(client)   # ✨ মূল বট হলে মূল db, ক্লোন হলে ক্লোনের নিজস্ব db (অব্যবহৃত হলেও
                           # ভবিষ্যতে এই ফাইলে db ব্যবহার করা কোড যোগ হলে সঠিক db-ই পাবে)
    user_id = message.from_user.id
    buttons = [
        [InlineKeyboardButton("📝 Cᴀᴘᴛɪᴏɴ Sᴇᴛᴛɪɴɢꜱ", callback_data=f"caption_setgs#{user_id}")],
        [InlineKeyboardButton("🔗 Sᴇᴛ Sʜᴏʀᴛᴇɴᴇʀ",    callback_data=f"shortlink_setgs#{user_id}")],
        [InlineKeyboardButton("✅ Vᴇʀɪғʏ Sᴇᴛᴛɪɴɢꜱ",  callback_data=f"verify_setgs#{user_id}")],
        [InlineKeyboardButton("🔗 Pᴇʀᴍᴀɴᴇɴᴛ Lɪɴᴋ", callback_data=f"permanent_link_setgs#{user_id}")],
        [InlineKeyboardButton("🎬 Tᴜᴛᴏʀɪᴀʟ Sᴇᴛᴛɪɴɢꜱ",callback_data=f"tutorial_setgs#{user_id}")],
        [InlineKeyboardButton("🛡 Pʀᴏᴛᴇᴄᴛ Sᴇᴛᴛɪɴɢꜱ", callback_data=f"update_protect_mode#{user_id}")],
        [InlineKeyboardButton("📢 Fᴏʀᴄᴇ Sᴜʙꜱᴄʀɪʙᴇ ", callback_data=f"force_channel_setgs#{user_id}")],
        [InlineKeyboardButton("📢 Lᴏɢ Cʜᴀɴɴᴇʟ",      callback_data=f"log_channel_setgs#{user_id}")],
        [InlineKeyboardButton("📑 Mʏ Dᴇᴛᴀɪʟꜱ", callback_data=f"user_details#{user_id}")]
    ]
    await message.reply_text(
        "**⚙️ ꜱᴇᴛᴛɪɴɢꜱ ᴍᴇɴᴜ:\n\nsᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴄᴜsᴛᴏᴍɪᴢᴇ ʏᴏᴜʀ ꜰɪʟᴇs sᴇᴛᴛɪɴɢs:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
