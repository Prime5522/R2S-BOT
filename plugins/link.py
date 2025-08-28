from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
import asyncio

from config import BOT_USERNAME, VERIFY, HOW_TO_VERIFY, LOG_CHANNEL, DB_CHANNEL, IS_FSUB
from utils import str_to_b64, check_verification, get_token
from database import db
from Script import script
from plugins.fsub import get_fsub


async def av_verification(client, message, owner_uid: int = None):
    user_id = message.from_user.id
    
    owner = await db.get_user(owner_uid)
    download = owner.get("how_to_download", HOW_TO_VERIFY)
    verify = owner.get("verify", VERIFY)

    if verify and not await check_verification(client, user_id):
        btn = [[
            InlineKeyboardButton(
                "✅️ ᴠᴇʀɪғʏ ✅️",
                url=await get_token(client, user_id, f"https://t.me/{BOT_USERNAME}?start=")
            ),
            InlineKeyboardButton("⁉️ ʜᴏᴡ ᴛᴏ ᴠᴇʀɪғʏ ⁉️", url=download)
        ]]

        d = await message.reply_text(
            text=script.VERIFICATION_TEXT.format(message.from_user.mention),
            protect_content=False,
            reply_markup=InlineKeyboardMarkup(btn),
            disable_web_page_preview=True,
            parse_mode=ParseMode.HTML
        )
        
        # 10 min बाद msg delete हो जाएगा
        await asyncio.sleep(600)
        try:
            await d.delete()
            await message.delete()
        except:
            pass
        return False

    return True
    

@Client.on_message((filters.document | filters.video | filters.audio) & ~filters.chat(DB_CHANNEL))
async def main(bot: Client, message):
    user_id = message.from_user.id
    mention = message.from_user.mention
    me2 = (await bot.get_me()).mention

    # FSUB check
    if IS_FSUB and not await get_fsub(bot, message, owner_uid=None):
        return

    # अगर user DB में नहीं है तो add करो
    if not await db.is_user_exist(user_id):
        await db.add_user(user_id, message.from_user.first_name)
        await bot.send_message(LOG_CHANNEL, script.LOG_TEXT.format(me2, user_id, mention))

    # Private Chat
    if message.chat.type == enums.ChatType.PRIVATE:
        await message.reply_text(
            "**ᴄʜᴏᴏsᴇ ᴀɴ ᴏᴘᴛɪᴏɴ ꜰʀᴏᴍ ʙᴇʟᴏᴡ :**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("ꜱᴀᴠᴇ ɪɴ ʙᴀᴛᴄʜ", callback_data="addToBatchTrue")],
                [InlineKeyboardButton("ɢᴇᴛ ꜱʜᴀʀᴀʙʟᴇ ʟɪɴᴋ", callback_data="addToBatchFalse")]
            ]),
            quote=True,
            disable_web_page_preview=True
        )

    # Channel
    elif message.chat.type == enums.ChatType.CHANNEL:
        # अगर forward किया हुआ msg है तो ignore
        if message.forward_from_chat or message.forward_from:
            return

        try:
            # DB_CHANNEL में forward
            forwarded_msg = await message.forward(DB_CHANNEL)
            file_er_id = str(forwarded_msg.id)

            # ✅ user id सुरक्षित तरीके से निकालें (channel/anonymous के लिए fallback)
            if message.from_user:
                owner_uid = message.from_user.id
            elif message.sender_chat:
                owner_uid = message.sender_chat.id  # channel या anonymous sender
            else:
                owner_uid = 0  # अंतिम fallback, ताकि code कभी crash न हो

            # ✅ user_id + file_id को base64 में छिपाएँ
            unique_str = f"{owner_uid}:{file_er_id}"
            share_link = f"https://t.me/{BOT_USERNAME}?start=_{str_to_b64(unique_str)}"

            await bot.edit_message_reply_markup(
                message.chat.id,
                message.id,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("ɢᴇᴛ ꜱʜᴀʀᴀʙʟᴇ ʟɪɴᴋ", url=share_link)]]
                )
            )

        except Exception as err:
            print(f"Error: {err}")
