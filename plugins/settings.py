from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from database import db   # आपकी db wrapper

# ------------------------ /settings ------------------------
@Client.on_message(filters.command("settings") & filters.private)
async def settings_command(client: Client, message: Message):
    user_id = message.from_user.id
    buttons = [
        [InlineKeyboardButton("📝 Cᴀᴘᴛɪᴏɴ Sᴇᴛᴛɪɴɢꜱ", callback_data=f"caption_setgs#{user_id}")],
        [InlineKeyboardButton("🔗 Sᴇᴛ Sʜᴏʀᴛᴇɴᴇʀ",    callback_data=f"shortlink_setgs#{user_id}")],
        [InlineKeyboardButton("✅ Vᴇʀɪғʏ Sᴇᴛᴛɪɴɢꜱ",  callback_data=f"verify_setgs#{user_id}")],
        [InlineKeyboardButton("🎬 Tᴜᴛᴏʀɪᴀʟ Sᴇᴛᴛɪɴɢꜱ",callback_data=f"tutorial_setgs#{user_id}")],
      #  [InlineKeyboardButton("⏳ Verification Time", callback_data=f"verify_time_setgs#{user_id}")],
        [InlineKeyboardButton("🛡 Pʀᴏᴛᴇᴄᴛ Sᴇᴛᴛɪɴɢꜱ", callback_data=f"update_protect_mode#{user_id}")],
        [InlineKeyboardButton("📢 Fᴏʀᴄᴇ Sᴜʙꜱᴄʀɪʙᴇ ", callback_data=f"force_channel_setgs#{user_id}")],
        [InlineKeyboardButton("📢 Lᴏɢ Cʜᴀɴɴᴇʟ",      callback_data=f"log_channel_setgs#{user_id}")],
        [InlineKeyboardButton("📑 Mʏ Dᴇᴛᴀɪʟꜱ", callback_data=f"user_details#{user_id}")]
    ]
    await message.reply_text(
        "**⚙️ ꜱᴇᴛᴛɪɴɢꜱ ᴍᴇɴᴜ:\n\nsᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴄᴜsᴛᴏᴍɪᴢᴇ ʏᴏᴜʀ ꜰɪʟᴇs sᴇᴛᴛɪɴɢs:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
  
