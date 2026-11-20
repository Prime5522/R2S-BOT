import asyncio, time
from pyrogram import Client, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from config import *
from utils import get_hash
from Script import script
from plugins.save_media import save_batch_media_in_channel, save_media_in_channel
from database.clonedb import clone_db
from plugins.clone import (
    build_start_content,
    handle_clone_callback,
    set_pending_input,
    clear_pending_input,
    resolve_target_db,
    resolve_target_client,
    send_or_edit_text,
)


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


def parse_settings_target(data: str, fallback_uid: int):
    """
    Parse callback patterns:
      prefix#user_id
      prefix#user_id#clone_bot_id
    """
    parts = data.split("#")
    target_uid = int(parts[1]) if len(parts) > 1 and parts[1] else fallback_uid
    clone_bot_id = int(parts[2]) if len(parts) > 2 and parts[2] else None
    return target_uid, clone_bot_id


def parse_toggle_target(data: str, fallback_uid: int):
    """
    Parse callback patterns:
      prefix#user_id#status
      prefix#user_id#status#clone_bot_id
    """
    parts = data.split("#")
    target_uid = int(parts[1]) if len(parts) > 1 and parts[1] else fallback_uid
    status = parts[2] if len(parts) > 2 else "False"
    clone_bot_id = int(parts[3]) if len(parts) > 3 and parts[3] else None
    return target_uid, status, clone_bot_id


def build_suffix(target_uid: int, clone_bot_id: int = None) -> str:
    return f"{target_uid}#{clone_bot_id}" if clone_bot_id else f"{target_uid}"


async def edit_caption_or_text(query: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup):
    if query.message.photo:
        return await query.message.edit_caption(
            caption=text,
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML,
        )
    return await query.message.edit_text(
        text=text,
        reply_markup=reply_markup,
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True,
    )


