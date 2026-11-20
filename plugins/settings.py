from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from config import MAIN_BOT_USERNAME
from database import get_db


# ------------------------ /settings ------------------------
@Client.on_message(filters.command("settings") & filters.private)
async def settings_command(client: Client, message: Message):
    if getattr(client, "is_clone", False):
        text = (
            "<b>⚙️ Bot Settings & Customization</b>\n\n"
            "You can manage your clone bot's settings (Start Message, Start Picture, Custom Buttons, Caption, Shortener, Verify, Force Subscribe, Log Channel, and more) from our main bot.\n\n"
            "👇 Click the button below to open the Clone Settings panel:"
        )
        buttons = [
            [
                InlineKeyboardButton(
                    "⚙️ Open Clone Settings",
                    url=f"https://t.me/{MAIN_BOT_USERNAME}?start=clone",
                )
            ]
        ]
        return await message.reply_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True,
        )

    _ = get_db(client)
    user_id = message.from_user.id
    buttons = [
        [InlineKeyboardButton("📝 Caption Settings", callback_data=f"caption_setgs#{user_id}")],
        [InlineKeyboardButton("🔗 Set Shortener", callback_data=f"shortlink_setgs#{user_id}")],
        [InlineKeyboardButton("✅ Verify Settings", callback_data=f"verify_setgs#{user_id}")],
        [InlineKeyboardButton("🔗 Permanent Link", callback_data=f"permanent_link_setgs#{user_id}")],
        [InlineKeyboardButton("🎬 Tutorial Settings", callback_data=f"tutorial_setgs#{user_id}")],
        [InlineKeyboardButton("🛡 Protect Settings", callback_data=f"update_protect_mode#{user_id}")],
        [InlineKeyboardButton("📢 Force Subscribe", callback_data=f"force_channel_setgs#{user_id}")],
        [InlineKeyboardButton("📢 Log Channel", callback_data=f"log_channel_setgs#{user_id}")],
        [InlineKeyboardButton("📑 My Details", callback_data=f"user_details#{user_id}")],
    ]
    await message.reply_text(
        "<b>⚙️ Settings Menu</b>\n\nSelect an option below to customize your file settings:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
