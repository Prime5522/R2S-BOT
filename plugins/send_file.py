import asyncio
from config import *
from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait

async def delete_file(bot: Client, chat_id: int, msg_id: int, send_info: bool = True):
    await asyncio.sleep(300)
    try:
        await bot.delete_messages(chat_id, msg_id)
        if send_info:
            await bot.send_message(chat_id, "❌ ꜰɪʟᴇs ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ɪɴ 𝟷𝟶 ᴍɪɴᴜᴛᴇs ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛ ɪssᴜᴇs. ᴘʟᴇᴀsᴇ ғᴏʀᴡᴀʀᴅ ᴀɴᴅ sᴀᴠᴇ ᴛʜᴇᴍ. 🗑!")
    except Exception as e:
        print(f"Delete failed: {e}")

async def reply_forward_once(message: Message):
    try:
        return await message.reply_text(
            "**♻️ ꜰɪʟᴇs ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ɪɴ 𝟷𝟶 ᴍɪɴᴜᴛᴇs ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛ ɪssᴜᴇs. ᴘʟᴇᴀsᴇ ғᴏʀᴡᴀʀᴅ ᴀɴᴅ sᴀᴠᴇ ᴛʜᴇᴍ. 🗑**",
            disable_web_page_preview=True
        )
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await reply_forward_once(message)