@Client.on_callback_query()
async def cb_handler(client: Client, query: CallbackQuery):
    # Handle all Clone Mode callbacks first
    if await handle_clone_callback(client, query):
        return

    user_id = query.from_user.id

    if query.data == "close_data":
        await query.message.delete()

    elif query.data == "about":
        buttons = [[
            InlineKeyboardButton('• Home •', callback_data='start'),
            InlineKeyboardButton('• Close •', callback_data='close_data')
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        me2 = (await client.get_me()).mention
        await edit_caption_or_text(
            query,
            script.ABOUT_TXT.format(me2, me2),
            reply_markup,
        )

    elif query.data == "start":
        await clear_pending_input(client, user_id)
        start_pic, caption_text, reply_markup = await build_start_content(client, query.from_user.mention)

        if query.message.photo:
            if start_pic:
                await query.message.edit_caption(
                    caption=caption_text,
                    reply_markup=reply_markup,
                    parse_mode=enums.ParseMode.HTML,
                )
            else:
                try:
                    await query.message.delete()
                except Exception:
                    pass
                await query.message.reply_text(
                    text=caption_text,
                    reply_markup=reply_markup,
                    parse_mode=enums.ParseMode.HTML,
                    disable_web_page_preview=True,
                )
        else:
            if start_pic:
                try:
                    await query.message.delete()
                except Exception:
                    pass
                await query.message.reply_photo(
                    photo=start_pic,
                    caption=caption_text,
                    reply_markup=reply_markup,
                    parse_mode=enums.ParseMode.HTML,
                )
            else:
                await query.message.edit_text(
                    text=caption_text,
                    reply_markup=reply_markup,
                    parse_mode=enums.ParseMode.HTML,
                    disable_web_page_preview=True,
                )

    elif query.data == "help":
        buttons = [[
            InlineKeyboardButton('• Home •', callback_data='start'),
            InlineKeyboardButton('• Close •', callback_data='close_data')
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await edit_caption_or_text(query, script.HELP_TXT, reply_markup)

    elif query.data.startswith("stream"):
        msg_id = int(query.data.split('#', 1)[1])

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
                InlineKeyboardButton("▶ Watch Online", url=online),
                InlineKeyboardButton("⬇ Fast Download", url=download)
            ],
            [InlineKeyboardButton('❌ Close ❌', callback_data='close_data')]
        ]

        return await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btn))

    elif query.data == "addToBatchTrue":
        cur_db = await resolve_target_db(client)
        file_msg_id = query.message.reply_to_message.id
        await cur_db.add_media(user_id, file_msg_id)
        await cur_db.add_user_file(user_id, file_msg_id)
        confirm = await query.message.edit(
            "✅ File saved in batch!\n\nPress the button below to generate your batch link:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📦 Get Batch Link", callback_data="getBatchLink")],
                [InlineKeyboardButton("❌ Close", callback_data='close_data')]
            ])
        )
        await cur_db.add_confirm_msg(user_id, confirm.id)
        return

    elif query.data == "getBatchLink":
        cur_db = await resolve_target_db(client)
        message_ids = await cur_db.get_media(user_id)
        if not message_ids:
            return await query.answer("⚠️ Batch list is empty!", show_alert=True)
        editable = await client.send_message(
            chat_id=query.message.chat.id,
            text="⏳ Please wait, generating batch link..."
        )
        await save_batch_media_in_channel(
            bot=client,
            editable=editable,
            message_ids=message_ids,
            owner_uid=user_id
        )
        await cur_db.clear_media(user_id)

        async def delete_later():
            await asyncio.sleep(30)
            for msg_id in await cur_db.get_confirm_msgs(user_id):
                try:
                    await client.delete_messages(chat_id=query.message.chat.id, message_ids=msg_id)
                except Exception:
                    pass
            await cur_db.clear_confirm_msgs(user_id)
            for msg_id in await cur_db.get_user_files(user_id):
                try:
                    await client.delete_messages(chat_id=query.message.chat.id, message_ids=msg_id)
                except Exception:
                    pass
            await cur_db.clear_user_files(user_id)

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
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        await cur_db.reset_user(target_uid)
        await query.answer("✅ Your settings have been reset successfully.", show_alert=True)
        buttons = [[InlineKeyboardButton("« Back", callback_data=f"user_details#{sfx}")]]
        await send_or_edit_text(
            query,
            "⚙️ All of your settings have been reset to default!\n\nYou can now configure them freshly.",
            InlineKeyboardMarkup(buttons),
        )

    elif query.data.startswith("user_details"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        user = await cur_db.get_user(target_uid)
        shortener_api = user.get("shortener_api") or "Not Set"
        base_site = user.get("base_site") or "Not Set"
        custom_caption = user.get("custom_caption") or "Not Set"
        verify_api = user.get("verify_api") or "Not Set"
        verify_site = user.get("verify_site") or "Not Set"
        verify_expire = user.get("verify_expire") or "Not Set"
        how_to_download = user.get("how_to_download") or "Not Set"
        verify = "✅ Enabled" if user.get("verify") else "❌ Disabled"
        log_channel = user.get("log_channel") or "Not Set"
        fsub_channels = user.get("fsub_channels") or []
        protect_content = "✅ Enabled" if user.get("protect_content") else "❌ Disabled"
        text = (
            "<b>⚙️ Your File Store Settings</b>\n\n"
            f"<b>✅ Verify Shortener:</b>\n"
            f"• Site: <code>{verify_site}</code>\n"
            f"• API: <code>{verify_api}</code>\n\n"
            f"<b>🔗 File Shortener:</b>\n"
            f"• Site: <code>{base_site}</code>\n"
            f"• API: <code>{shortener_api}</code>\n\n"
            f"<b>🧭 Verification Time:</b> <code>{verify_expire}</code>\n"
            f"<b>📘 Verify Status:</b> {verify}\n"
            f"<b>⚡ Tutorial Link:</b> {how_to_download}\n"
            f"<b>🛡 Protect Content:</b> {protect_content}\n"
            f"<b>📢 F-Sub Channels:</b> {', '.join([str(ch) for ch in fsub_channels]) if fsub_channels else 'Not Set'}\n"
            f"<b>📜 Log Channel:</b> <code>{log_channel}</code>\n"
            f"<b>📝 Caption:</b> <code>{custom_caption}</code>"
        )
        btn = [
            [InlineKeyboardButton("♻️ Reset Settings", callback_data=f"user_reset#{sfx}")],
            [InlineKeyboardButton("« Back", callback_data=f"settings#{sfx}")]
        ]
        await send_or_edit_text(query, text, InlineKeyboardMarkup(btn))

    elif query.data.startswith("permanent_link_setgs"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        user = await cur_db.get_user(target_uid)
        is_on = user.get("permanent_link_mode", True)
        text = (
            "<b>🔗 Permanent Link Settings</b>\n\n"
            "When enabled, file links will use the Website URL (e.g. https://.../file_id...), displaying a web page.\n\n"
            "When disabled, a direct Telegram t.me link will be generated.\n\n"
            f"<b>Current Status:</b> <code>{'ON ✅' if is_on else 'OFF ❌'}</code>"
        )
        buttons = [
            [InlineKeyboardButton(f"Turn {'OFF ❌' if is_on else 'ON ✅'}", callback_data=f"toggle_permanent_link#{target_uid}#{is_on}" + (f"#{clone_bot_id}" if clone_bot_id else ""))],
            [InlineKeyboardButton("« Back", callback_data=f"settings#{sfx}")]
        ]
        await send_or_edit_text(query, text, InlineKeyboardMarkup(buttons))

    elif query.data.startswith("toggle_permanent_link"):
        target_uid, status, clone_bot_id = parse_toggle_target(query.data, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        new_status = False if status == 'True' else True
        await cur_db.update_user_info(target_uid, {"permanent_link_mode": new_status})
        user = await cur_db.get_user(target_uid)
        is_on = user.get("permanent_link_mode", True)
        text = (
            "<b>🔗 Permanent Link Settings</b>\n\n"
            "When enabled, file links will use the Website URL (e.g. https://.../file_id...), displaying a web page.\n\n"
            "When disabled, a direct Telegram t.me link will be generated.\n\n"
            f"<b>Current Status:</b> <code>{'ON ✅' if is_on else 'OFF ❌'}</code>"
        )
        buttons = [
            [InlineKeyboardButton(f"Turn {'OFF ❌' if is_on else 'ON ✅'}", callback_data=f"toggle_permanent_link#{target_uid}#{is_on}" + (f"#{clone_bot_id}" if clone_bot_id else ""))],
            [InlineKeyboardButton("« Back", callback_data=f"settings#{sfx}")]
        ]
        await send_or_edit_text(query, text, InlineKeyboardMarkup(buttons))
        await query.answer(f"✅ Permanent Link mode is now {'ON' if is_on else 'OFF'}")

    elif query.data.startswith("force_channel_setgs"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        await clear_pending_input(client, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        target_client = await resolve_target_client(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        settings = await cur_db.get_user(target_uid)
        btn = [
            [
                InlineKeyboardButton('Set Channel', callback_data=f'set_force_channel#{sfx}'),
                InlineKeyboardButton('Delete Channels', callback_data=f'force_channel_delete#{sfx}')
            ],
            [InlineKeyboardButton('« Back', callback_data=f'settings#{sfx}')]
        ]
        channels = settings.get("fsub_channels", [])
        if not channels:
            channel = "You haven't added any Force Subscribe channels yet."
        else:
            try:
                chat_titles = []
                for ch in channels:
                    chat = await target_client.get_chat(ch)
                    chat_titles.append(f"<b>{chat.title}</b> (<code>{ch}</code>)")
                channel = "<b>Force Subscribe Channels:</b>\n" + "\n".join(chat_titles)
            except Exception as e:
                channel = f"⚠️ Error fetching channels: <code>{e}</code>"
        await send_or_edit_text(
            query,
            f"Manage your Force Subscribe channels below.\n\n{channel}",
            InlineKeyboardMarkup(btn),
        )

    elif query.data.startswith("force_channel_delete"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        btn = [[InlineKeyboardButton('« Back', callback_data=f'force_channel_setgs#{sfx}')]]
        settings = await cur_db.get_user(target_uid)
        channels = settings.get("fsub_channels", [])
        if not channels:
            return await query.answer("You haven't added any Force Subscribe channels.", show_alert=True)
        await cur_db.update_user_info(target_uid, {"fsub_channels": []})
        await send_or_edit_text(query, "🗑 Successfully deleted all Force Subscribe channels.", InlineKeyboardMarkup(btn))

    elif query.data.startswith("set_force_channel"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        back_cb = f"force_channel_setgs#{sfx}"
        await set_pending_input(
            client,
            user_id,
            action="set_force_channel",
            back_cb=back_cb,
            data={"target_uid": target_uid, "clone_bot_id": clone_bot_id},
        )
        await send_or_edit_text(
            query,
            "Send one or more channel IDs separated by spaces:\n\n"
            "<b>Example:</b> <code>-1001234567890 -1009876543210</code>\n\n"
            "Send /cancel to cancel.",
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=back_cb)]]),
        )

    elif query.data.startswith("log_channel_setgs"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        await clear_pending_input(client, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        target_client = await resolve_target_client(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        settings = await cur_db.get_user(target_uid)
        btn = [
            [
                InlineKeyboardButton('Set Channel', callback_data=f'set_log_channel#{sfx}'),
                InlineKeyboardButton('Delete Channel', callback_data=f'log_channel_delete#{sfx}')
            ],
            [InlineKeyboardButton('« Back', callback_data=f'settings#{sfx}')]
        ]
        if not settings.get('log_channel'):
            channel = "Not Set"
        else:
            try:
                chat = await target_client.get_chat(settings['log_channel'])
                channel = chat.title
            except Exception:
                channel = str(settings['log_channel'])
        await send_or_edit_text(
            query,
            f"<b>📝 Log Channel Settings</b>\n\n<b>Current Log Channel:</b> {channel}",
            InlineKeyboardMarkup(btn),
        )

    elif query.data.startswith("set_log_channel"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        target_client = await resolve_target_client(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        back_cb = f"log_channel_setgs#{sfx}"
        bot_username = getattr(target_client, "username", None) or (await target_client.get_me()).username
        await set_pending_input(
            client,
            user_id,
            action="set_log_channel",
            back_cb=back_cb,
            data={"target_uid": target_uid, "clone_bot_id": clone_bot_id},
        )
        await send_or_edit_text(
            query,
            f"<b>Forward any message from your log channel to me.</b>\n"
            f"Make sure @{bot_username} is an admin in that channel.\n\n"
            f"Send /cancel to cancel.",
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=back_cb)]]),
        )

    elif query.data.startswith("log_channel_delete"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        btn = [[InlineKeyboardButton('« Back', callback_data=f'log_channel_setgs#{sfx}')]]
        settings = await cur_db.get_user(target_uid)
        if not settings.get('log_channel'):
            return await query.answer("You haven't added a log channel yet.", show_alert=True)
        await cur_db.update_user_info(target_uid, {"log_channel": None})
        await send_or_edit_text(query, "✅ Successfully deleted your log channel.", InlineKeyboardMarkup(btn))

    elif query.data.startswith("update_protect_mode"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        settings = await cur_db.get_user(target_uid)
        protect = bool(settings.get('protect_content', False))
        btn = [
            [InlineKeyboardButton('Turn OFF ❌' if protect else 'Turn ON ✅', callback_data=f"clone_files_mode#{target_uid}#{protect}" + (f"#{clone_bot_id}" if clone_bot_id else ""))],
            [InlineKeyboardButton('« Back', callback_data=f'settings#{sfx}')]
        ]
        mode = 'ON ✅' if protect else 'OFF ❌'
        await send_or_edit_text(
            query,
            f"<b>🛡 Content Protection Settings</b>\n\nControl whether users can forward or save your files.\n\n<b>Current Status:</b> {mode}",
            InlineKeyboardMarkup(btn),
        )

    elif query.data.startswith("clone_files_mode"):
        target_uid, status, clone_bot_id = parse_toggle_target(query.data, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        await cur_db.update_user_info(target_uid, {"protect_content": False if status == 'True' else True})
        settings = await cur_db.get_user(target_uid)
        protect = bool(settings.get('protect_content', False))
        btn = [
            [InlineKeyboardButton('Turn OFF ❌' if protect else 'Turn ON ✅', callback_data=f"clone_files_mode#{target_uid}#{protect}" + (f"#{clone_bot_id}" if clone_bot_id else ""))],
            [InlineKeyboardButton('« Back', callback_data=f'settings#{sfx}')]
        ]
        mode = 'ON ✅' if protect else 'OFF ❌'
        await send_or_edit_text(
            query,
            f"<b>🛡 Content Protection Settings</b>\n\nControl whether users can forward or save your files.\n\n<b>Current Status:</b> {mode}",
            InlineKeyboardMarkup(btn),
        )

    elif query.data.startswith("tutorial_setgs"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        await clear_pending_input(client, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        settings = await cur_db.get_user(target_uid)
        btn = [
            [
                InlineKeyboardButton('Set Tutorial', callback_data=f'set_tutorial#{sfx}'),
                InlineKeyboardButton('Delete Tutorial', callback_data=f'tutorial_delete#{sfx}')
            ],
            [InlineKeyboardButton('« Back', callback_data=f'settings#{sfx}')]
        ]
        tutorial = f"Link: {settings['how_to_download']}" if settings.get('how_to_download') else "No tutorial link set yet."
        await send_or_edit_text(
            query,
            f"<b>🎬 Tutorial Video Settings</b>\n\nManage your 'How to Open Link' tutorial URL.\n\n{tutorial}",
            InlineKeyboardMarkup(btn),
        )

    elif query.data.startswith("set_tutorial"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        back_cb = f"tutorial_setgs#{sfx}"
        await set_pending_input(
            client,
            user_id,
            action="set_tutorial",
            back_cb=back_cb,
            data={"target_uid": target_uid, "clone_bot_id": clone_bot_id},
        )
        await send_or_edit_text(
            query,
            "Send your tutorial video link.\n\nSend /cancel to cancel.",
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=back_cb)]]),
        )

    elif query.data.startswith("tutorial_delete"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        btn = [[InlineKeyboardButton('« Back', callback_data=f'tutorial_setgs#{sfx}')]]
        settings = await cur_db.get_user(target_uid)
        if not settings.get('how_to_download'):
            return await query.answer("You haven't added a tutorial link yet.", show_alert=True)
        await cur_db.update_user_info(target_uid, {"how_to_download": None})
        await send_or_edit_text(query, "🗑 Successfully deleted tutorial link.", InlineKeyboardMarkup(btn))

    elif query.data.startswith("verify_time_setgs"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        await clear_pending_input(client, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        settings = await cur_db.get_user(target_uid)
        verify_time = settings.get("verify_expire", 0)
        btn = [
            [InlineKeyboardButton("⏳ Set Time", callback_data=f"set_verify_time#{sfx}")],
            [InlineKeyboardButton("« Back", callback_data=f"verify_setgs#{sfx}")]
        ]
        await send_or_edit_text(
            query,
            f"<b>⏳ Verification Time Settings</b>\n\n"
            f"⏰ Current Time: <code>{verify_time if verify_time else 'Not Set'}</code> sec",
            InlineKeyboardMarkup(btn),
        )

    elif query.data.startswith("set_verify_time"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        back_cb = f"verify_time_setgs#{sfx}"
        await set_pending_input(
            client,
            user_id,
            action="set_verify_time",
            back_cb=back_cb,
            data={"target_uid": target_uid, "clone_bot_id": clone_bot_id},
        )
        await send_or_edit_text(
            query,
            "<b>Send verification duration like:</b>\n"
            "<code>10m</code> → 10 minutes\n"
            "<code>1h</code> → 1 hour\n"
            "<code>30s</code> → 30 seconds\n\n"
            "Send /cancel to cancel.",
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=back_cb)]]),
        )

    elif query.data.startswith("verify_setgs"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        await clear_pending_input(client, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        settings = await cur_db.get_user(target_uid)
        verify = bool(settings.get('verify', False))
        btn = [
            [InlineKeyboardButton('Disable Verify ❌' if verify else 'Enable Verify ✅', callback_data=f"update_verify#{target_uid}#{verify}" + (f"#{clone_bot_id}" if clone_bot_id else ""))],
            [
                InlineKeyboardButton('Set Verify', callback_data=f'set_verify#{sfx}'),
                InlineKeyboardButton('Delete Verify', callback_data=f'verify_delete#{sfx}')
            ],
            [InlineKeyboardButton("⏳ Set Verify Time", callback_data=f"verify_time_setgs#{sfx}")],
            [InlineKeyboardButton('« Back', callback_data=f'settings#{sfx}')]
        ]
        verify_status = 'ON ✅' if verify else 'OFF ❌'
        if not settings.get('verify_api'):
            api_url = "No verification shortener configured."
        else:
            api_url = f"URL: <code>{settings['verify_site']}</code>\nAPI: <code>{settings['verify_api']}</code>"
        await send_or_edit_text(
            query,
            f"<b>✅ Verification Settings</b>\n\nStatus: {verify_status}\n\n{api_url}",
            InlineKeyboardMarkup(btn),
        )

    elif query.data.startswith("set_verify"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        back_cb = f"verify_setgs#{sfx}"
        await set_pending_input(
            client,
            user_id,
            action="set_verify_url",
            back_cb=back_cb,
            data={"target_uid": target_uid, "clone_bot_id": clone_bot_id},
        )
        await send_or_edit_text(
            query,
            "<b>Send your Verify Shortener URL/Domain...</b>\n\nSend /cancel to cancel.",
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=back_cb)]]),
        )

    elif query.data.startswith("update_verify"):
        target_uid, status, clone_bot_id = parse_toggle_target(query.data, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        settings = await cur_db.get_user(target_uid)

        if status == 'False':
            if not settings.get("verify_api") or not settings.get("verify_site"):
                return await query.answer("⚠️ Please set Verify URL and API first!", show_alert=True)

        await cur_db.update_user_info(target_uid, {"verify": False if status == 'True' else True})
        settings = await cur_db.get_user(target_uid)
        verify = bool(settings.get('verify', False))
        btn = [
            [InlineKeyboardButton('Disable Verify ❌' if verify else 'Enable Verify ✅', callback_data=f"update_verify#{target_uid}#{verify}" + (f"#{clone_bot_id}" if clone_bot_id else ""))],
            [
                InlineKeyboardButton('Set Verify', callback_data=f'set_verify#{sfx}'),
                InlineKeyboardButton('Delete Verify', callback_data=f'verify_delete#{sfx}')
            ],
            [InlineKeyboardButton("⏳ Set Verify Time", callback_data=f"verify_time_setgs#{sfx}")],
            [InlineKeyboardButton('« Back', callback_data=f'settings#{sfx}')]
        ]
        verify_status = 'ON ✅' if verify else 'OFF ❌'
        await send_or_edit_text(
            query,
            f"<b>✅ Verification Settings</b>\n\nStatus: {verify_status}\n\nURL: <code>{settings.get('verify_site')}</code>\nAPI: <code>{settings.get('verify_api')}</code>",
            InlineKeyboardMarkup(btn),
        )

    elif query.data.startswith("verify_delete"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        btn = [[InlineKeyboardButton('« Back', callback_data=f'verify_setgs#{sfx}')]]
        settings = await cur_db.get_user(target_uid)
        if not settings.get('verify_api'):
            return await query.answer("⚠️ No verification shortener is configured.", show_alert=True)
        await cur_db.update_user_info(target_uid, {"verify": False, "verify_api": None, "verify_site": None})
        await send_or_edit_text(query, "🗑 Successfully deleted verification settings.", InlineKeyboardMarkup(btn))

    elif query.data.startswith("shortlink_setgs"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        await clear_pending_input(client, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        settings = await cur_db.get_user(target_uid)
        btn = [
            [
                InlineKeyboardButton('Set Shortlink', callback_data=f'set_shortlink#{sfx}'),
                InlineKeyboardButton('Delete Shortlink', callback_data=f'shortlink_delete#{sfx}')
            ],
            [InlineKeyboardButton('« Back', callback_data=f'settings#{sfx}')]
        ]
        if not settings.get('shortener_api'):
            api_url = "No shortlink configured."
        else:
            api_url = f"URL: <code>{settings['base_site']}</code>\nAPI: <code>{settings['shortener_api']}</code>"
        await send_or_edit_text(
            query,
            f"<b>🔗 Shortener Settings</b>\n\n{api_url}",
            InlineKeyboardMarkup(btn),
        )

    elif query.data.startswith("set_shortlink"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        back_cb = f"shortlink_setgs#{sfx}"
        await set_pending_input(
            client,
            user_id,
            action="set_shortlink_url",
            back_cb=back_cb,
            data={"target_uid": target_uid, "clone_bot_id": clone_bot_id},
        )
        await send_or_edit_text(
            query,
            "<b>Send your Shortener URL/Domain...</b>\n\nSend /cancel to cancel.",
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=back_cb)]]),
        )

    elif query.data.startswith("shortlink_delete"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        btn = [[InlineKeyboardButton('« Back', callback_data=f'shortlink_setgs#{sfx}')]]
        settings = await cur_db.get_user(target_uid)
        if not settings.get('shortener_api'):
            return await query.answer("⚠️ No shortlink is configured.", show_alert=True)
        await cur_db.update_user_info(target_uid, {"base_site": None, "shortener_api": None})
        await send_or_edit_text(query, "🗑 Successfully deleted shortlink!", InlineKeyboardMarkup(btn))

    elif query.data.startswith("caption_setgs"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        await clear_pending_input(client, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        user = await cur_db.get_user(target_uid)
        caption = user.get("custom_caption") or "Not Set"
        btn = [
            [InlineKeyboardButton("📝 Set Caption", callback_data=f"set_caption#{sfx}")],
            [InlineKeyboardButton("♻️ Default Caption", callback_data=f"default_caption#{sfx}")],
            [InlineKeyboardButton("« Back", callback_data=f"settings#{sfx}")]
        ]
        await send_or_edit_text(
            query,
            f"<b>📝 File Caption Settings</b>\n\n<b>Current Caption:</b>\n<code>{caption}</code>",
            InlineKeyboardMarkup(btn),
        )

    elif query.data.startswith("default_caption"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        cur_db = await resolve_target_db(client, clone_bot_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        btn = [[InlineKeyboardButton("« Back", callback_data=f"caption_setgs#{sfx}")]]
        await cur_db.update_user_info(target_uid, {"custom_caption": None})
        await send_or_edit_text(query, "✅ Reset to default file caption.", InlineKeyboardMarkup(btn))

    elif query.data.startswith("set_caption"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        sfx = build_suffix(target_uid, clone_bot_id)
        back_cb = f"caption_setgs#{sfx}"
        await set_pending_input(
            client,
            user_id,
            action="set_caption",
            back_cb=back_cb,
            data={"target_uid": target_uid, "clone_bot_id": clone_bot_id},
        )
        await send_or_edit_text(
            query,
            "✍️ Send your custom file caption.\n\n"
            "Available placeholders:\n"
            "• <code>{file_name}</code> — File name\n"
            "• <code>{file_size}</code> — File size\n\n"
            "Send /cancel to cancel.",
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=back_cb)]]),
        )

    elif query.data.startswith("settings"):
        target_uid, clone_bot_id = parse_settings_target(query.data, user_id)
        await clear_pending_input(client, user_id)
        sfx = build_suffix(target_uid, clone_bot_id)

        title = "<b>⚙️ Settings Menu</b>"
        if clone_bot_id:
            clone_doc = await clone_db.get_clone(clone_bot_id)
            if not clone_doc or int(clone_doc["owner_id"]) != int(user_id):
                return await query.answer("⚠️ Access denied!", show_alert=True)
            title = f"<b>⚙️ Clone Bot Settings (@{clone_doc.get('bot_username')})</b>"

        buttons = [
            [InlineKeyboardButton("📝 Caption Settings", callback_data=f"caption_setgs#{sfx}")],
            [InlineKeyboardButton("🔗 Set Shortener", callback_data=f"shortlink_setgs#{sfx}")],
            [InlineKeyboardButton("✅ Verify Settings", callback_data=f"verify_setgs#{sfx}")],
            [InlineKeyboardButton("🔗 Permanent Link", callback_data=f"permanent_link_setgs#{sfx}")],
            [InlineKeyboardButton("🎬 Tutorial Settings", callback_data=f"tutorial_setgs#{sfx}")],
            [InlineKeyboardButton("🛡 Protect Settings", callback_data=f"update_protect_mode#{sfx}")],
            [InlineKeyboardButton("📢 Force Subscribe", callback_data=f"force_channel_setgs#{sfx}")],
            [InlineKeyboardButton("📢 Log Channel", callback_data=f"log_channel_setgs#{sfx}")],
            [InlineKeyboardButton("📑 My Details", callback_data=f"user_details#{sfx}")],
        ]
        if clone_bot_id:
            buttons.append([InlineKeyboardButton("« Back to Clone Panel", callback_data=f"manage_clone#{clone_bot_id}")])

        await send_or_edit_text(
            query,
            f"{title}\n\nSelect an option below to customize your file settings:",
            InlineKeyboardMarkup(buttons),
        )
