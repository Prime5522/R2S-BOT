import asyncio, time
from pyrogram import Client, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from config import *
from utils import get_hash
from Script import script
from plugins.save_media import save_batch_media_in_channel, save_media_in_channel
from database import db
from shortzy import Shortzy

MediaList = {}
ConfirmMsgs = {}
UserFiles = {}

async def safe_send_cached_media(client, chat_id, file_id):
    while True:
        try:
            return await client.send_cached_media(chat_id=chat_id, file_id=file_id)
        except FloodWait as e:
            await asyncio.sleep(e.value)

# ==== Helper: get real Telegram file_id from message_id ====
async def get_real_file_id(client, msg_id):
    msg = await client.get_messages(DB_CHANNEL, msg_id)
    media = msg.document or msg.video or msg.audio or msg.photo
    if not media:
        return None
    return media.file_id

@Client.on_callback_query()
async def cb_handler(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
  
    if query.data == "close_data":
        await query.message.delete()
        
    elif query.data == "about":
        buttons = [[
	    InlineKeyboardButton('• ʜᴏᴍᴇ •', callback_data='start'),
	    InlineKeyboardButton('• ᴄʟᴏsᴇ •', callback_data='close_data')
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        me2 = (await client.get_me()).mention
        await query.message.edit_text(
            text=script.ABOUT_TXT.format(me2, me2),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
    
    elif query.data == "start":
        buttons = [[
            InlineKeyboardButton("• ᴜᴘᴅᴀᴛᴇᴅ •", url="https://t.me/PrimeXBots"),
                InlineKeyboardButton("• sᴜᴘᴘᴏʀᴛ •", url="https://t.me/Prime_Support_group")
        ],[
            InlineKeyboardButton('• ʜᴇʟᴘ •', callback_data='help'),
            InlineKeyboardButton('• ᴀʙᴏᴜᴛ •', callback_data='about')
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_text(
            text=script.START_TXT.format(query.from_user.mention),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
	    )
	    
    elif query.data == "help":
        buttons = [[
	    InlineKeyboardButton('• ʜᴏᴍᴇ •', callback_data='start'),
	    InlineKeyboardButton('• ᴄʟᴏsᴇ •', callback_data='close_data')
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_text(
            text=script.HELP_TXT,
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )     

    elif query.data.startswith("stream"):
        msg_id = int(query.data.split('#', 1)[1])  # ये है message_id

        try:
            msg = await client.get_messages(DB_CHANNEL, msg_id)
            if not msg:
                return await query.answer("⚠️ File not found!", show_alert=True)
        except Exception:
            return await query.answer("⚠️ Invalid file!", show_alert=True)

        real_file_id = await get_real_file_id(client, msg_id)
        if not real_file_id:
            return await query.answer("⚠️ Media not found!", show_alert=True)

        AKS = await safe_send_cached_media(client, BIN_CHANNEL, real_file_id)

        file_hash = get_hash(AKS)
        online = f"{URL}/watch/{AKS.id}/AV_File_{int(time.time())}.mkv?hash={file_hash}"
        download = f"{URL}/{AKS.id}?hash={file_hash}"

        btn = [
                [
                    InlineKeyboardButton("▶ ᴡᴀᴛᴄʜ ᴏɴʟɪɴᴇ", url=online),
                    InlineKeyboardButton("⬇ ꜰᴀsᴛ ᴅᴏᴡɴʟᴏᴀᴅ", url=download)
                ],
                [InlineKeyboardButton('❌ ᴄʟᴏsᴇ ❌', callback_data='close_data')]
        ]

        return await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(btn)
		)

    elif query.data == "addToBatchTrue":
        file_msg_id = query.message.reply_to_message.id
        await db.add_media(user_id, file_msg_id)
        await db.add_user_file(user_id, file_msg_id)
        confirm = await query.message.edit(
            "✅ ꜰɪʟᴇ sᴀᴠᴇᴅ ɪɴ ʙᴀᴛᴄʜ!\n\nᴘʀᴇss ʙᴇʟᴏᴡ ʙᴜᴛᴛᴏɴ ᴛᴏ ɢᴇᴛ ʙᴀᴛᴄʜ ʟɪɴᴋ..",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📦 Gᴇᴛ Bᴀᴛᴄʜ Lɪɴᴋ", callback_data="getBatchLink")],
                [InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data='close_data')]
            ])
        )
        await db.add_confirm_msg(user_id, confirm.id)
        return

    elif query.data == "getBatchLink":
        message_ids = await db.get_media(user_id)
        if not message_ids:
            return await query.answer("⚠️ Bᴀᴛᴄʜ Lɪꜱᴛ Eᴍᴘᴛʏ!", show_alert=True)
        editable = await client.send_message(
            chat_id=query.message.chat.id,
            text="⏳ ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ɢᴇɴᴇʀᴀᴛɪɴɢ ʙᴀᴛᴄʜ ʟɪɴᴋ..."
        )
        await save_batch_media_in_channel(
            bot=client,
            editable=editable,
            message_ids=message_ids,
            owner_uid=user_id
        )
        await db.clear_media(user_id)
        async def delete_later():
            await asyncio.sleep(30)
            for msg_id in await db.get_confirm_msgs(user_id):
                try: await client.delete_messages(chat_id=query.message.chat.id, message_ids=msg_id)
                except: pass
            await db.clear_confirm_msgs(user_id)
            for msg_id in await db.get_user_files(user_id):
                try: await client.delete_messages(chat_id=query.message.chat.id, message_ids=msg_id)
                except: pass
            await db.clear_user_files(user_id)
        asyncio.create_task(delete_later())
        return
		
    elif query.data == "addToBatchFalse":
        await save_media_in_channel(
            bot=client,
            message=query.message.reply_to_message,
            editable=query.message
		)
        if query.message.reply_to_message:
            await query.message.reply_to_message.delete()
        return
		
    elif query.data.startswith("user_reset"):
        await db.reset_user(int(user_id))
        await query.answer("✅ Yᴏᴜʀ ꜱᴇᴛᴛɪɴɢꜱ ʜᴀᴠᴇ ʙᴇᴇɴ ʀᴇꜱᴇᴛ ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ.", show_alert=True)
        buttons = [[InlineKeyboardButton("≼ ʙᴀᴄᴋ", callback_data=f"user_details#{user_id}")]]
        await query.message.edit_text(
            "⚙️ ᴀʟʟ ʏᴏᴜʀ ᴜsᴇʀ ᴅᴀᴛᴀ ʜᴀꜱ ʙᴇᴇɴ ʀᴇsᴇᴛ.!\n\nʏᴏᴜ ᴄᴀɴ ɴᴏᴡ ꜰʀᴇsʜʟʏ ᴜꜱᴇ ᴛʜᴇ ʙᴏᴛ.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
		
    elif query.data.startswith("user_details"):
        user = await db.get_user(int(user_id))
        shortener_api = user.get("shortener_api") or "ɴᴏᴛ sᴇᴛ"
        base_site = user.get("base_site") or "ɴᴏᴛ sᴇᴛ"
        custom_caption = user.get("custom_caption") or "ɴᴏᴛ sᴇᴛ"
        verify_api = user.get("verify_api") or "ɴᴏᴛ sᴇᴛ"
        verify_site = user.get("verify_site") or "ɴᴏᴛ sᴇᴛ"
        verify_expire = user.get("verify_expire") or "ɴᴏᴛ sᴇᴛ"
        how_to_download = user.get("how_to_download") or "ɴᴏᴛ sᴇᴛ"
        verify = "✅ True" if user.get("verify") else "❌ False"
        log_channel = user.get("log_channel") or "ɴᴏᴛ sᴇᴛ"
        fsub_channels = user.get("fsub_channels") or []
        protect_content = "✅ True" if user.get("protect_content") else "❌ False"
        text = (
            "⚙️ ** ʏᴏᴜʀ sᴇᴛᴛɪɴɢs ꜰᴏʀ ꜰɪʟᴇ sᴛᴏʀᴇ\n\n"
            f"✅️  ᴠᴇʀɪꜰʏ sʜᴏʀᴛɴᴇʀ ɴᴀᴍᴇ/ᴀᴘɪ\n"
            f"ɴᴀᴍᴇ - {verify_site}\n"
            f"ᴀᴘɪ - {verify_api}\n\n"
            f"✅ sʜᴏʀᴛɴᴇʀ ɴᴀᴍᴇ/ᴀᴘɪ\n"
            f"ɴᴀᴍᴇ - {base_site}\n"
            f"ᴀᴘɪ - {shortener_api}\n\n"
            f"🧭 ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ - {verify_expire}\n\n"
            f"📘 ᴠᴇʀɪꜰʏ - {verify}\n\n"
            f"⚡ ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ - {how_to_download}\n\n"
            f"⭕️ ᴘʀᴏᴛᴇᴄᴛ ᴄᴏɴᴛᴇɴᴛ - {protect_content}\n\n"
            f"🧾 ꜰ-sᴜʙ ᴄʜᴀɴɴᴇʟ - {', '.join([str(ch) for ch in fsub_channels]) if fsub_channels else 'ɴᴏᴛ sᴇᴛ'}\n\n"
            f"📜 ʟᴏɢ ᴄʜᴀɴɴᴇʟ - {log_channel}\n\n"
            f"📝 ᴄᴀᴘᴛɪᴏɴ - {custom_caption}\n"
        )
        btn = [
            [InlineKeyboardButton("♻ Rᴇꜱᴇᴛ Sᴇᴛᴛɪɴɢꜱ", callback_data=f"user_reset#{user_id}")],
            [InlineKeyboardButton("≼ ʙᴀᴄᴋ", callback_data=f"settings#{user_id}")]
        ]
        await query.message.edit(text, reply_markup=InlineKeyboardMarkup(btn))

    # ------------------- START OF NEW CODE BLOCK -------------------
    elif query.data.startswith("permanent_link_setgs"):
        _, user_id = query.data.split("#")
        user = await db.get_user(int(user_id))
        is_on = user.get("permanent_link_mode", True)
        text = (
            "**🔗 Pᴇʀᴍᴀɴᴇɴᴛ Lɪɴᴋ Sᴇᴛᴛɪɴɢꜱ**\n\n"
            "এই মোডটি চালু থাকলে, আপনার ফাইল লিঙ্কে Vercel/Website URL ব্যবহার করা হবে (যেমন: `https://.../file_id...`), যা একটি ওয়েব পেজ দেখাবে।\n\n"
            "এটি বন্ধ থাকলে, সরাসরি টেলিগ্রামের `t.me` লিঙ্ক তৈরি হবে, যা ব্যবহারকারীকে সরাসরি আপনার বটে নিয়ে আসবে।\n\n"
            f"**ᴄᴜʀʀᴇɴᴛ sᴛᴀᴛᴜs:** `{'ON ✅' if is_on else 'OFF ❌'}`"
        )
        buttons = [
            [InlineKeyboardButton(f"ᴛᴜʀɴ {'OFF ❌' if is_on else 'ON ✅'}", callback_data=f"toggle_permanent_link#{user_id}#{is_on}")],
            [InlineKeyboardButton("≼ ʙᴀᴄᴋ", callback_data=f"settings#{user_id}")]
        ]
        await query.message.edit(text, reply_markup=InlineKeyboardMarkup(buttons))

    elif query.data.startswith("toggle_permanent_link"):
        _, user_id, status = query.data.split("#")
        new_status = False if status == 'True' else True
        await db.update_user_info(int(user_id), {"permanent_link_mode": new_status})
        user = await db.get_user(int(user_id))
        is_on = user.get("permanent_link_mode", True)
        text = (
            "**🔗 Pᴇʀᴍᴀɴᴇɴᴛ Lɪɴᴋ Sᴇᴛᴛɪɴɢꜱ**\n\n"
            "এই মোডটি চালু থাকলে, আপনার ফাইল লিঙ্কে Vercel/Website URL ব্যবহার করা হবে (যেমন: `https://.../file_id...`), যা একটি ওয়েব পেজ দেখাবে।\n\n"
            "এটি বন্ধ থাকলে, সরাসরি টেলিগ্রামের `t.me` লিঙ্ক তৈরি হবে, যা ব্যবহারকারীকে সরাসরি আপনার বটে নিয়ে আসবে।\n\n"
            f"**ᴄᴜʀʀᴇɴᴛ sᴛᴀᴛᴜs:** `{'ON ✅' if is_on else 'OFF ❌'}`"
        )
        buttons = [
            [InlineKeyboardButton(f"ᴛᴜʀɴ {'OFF ❌' if is_on else 'ON ✅'}", callback_data=f"toggle_permanent_link#{user_id}#{is_on}")],
            [InlineKeyboardButton("≼ ʙᴀᴄᴋ", callback_data=f"settings#{user_id}")]
        ]
        await query.message.edit(text, reply_markup=InlineKeyboardMarkup(buttons))
        await query.answer(f"✅ Permanent Link mode is now {'ON' if is_on else 'OFF'}")
    # -------------------- END OF NEW CODE BLOCK --------------------
		
    elif query.data.startswith("force_channel_setgs"):
        _, user_id = query.data.split("#")
        settings = await db.get_user(int(user_id))
        btn = [[
            InlineKeyboardButton('sᴇᴛ ᴄʜᴀɴɴᴇʟ ', callback_data=f'set_force_channel#{user_id}'),
            InlineKeyboardButton('ᴅᴇʟᴇᴛᴇ ᴄʜᴀɴɴᴇʟ', callback_data=f'force_channel_delete#{user_id}')
        ],[
            InlineKeyboardButton('≼ ʙᴀᴄᴋ', callback_data=f'settings#{user_id}')
        ]]
        channels = settings.get("fsub_channels", [])
        if not channels:
            channel = "ʏᴏᴜ ᴅɪᴅɴ'ᴛ ᴀᴅᴅᴇᴅ ᴀɴʏ ꜰᴏʀᴄᴇ sᴜʙsᴄʀɪʙᴇ ᴄʜᴀɴɴᴇʟ..."
        else:
            try:
                chat_titles = []
                for ch in channels:
                    chat = await client.get_chat(ch)
                    chat_titles.append(f"<b>{chat.title}</b> (<code>{ch}</code>)")
                channel = "Force Channels:\n" + "\n".join(chat_titles)
            except Exception as e:
                channel = f"⚠️ Error fetching channels: <code>{e}</code>"
        await query.message.edit(
            f"ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ʙᴏᴛ ꜰᴏʀᴄᴇ sᴜʙsᴄʀɪʙᴇ ᴄʜᴀɴɴᴇʟs.\n\n{channel}", 
            reply_markup=InlineKeyboardMarkup(btn))
		
    elif query.data.startswith("force_channel_delete"):
        _, user_id = query.data.split("#")
        btn = [[InlineKeyboardButton('≼ ʙᴀᴄᴋ', callback_data=f'force_channel_setgs#{user_id}')]]
        settings = await db.get_user(int(user_id))
        channels = settings.get("fsub_channels", [])
        if not channels:
            await query.answer("ʏᴏᴜ ᴅɪᴅɴ'ᴛ ᴀᴅᴅᴇᴅ ᴀɴʏ ꜰᴏʀᴄᴇ sᴜʙsᴄʀɪʙᴇ ᴄʜᴀɴɴᴇʟ...", show_alert=True)
            return
        await db.update_user_info(int(user_id), {"fsub_channels": []})
        await query.message.edit_text("sᴜᴄᴄᴇssꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ꜰᴏʀᴄᴇ ᴄʜᴀɴɴᴇʟ 🗑", reply_markup=InlineKeyboardMarkup(btn))

    elif query.data.startswith("set_force_channel"):
        _, user_id = query.data.split("#")
        btn = [[InlineKeyboardButton('≼ ʙᴀᴄᴋ', callback_data=f'force_channel_setgs#{user_id}')]]
        await query.message.edit_text(
            f"ꜱᴇɴᴅ ᴏɴᴇ ᴏʀ ᴍᴏʀᴇ ᴄʜᴀɴɴᴇʟ ɪᴅꜱ ꜱᴇᴘᴀʀᴀᴛᴇᴅ ʙʏ ꜱᴘᴀᴄᴇ:\n\n"
            f"**Example:** `-1001234567890 -1009876543210`\n\n"
            f"/cancel - ᴄᴀɴᴄᴇʟ ᴛʜɪs ᴘʀᴏᴄᴇss."
        )
        msg = await client.listen(query.from_user.id)
        if msg.text.strip() == "/cancel":
            await query.message.delete()
            await query.message.reply("❌ ᴄᴀɴᴄᴇʟʟᴇᴅ ᴛʜɪs ᴘʀᴏᴄᴇss...", reply_markup=InlineKeyboardMarkup(btn))
            return
        await query.message.delete()
        channel_ids = msg.text.split()
        added_channels, failed_channels = [], []
        await query.message.delete()
        settings = await db.get_user(int(user_id))
        channels = settings.get("fsub_channels", [])
        for ch_id in channel_ids:
            try:
                ch_id = int(ch_id)
                chat = await client.get_chat(ch_id)
                try: await client.create_chat_invite_link(chat.id)
                except Exception:
                    failed_channels.append(f"{chat.title} (<code>{ch_id}</code>) - ❌ Bot not admin")
                    continue
                if ch_id not in channels:
                    channels.append(ch_id)
                    added_channels.append(f"{chat.title} (<code>{ch_id}</code>) ✅")
            except Exception as e:
                failed_channels.append(f"<code>{ch_id}</code> - ❌ {str(e)}")
        await query.message.delete()
        await db.update_user_info(int(user_id), {"fsub_channels": channels})
        text = "📢 Force Channel Update Result:\n\n"
        if added_channels: text += "✅ Added:\n" + "\n".join(added_channels) + "\n\n"
        if failed_channels: text += "⚠️ Failed:\n" + "\n".join(failed_channels)
        await query.message.reply(text, reply_markup=InlineKeyboardMarkup(btn))

    elif query.data.startswith("log_channel_setgs"):
        _, user_id = query.data.split("#")
        settings = await db.get_user(int(user_id))
        btn = [[
            InlineKeyboardButton('sᴇᴛ ᴄʜᴀɴɴᴇʟ', callback_data=f'set_log_channel#{user_id}'),
            InlineKeyboardButton('ᴅᴇʟᴇᴛᴇ ᴄʜᴀɴɴᴇʟ', callback_data=f'log_channel_delete#{user_id}')
        ],[InlineKeyboardButton('≼ ʙᴀᴄᴋ', callback_data=f'settings#{user_id}')]]
        if settings['log_channel'] == "": channel = "ʏᴏᴜ ᴅɪᴅɴ'ᴛ ᴀᴅᴅᴇᴅ ᴀɴʏ ʟᴏɢ ᴄʜᴀɴɴᴇʟ❗️"
        else:
            chat = await client.get_chat(settings['log_channel'])
            channel = f"ʏᴏᴜʀ ʟᴏɢ ᴄʜᴀɴɴᴇʟ - {chat.title}"
        await query.message.edit(f"<b>📝 ʟᴏɢ ᴄʜᴀɴɴᴇʟ ꜱᴇᴛᴛɪɴɢꜱ:\n\nᴄᴜʀʀᴇɴᴛ ʟᴏɢ ᴄʜᴀɴɴᴇʟ:{channel}</b>", reply_markup=InlineKeyboardMarkup(btn))
	    
    elif query.data.startswith("set_log_channel"):
        _, user_id = query.data.split("#")
        btn = [[InlineKeyboardButton('≼ ʙᴀᴄᴋ', callback_data=f'log_channel_setgs#{user_id}')]]
        await query.message.edit_text(f"<b>ꜰᴏʀᴡᴀʀᴅ ʟᴏɢ ᴄʜᴀɴɴᴇʟ ᴀɴʏ ᴍᴇssᴀɢᴇ ᴛᴏ ᴍᴇ,\nᴀɴᴅ ᴍᴀᴋᴇ sᴜʀᴇ @{BOT_USERNAME} ɪs ᴀᴅᴍɪɴ ɪɴ ʏᴏᴜʀ ᴄʜᴀɴɴᴇʟ.\n\n/cancel - ᴄᴀɴᴄᴇʟ ᴛʜɪs ᴘʀᴏᴄᴇss.</b>")
        msg = await client.listen(query.from_user.id)
        if msg.text == '/cancel':
            await query.message.delete()
            await query.message.reply("ᴄᴀɴᴄᴇʟᴇᴅ ᴛʜɪs ᴘʀᴏᴄᴇss...", reply_markup=InlineKeyboardMarkup(btn))
            return
        if msg.forward_from_chat and msg.forward_from_chat.type == enums.ChatType.CHANNEL: chat_id = msg.forward_from_chat.id
        else:
            await query.message.delete()
            await query.message.reply('ɴᴏᴛ ꜰᴏʀᴡᴀʀᴅ ꜰʀᴏᴍ ᴄʜᴀɴɴᴇʟ', reply_markup=InlineKeyboardMarkup(btn))
            return
        await query.message.delete()
        try:
            chat = await client.get_chat(chat_id)
            t = await client.send_message(chat.id, 'Test!')
            await t.delete()
        except Exception as e:
            await query.message.reply(f'💔 sᴏᴍᴇᴛʜɪɴɢ ᴡᴇɴᴛ ᴡʀᴏɴɢ...\n\n<code>{e}</code>', reply_markup=InlineKeyboardMarkup(btn))
            return
        await db.update_user_info(int(user_id), {"log_channel": chat.id})
        await query.message.reply(f"⚡️ sᴜᴄᴄᴇssꜰᴜʟʟʏ ᴀᴅᴅᴇᴅ ʏᴏᴜʀ ʟᴏɢ ᴄʜᴀɴɴᴇʟ - {chat.title}", reply_markup=InlineKeyboardMarkup(btn))

    elif query.data.startswith("log_channel_delete"):
        _, user_id = query.data.split("#")
        btn = [[InlineKeyboardButton('≼ ʙᴀᴄᴋ', callback_data=f'log_channel_setgs#{user_id}')]]
        settings = await db.get_user(int(user_id))
        if settings['log_channel'] == "":
            await query.answer("ʏᴏᴜ ᴅɪᴅɴ'ᴛ ᴀᴅᴅᴇᴅ ᴀɴʏ ʟᴏɢ ᴄʜᴀɴɴᴇʟ.", show_alert=True)
            return
        await db.update_user_info(int(user_id), {"log_channel": ""})
        await query.message.edit_text("sᴜᴄᴄᴇssꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ʏᴏᴜʀ ʟᴏɢ ᴄʜᴀɴɴᴇʟ ✅", reply_markup=InlineKeyboardMarkup(btn))
		
    elif query.data.startswith("update_protect_mode"):
        _, user_id = query.data.split("#")
        settings = await db.get_user(int(user_id))
        btn = [[InlineKeyboardButton('ᴛᴜʀɴ ᴏꜰꜰ ❌ ' if settings['protect_content'] else 'ᴛᴜʀɴ ᴏɴ ✅', callback_data=f"clone_files_mode#{user_id}#{settings['protect_content']}")],[InlineKeyboardButton('≼ ʙᴀᴄᴋ', callback_data=f'settings#{user_id}')]]
        mode = 'ᴛᴜʀɴ ᴏɴ ✅' if settings['protect_content'] else 'ᴛᴜʀɴ ᴏꜰꜰ ❌'
        await query.message.edit(f"ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ʙᴏᴛ ɢɪᴠᴇɴ ꜰɪʟᴇꜱ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ, ᴍᴇᴀɴꜱ ᴡʜᴇᴛʜᴇʀ ᴜꜱᴇʀꜱ ᴄᴀɴ ꜰᴏʀᴡᴀʀᴅ ʏᴏᴜʀ ꜰɪʟᴇ ᴏʀ ɴᴏᴛ....\n\nᴘʀᴏᴛᴇᴄᴛ:- {mode}", reply_markup=InlineKeyboardMarkup(btn))
    
    elif query.data.startswith("clone_files_mode"):
        _, user_id, status = query.data.split("#")
        if status == 'True': await db.update_user_info(int(user_id), {"protect_content": False})
        else: await db.update_user_info(int(user_id), {"protect_content": True})
        settings = await db.get_user(int(user_id))
        btn = [[InlineKeyboardButton('ᴛᴜʀɴ ᴏꜰꜰ ❌ ' if settings['protect_content'] else 'ᴛᴜʀɴ ᴏɴ ✅', callback_data=f"clone_files_mode#{user_id}#{settings['protect_content']}")],[InlineKeyboardButton('≼ ʙᴀᴄᴋ', callback_data=f'settings#{user_id}')]]
        mode = 'ᴛᴜʀɴ ᴏɴ ✅' if settings['protect_content'] else 'ᴛᴜʀɴ ᴏꜰꜰ ❌'
        await query.message.edit(f"ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ʙᴏᴛ ɢɪᴠᴇɴ ꜰɪʟᴇꜱ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ, ᴍᴇᴀɴꜱ ᴡʜᴇᴛʜᴇʀ ᴜꜱᴇʀꜱ ᴄᴀɴ ꜰᴏʀᴡᴀʀᴅ ʏᴏᴜʀ ꜰɪʟᴇ ᴏʀ ɴᴏᴛ....\n\nᴘʀᴏᴛᴇᴄᴛ:- {mode}", reply_markup=InlineKeyboardMarkup(btn))
    
    elif query.data.startswith("tutorial_setgs"):
        _, user_id = query.data.split("#")
        settings = await db.get_user(int(user_id))
        btn = [[
            InlineKeyboardButton('sᴇᴛ ᴛᴜᴛᴏʀɪᴀʟ', callback_data=f'set_tutorial#{user_id}'),
            InlineKeyboardButton('ᴅᴇʟᴇᴛᴇ ᴛᴜᴛᴏʀɪᴀʟ', callback_data=f'tutorial_delete#{user_id}')
        ],[InlineKeyboardButton('≼ ʙᴀᴄᴋ', callback_data=f'settings#{user_id}')]]
        if settings['how_to_download'] == "": tutorial = "ᴅɪᴅɴ'ᴛ ᴀᴅᴅᴇᴅ ᴀɴʏ ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ..."
        else: tutorial = f"ʟɪɴᴋ - {settings['how_to_download']}"
        await query.message.edit(f"ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ʙᴏᴛ ᴛᴜᴛᴏʀɪᴀʟ ᴠɪᴅᴇᴏ ʟɪɴᴋ ꜰᴏʀ ʜᴏᴡ ᴛᴏ ᴏᴘᴇɴ ʟɪɴᴋ.\n\n{tutorial}", disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(btn))

    elif query.data.startswith("set_tutorial"):
        _, user_id = query.data.split("#")
        uid = int(user_id)		
        btn = [[InlineKeyboardButton('≼ ʙᴀᴄᴋ', callback_data=f'tutorial_setgs#{user_id}')]]
        await query.message.edit_text("sᴇɴᴅ ᴍᴇ ᴀ ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ...\n\n/cancel - ᴄᴀɴᴄᴇʟ ᴛʜɪs ᴘʀᴏᴄᴇss.")
        msg = await client.listen(query.from_user.id)
        if msg.text == '/cancel':
            await query.message.delete()
            await query.message.reply("ᴄᴀɴᴄᴇʟʟᴇᴅ ᴛʜɪs ᴘʀᴏᴄᴇss...", reply_markup=InlineKeyboardMarkup(btn))
            return
        await db.update_user_info(int(user_id), {"how_to_download": msg.text})
        await query.message.delete()
        await query.message.reply("sᴜᴄᴄᴇssꜰᴜʟʟʏ sᴇᴛ ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ ✅", reply_markup=InlineKeyboardMarkup(btn))

    elif query.data.startswith("tutorial_delete"):
        _, user_id = query.data.split("#")
        btn = [[InlineKeyboardButton('≼ ʙᴀᴄᴋ', callback_data=f'tutorial_setgs#{user_id}')]]
        settings = await db.get_user(int(user_id))
        if settings['how_to_download'] == "":
            await query.answer("ʏᴏᴜ ᴅɪᴅɴ'ᴛ ᴀᴅᴅᴇᴅ ᴀɴʏ ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ", show_alert=True)
            return
        await db.update_user_info(int(user_id), {"how_to_download": ""})
        await query.message.edit_text('⚠️ sᴜᴄᴄᴇssꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ...', reply_markup=InlineKeyboardMarkup(btn))
	
    elif query.data.startswith("verify_time_setgs"):
        _, user_id = query.data.split("#")
        settings = await db.get_user(int(user_id))
        verify_time = settings.get("verify_expire", 0)
        btn = [
            [InlineKeyboardButton("⏳ ꜱᴇᴛ ᴛɪᴍᴇ", callback_data=f"set_verify_time#{user_id}")],
            [InlineKeyboardButton("≼ ʙᴀᴄᴋ", callback_data=f"verify_setgs#{user_id}")]
        ]
        await query.message.edit_text(
            f"<b>Vᴇʀɪғɪᴄᴀᴛɪᴏɴ Tɪᴍᴇ Sᴇᴛᴛɪɴɢꜱ</b>\n\n"
            f"⏰ Cᴜʀʀᴇɴᴛ Tɪᴍᴇ: <code>{verify_time if verify_time else 'Nᴏᴛ Sᴇᴛ'}</code> sec",
            reply_markup=InlineKeyboardMarkup(btn)
        )

    elif query.data.startswith("set_verify_time"):
        _, user_id = query.data.split("#")
        btn = [[InlineKeyboardButton('≼ ʙᴀᴄᴋ', callback_data=f'verify_time_setgs#{user_id}')]]		
        await query.message.edit_text(
            "<b>Sᴇɴᴅ ᴍᴇ ᴀ ᴛɪᴍᴇ ʟɪᴋᴇ:</b>\n"
            "`10m` → 10 minutes\n"
            "`1h` → 1 hour\n"
            "`30s` → 30 seconds\n\n"
            "/cancel - ᴄᴀɴᴄᴇʟʟᴇᴅ ᴛʜɪs ᴘʀᴏᴄᴇss..."
        )
        msg = await client.listen(int(user_id))
        if msg.text == "/cancel":
            await query.message.delete()
            await query.message.reply("ᴄᴀɴᴄᴇʟʟᴇᴅ ᴛʜɪs ᴘʀᴏᴄᴇss...", reply_markup=InlineKeyboardMarkup(btn))
            return
        await query.message.delete() 			
        try:
            arg = msg.text.lower()
            if arg.endswith("s"): seconds = int(arg[:-1])
            elif arg.endswith("m"): seconds = int(arg[:-1]) * 60
            elif arg.endswith("h"): seconds = int(arg[:-1]) * 3600
            elif arg.endswith("d"): seconds = int(arg[:-1]) * 86400
            else: seconds = int(arg)
        except: return await query.message.reply("❌ Iɴᴠᴀʟɪᴅ ғᴏʀᴍᴀᴛ. Exᴀᴍᴘʟᴇ: 10m or 2h", quote=True)
        await query.message.delete()
        await db.update_user_info(int(user_id), {"verify_expire": seconds})
        await query.message.reply(f"✅ Vᴇʀɪғɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ ᴜᴘᴅᴀᴛᴇᴅ ᴛᴏ <b>{seconds} ꜱᴇᴄᴏɴᴅꜱ</b>", reply_markup=InlineKeyboardMarkup(btn))
		
    elif query.data.startswith("verify_setgs"):
        _, user_id = query.data.split("#")
        settings = await db.get_user(int(user_id))
        btn = [[
			InlineKeyboardButton('ᴏꜰꜰ ᴠᴇʀɪꜰʏ' if settings['verify'] else 'ᴏɴ ᴠᴇʀɪꜰʏ', callback_data=f"update_verify#{user_id}#{settings['verify']}")
        ],[
            InlineKeyboardButton('sᴇᴛ ᴠᴇʀɪꜰʏ ', callback_data=f'set_verify#{user_id}'),
            InlineKeyboardButton('ᴅᴇʟᴇᴛᴇ ᴠᴇʀɪꜰʏ ', callback_data=f'verify_delete#{user_id}')
		],[InlineKeyboardButton("ꜱᴇᴛ ᴠᴇʀɪғʏ ᴛɪᴍᴇ", callback_data=f"verify_time_setgs#{user_id}")],[InlineKeyboardButton('≼ ʙᴀᴄᴋ', callback_data=f'settings#{user_id}')]]
        verify_status = 'ᴏɴ ✅' if settings['verify'] else 'ᴏꜰꜰ ❌'
        if settings['verify_api'] == "": api_url = "ʏᴏᴜ ᴅɪᴅɴ'ᴛ ᴀᴅᴅᴇᴅ ᴀɴʏ ᴠᴇʀɪꜰʏ"
        else: api_url = f"ᴜʀʟ - <code>{settings['verify_site']}</code>\nᴀᴘɪ - <code>{settings['verify_api']}</code>"
        await query.message.edit(f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ʙᴏᴛ ᴠᴇʀɪꜰʏ ᴡɪᴛʜ ɢɪᴠᴇɴ ꜰɪʟᴇs.\n\nᴠᴇʀɪꜰʏ - {verify_status}\n\n{api_url}</b>", reply_markup=InlineKeyboardMarkup(btn))

    elif query.data.startswith("set_verify"):
        _, user_id = query.data.split("#")
        btn = [[InlineKeyboardButton('≼ ʙᴀᴄᴋ', callback_data=f'verify_setgs#{user_id}')]]
        await query.message.edit_text("<b>sᴇɴᴅ ᴍᴇ ᴀ ᴠᴇʀɪꜰʏ ᴜʀʟ...\n\n/cancel - ᴄᴀɴᴄᴇʟ ᴛʜɪs ᴘʀᴏᴄᴇss.</b>")
        url_msg = await client.listen(query.from_user.id)
        url = url_msg.text
        if url_msg.text == '/cancel':
            await query.message.delete()
            await query.message.reply("ᴄᴀɴᴄᴇʟʟᴇᴅ ᴛʜɪs ᴘʀᴏᴄᴇss...", reply_markup=InlineKeyboardMarkup(btn))
            return
        await query.message.delete()
        a = await query.message.reply("sᴇɴᴅ ᴍᴇ ᴠᴇʀɪꜰʏ ᴀᴘɪ...")
        api_msg = await client.listen(query.from_user.id)
        api = api_msg.text
        await db.update_user_info(int(user_id), {"verify_site": url, "verify_api": api, "verify": True})
        await a.delete()
        await query.message.reply("sᴜᴄᴄᴇssꜰᴜʟʟʏ sᴇᴛ ᴠᴇʀɪꜰʏ ✅", reply_markup=InlineKeyboardMarkup(btn))

    # In plugins/callback.py

    elif query.data.startswith("update_verify"):
        _, user_id, status = query.data.split("#")
        settings = await db.get_user(int(user_id))

        # --- নতুন যুক্তি (New Logic) শুরু ---
        # যদি ব্যবহারকারী ভেরিফিকেশন 'অন' করতে চায় (অর্থাৎ বর্তমান স্ট্যাটাস 'False')
        if status == 'False':
            # চেক করো URL এবং API সেট করা আছে কিনা
            if not settings.get("verify_api") or not settings.get("verify_site"):
                await query.answer(
                    "⚠️ ᴘʟᴇᴀsᴇ sᴇᴛ ᴠᴇʀɪꜰʏ ᴜʀʟ ᴀɴᴅ ᴀᴘɪ ꜰɪʀsᴛ!",
                    show_alert=True
                )
                return  # 여기서 코드 실행을 멈춥니다.

        # --- নতুন যুক্তি শেষ ---

        # যদি উপরের শর্ত পূরণ হয় (বা ব্যবহারকারী 'অফ' করতে চায়), তাহলে স্ট্যাটাস আপডেট করো
        if status == 'True':
            await db.update_user_info(int(user_id), {"verify": False})
        else:
            await db.update_user_info(int(user_id), {"verify": True})

        # মেসেজ এবং বাটন পুনরায় তৈরি করে দেখাও
        settings = await db.get_user(int(user_id))
        btn = [[
			InlineKeyboardButton('ᴏꜰꜰ ᴠᴇʀɪꜰʏ' if settings['verify'] else 'ᴏɴ ᴠᴇʀɪꜰʏ', callback_data=f"update_verify#{user_id}#{settings['verify']}")
        ],[
            InlineKeyboardButton('sᴇᴛ ᴠᴇʀɪꜰʏ ', callback_data=f'set_verify#{user_id}'),
            InlineKeyboardButton('ᴅᴇʟᴇᴛᴇ ᴠᴇʀɪꜰʏ ', callback_data=f'verify_delete#{user_id}')
		],[InlineKeyboardButton("ꜱᴇᴛ ᴠᴇʀɪғʏ ᴛɪᴍᴇ", callback_data=f"verify_time_setgs#{user_id}")],[InlineKeyboardButton('≼ ʙᴀᴄᴋ', callback_data=f'settings#{user_id}')]]
        verify_status = 'ᴏɴ ✅' if settings['verify'] else 'ᴏꜰꜰ ❌'
        await query.message.edit(f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ʙᴏᴛ ᴠᴇʀɪꜰʏ ᴡɪᴛʜ ɢɪᴠᴇɴ ꜰɪʟᴇs.\n\nᴠᴇʀɪꜰʏ - {verify_status}\n\nᴜʀʟ - <code>{settings['verify_site']}</code>\nᴀᴘɪ - <code>{settings['verify_api']}</code></b>", reply_markup=InlineKeyboardMarkup(btn))
		
    elif query.data.startswith("verify_delete"):
        _, user_id = query.data.split("#")
        btn = [[InlineKeyboardButton('≼ ʙᴀᴄᴋ', callback_data=f'verify_setgs#{user_id}')]]
        settings = await db.get_user(int(user_id))
        if settings['verify_api'] == "":
            await query.answer("⚠️ ʏᴏᴜ ᴅɪᴅɴ'ᴛ ᴀᴅᴅᴇᴅ ᴀɴʏ ᴠᴇʀɪꜰʏ...", show_alert=True)
            return
        await db.update_user_info(int(user_id), {"verify": False, "verify_api": None, "verify_site": None})
        await query.message.edit_text("🗑 sᴜᴄᴄᴇssꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ᴠᴇʀɪꜰʏ...", reply_markup=InlineKeyboardMarkup(btn))
	
    elif query.data.startswith("shortlink_setgs"):
        _, user_id = query.data.split("#")
        settings = await db.get_user(int(user_id))
        btn = [[
            InlineKeyboardButton('sᴇᴛ sʜᴏʀᴛʟɪɴᴋ', callback_data=f'set_shortlink#{user_id}'),
            InlineKeyboardButton('ᴅᴇʟᴇᴛᴇ sʜᴏʀᴛʟɪɴᴋ ', callback_data=f'shortlink_delete#{user_id}')
        ],[InlineKeyboardButton('≼ ʙᴀᴄᴋ', callback_data=f'settings#{user_id}')]]
        if settings['shortener_api'] == "": api_url = "ʏᴏᴜ ᴅɪᴅɴ'ᴛ ᴀᴅᴅᴇᴅ ᴀɴʏ sʜᴏʀᴛʟɪɴᴋ"
        else: api_url = f"ᴜʀʟ - <code>{settings['base_site']}</code>\nᴀᴘɪ - <code>{settings['shortener_api']}</code>"
        await query.message.edit(f"<b>ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ʙᴏᴛ sʜᴏʀᴛʟɪɴᴋ ᴡɪᴛʜ ɢɪᴠᴇɴ ꜰɪʟᴇs.\n\n{api_url}</b>", reply_markup=InlineKeyboardMarkup(btn))

    elif query.data.startswith("set_shortlink"):
        _, user_id = query.data.split("#")
        btn = [[InlineKeyboardButton('≼ ʙᴀᴄᴋ', callback_data=f'shortlink_setgs#{user_id}')]]
        await query.message.edit_text("<b>sᴇɴᴅ ᴍᴇ ᴀ sʜᴏʀᴛʟɪɴᴋ ᴜʀʟ...\n\n/cancel - ᴄᴀɴᴄᴇʟ ᴛʜɪs ᴘʀᴏᴄᴇss.</b>")
        url_msg = await client.listen(query.from_user.id)
        url = url_msg.text
        if url_msg.text == '/cancel':
            await query.message.delete()
            await query.message.reply("ᴄᴀɴᴄᴇʟʟᴇᴅ ᴛʜɪs ᴘʀᴏᴄᴇss...", reply_markup=InlineKeyboardMarkup(btn))
            return
        await query.message.delete()
        a = await query.message.reply("sᴇɴᴅ ᴍᴇ sʜᴏʀᴛʟɪɴᴋ ᴀᴘɪ...")
        api_msg = await client.listen(query.from_user.id)
        api = api_msg.text
        await db.update_user_info(int(user_id), {"base_site": url, "shortener_api": api})
        await a.delete()
        await query.message.reply("sᴜᴄᴄᴇssꜰᴜʟʟʏ sᴇᴛ sʜᴏʀᴛʟɪɴᴋ ✅", reply_markup=InlineKeyboardMarkup(btn))

    elif query.data.startswith("shortlink_delete"):
        _, user_id = query.data.split("#")
        btn = [[InlineKeyboardButton('≼ ʙᴀᴄᴋ', callback_data=f'shortlink_setgs#{user_id}')]]
        settings = await db.get_user(int(user_id))
        if settings['shortener_api'] == "":
            await query.answer("⚠️ ʏᴏᴜ ᴅɪᴅɴ'ᴛ ᴀᴅᴅᴇᴅ ᴀɴʏ sʜᴏʀᴛʟɪɴᴋ...", show_alert=True)
            return
        await db.update_user_info(int(user_id), {"base_site": "", "shortener_api": ""})
        await query.message.edit_text("🗑 sᴜᴄᴄᴇssꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ sʜᴏʀᴛʟɪɴᴋ...!", reply_markup=InlineKeyboardMarkup(btn))

    elif query.data.startswith("caption_setgs"):
        _, user_id = query.data.split("#")
        user = await db.get_user(int(user_id))
        caption = user.get("custom_caption", "ɴᴏᴛ ꜱᴇᴛ!")
        btn = [[
            InlineKeyboardButton("📝 sᴇᴛ ᴄᴀᴘᴛɪᴏɴ", callback_data=f"set_caption#{user_id}")
		],[InlineKeyboardButton("♻️ ᴅᴇꜰᴀᴜʟᴛ ᴄᴀᴘᴛɪᴏɴ", callback_data=f"default_caption#{user_id}")],[InlineKeyboardButton("≼ ʙᴀᴄᴋ", callback_data=f"settings#{user_id}")]]
        await query.message.edit(f"**📝 ʜᴇʀᴇ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ʙᴏᴛ ɢɪᴠᴇɴ ꜰɪʟᴇ ᴄᴀᴘᴛɪᴏɴ.\n\n**📌 ꜰɪʟᴇ ᴄᴀᴘᴛɪᴏɴ -:`{caption}`", disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(btn))

    elif query.data.startswith("default_caption"):
        _, user_id = query.data.split("#")
        btn = [[InlineKeyboardButton("≼ ʙᴀᴄᴋ", callback_data=f"caption_setgs#{user_id}")]]
        await db.update_user_info(int(user_id), {"custom_caption": ""})
        await query.message.edit_text("✅ sᴜᴄᴄᴇssꜰᴜʟʟʏ sᴇᴛ ᴛᴏ ᴅᴇꜰᴀᴜʟᴛ ꜰɪʟᴇ ᴄᴀᴘᴛɪᴏɴ....", reply_markup=InlineKeyboardMarkup(btn))
        
    elif query.data.startswith("set_caption"):
        _, user_id = query.data.split("#")
        btn = [[InlineKeyboardButton("≼ ʙᴀᴄᴋ", callback_data=f"caption_setgs#{user_id}")]]
        await query.message.edit_text("✍️ sᴇɴᴅ ᴍᴇ ᴀ ꜰɪʟᴇ ᴄᴀᴘᴛɪᴏɴ.\n\nᴀᴠᴀɪʟᴀʙʟᴇ ꜰɪʟʟɪɴɢ:-\n`{file_name}` - File name\n`{file_size}` - File size\n\n/cancel - ᴄᴀɴᴄᴇʟ ᴛʜɪs ᴘʀᴏᴄᴇss.")
        msg = await client.listen(query.from_user.id)
        if msg.text == "/cancel":
            await query.message.delete()
            await query.message.reply("❌ ᴄᴀɴᴄᴇʟʟᴇᴅ ᴛʜɪs ᴘʀᴏᴄᴇss...!", reply_markup=InlineKeyboardMarkup(btn))
            return
        try: msg.text.format(file_name='file_name', file_size='file_size')
        except Exception as e:
            await query.message.delete()
            await query.message.reply(f'ᴡʀᴏɴɢ ꜰᴏʀᴍᴀᴛ <code>{e}</code> ᴜsᴇᴅ...', reply_markup=InlineKeyboardMarkup(btn))
            return
        await db.update_user_info(int(user_id), {"custom_caption": msg.text})
        await query.message.delete()
        await query.message.reply(f"✅ sᴜᴄᴄᴇssꜰᴜʟʟʏ sᴇᴛ ꜰɪʟᴇ ᴄᴀᴘᴛɪᴏɴ -\n\n{msg.text}", disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(btn))

    elif query.data.startswith("settings"):
        _, user_id = query.data.split("#")
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
        await query.message.edit_text("**⚙️ ꜱᴇᴛᴛɪɴɢꜱ ᴍᴇɴᴜ:\n\nsᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴄᴜsᴛᴏᴍɪᴢᴇ ʏᴏᴜʀ ꜰɪʟᴇs sᴇᴛᴛɪɴɢs:",reply_markup=InlineKeyboardMarkup(buttons))
