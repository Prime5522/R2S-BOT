import re
from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from config import MAIN_BOT_USERNAME, MAX_CLONE_PER_USER, PICS
from Script import script
from database import get_db, get_clone_database
from database.clonedb import clone_db
from clone_manager import start_clone, stop_clone, restart_clone, delete_clone, RUNNING_CLONES

# Per-(bot_id, user_id) input state store — completely isolated across users
PENDING_INPUTS: dict = {}

DEFAULT_CLONE_START_TXT = (
    "<b>Hello {mention} 👋,\n\n"
    "Welcome to {bot_mention}!\n"
    "I am your personal File Storage Bot. 📁\n"
    "Send me any file, document, video, audio, or photo and I will store it and generate a shareable link.\n\n"
    "👇 Use the buttons below to get started or create your own clone bot!</b>"
)


async def get_client_bot_id(client: Client) -> int:
    bot_id = getattr(client, "bot_id", None)
    if not bot_id:
        me = await client.get_me()
        bot_id = me.id
        client.bot_id = bot_id
    return bot_id


async def set_pending_input(client: Client, user_id: int, action: str, back_cb: str, data: dict = None):
    bot_id = await get_client_bot_id(client)
    PENDING_INPUTS[(bot_id, int(user_id))] = {
        "action": action,
        "back_cb": back_cb,
        "data": data or {},
    }


async def clear_pending_input(client: Client, user_id: int):
    bot_id = await get_client_bot_id(client)
    PENDING_INPUTS.pop((bot_id, int(user_id)), None)


async def resolve_target_db(client: Client, clone_bot_id: int = None):
    if clone_bot_id:
        clone_doc = await clone_db.get_clone(int(clone_bot_id))
        if clone_doc:
            return get_clone_database(int(clone_bot_id), clone_doc["db_name"])
    return get_db(client)


async def resolve_target_client(client: Client, clone_bot_id: int = None):
    if clone_bot_id:
        running = RUNNING_CLONES.get(int(clone_bot_id))
        if running:
            return running
    return client


async def send_or_edit_text(query: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup = None, disable_web_page_preview: bool = True):
    """Safely edit a text message, or replace a photo message with a clean text card."""
    if query.message.text:
        try:
            return await query.message.edit_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=disable_web_page_preview,
            )
        except Exception:
            pass
    try:
        await query.message.delete()
    except Exception:
        pass
    return await query.message.reply_text(
        text=text,
        reply_markup=reply_markup,
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=disable_web_page_preview,
    )


def format_start_text(template: str, user_mention: str, bot_mention: str) -> str:
    try:
        if "{mention}" in template or "{bot_mention}" in template:
            return template.format(mention=user_mention, bot_mention=bot_mention)
        if "{}" in template:
            if template.count("{}") >= 2:
                return template.format(user_mention, bot_mention)
            return template.format(user_mention)
        return template
    except Exception:
        return template


async def build_start_content(client: Client, user_mention: str):
    """Build start photo, caption/text, and buttons for either Main Bot or Clone Bot."""
    me = await client.get_me()
    bot_mention = me.mention

    if getattr(client, "is_clone", False):
        start_pic = getattr(client, "custom_start_pic", None)
        custom_txt = getattr(client, "custom_start_txt", None)
        template = custom_txt if custom_txt else DEFAULT_CLONE_START_TXT
        caption_text = format_start_text(template, user_mention, bot_mention)

        buttons = [
            [
                InlineKeyboardButton("• Help •", callback_data="help"),
                InlineKeyboardButton("• About •", callback_data="about"),
            ],
            [
                InlineKeyboardButton(
                    "✨ Create Your Own Clone",
                    url=f"https://t.me/{MAIN_BOT_USERNAME}?start=clone",
                )
            ],
        ]

        custom_buttons = getattr(client, "custom_start_buttons", None) or []
        for row in custom_buttons:
            btn_row = [
                InlineKeyboardButton(b["text"], url=b["url"])
                for b in row
                if b.get("text") and b.get("url")
            ]
            if btn_row:
                buttons.append(btn_row)

        return start_pic, caption_text, InlineKeyboardMarkup(buttons)

    # Main Bot start content
    start_pic = PICS if PICS else None
    caption_text = format_start_text(script.START_TXT, user_mention, bot_mention)
    buttons = [
        [
            InlineKeyboardButton("• Updates •", url="https://t.me/PrimeXBots"),
            InlineKeyboardButton("• Support •", url="https://t.me/Prime_Support_group"),
        ],
        [
            InlineKeyboardButton("• Help •", callback_data="help"),
            InlineKeyboardButton("• About •", callback_data="about"),
        ],
        [
            InlineKeyboardButton("✨ Create / Manage Clone", callback_data="create_clone"),
        ],
    ]
    return start_pic, caption_text, InlineKeyboardMarkup(buttons)


def parse_custom_buttons(raw_text: str):
    rows = []
    for line in raw_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        row = []
        for part in line.split("|"):
            part = part.strip()
            if " - " in part:
                text, url = part.rsplit(" - ", 1)
            else:
                m = re.match(r"^(.*?)\s*-\s*((?:https?|tg)://\S+)$", part)
                if not m:
                    raise ValueError(f"Invalid format: <code>{part}</code>")
                text, url = m.group(1), m.group(2)
            text = text.strip()
            url = url.strip()
            if not text or not re.match(r"^(https?|tg)://\S+$", url):
                raise ValueError(f"Invalid button text or URL: <code>{part}</code>")
            row.append({"text": text, "url": url})
        if row:
            rows.append(row)
    if not rows:
        raise ValueError("No valid buttons found.")
    return rows


async def send_clone_entry(client: Client, target, is_callback: bool = False):
    """
    Entry point for /clone, /start clone, and Main Bot's Clone button.
    - If run on a clone bot: redirects user to Main Bot with ?start=clone.
    - If user already has a clone: shows a nice card with @username button.
    - If user has no clone: asks them to forward the BotFather token message.
    """
    user_id = target.from_user.id

    if getattr(client, "is_clone", False):
        text = (
            "<b>✨ Create or Manage Your Clone Bot</b>\n\n"
            "Clone management is handled on our main bot.\n"
            "Click the button below to continue:"
        )
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🚀 Open Clone Panel", url=f"https://t.me/{MAIN_BOT_USERNAME}?start=clone")]]
        )
        if is_callback:
            return await send_or_edit_text(target, text, markup)
        return await target.reply_text(text, reply_markup=markup, disable_web_page_preview=True)

    await clear_pending_input(client, user_id)
    existing = await clone_db.get_user_clone(user_id)

    if existing:
        bot_id = existing["bot_id"]
        bot_username = existing.get("bot_username") or "Unknown"
        status = existing.get("status", "active")
        status_label = "✅ Active" if status == "active" else "⛔ Inactive"
        has_msg = "Custom" if existing.get("start_msg") else "Default"
        has_pic = "Set" if existing.get("start_pic") else "None"
        btn_count = sum(len(r) for r in (existing.get("start_buttons") or []))

        text = (
            "<b>🤖 Your Cloned Bot</b>\n\n"
            "You already have a cloned bot linked to your account.\n"
            f"<i>(Limit: {MAX_CLONE_PER_USER} clone per user)</i>\n\n"
            f"• <b>Bot:</b> @{bot_username}\n"
            f"• <b>Status:</b> {status_label}\n"
            f"• <b>Start Message:</b> {has_msg}\n"
            f"• <b>Start Picture:</b> {has_pic}\n"
            f"• <b>Custom Buttons:</b> {btn_count}\n\n"
            "👇 Click your bot below to open the customization and settings panel:"
        )
        buttons = [
            [InlineKeyboardButton(f"🤖 @{bot_username}", callback_data=f"manage_clone#{bot_id}")],
        ]
        if is_callback:
            buttons.append([InlineKeyboardButton("« Back", callback_data="start")])
        else:
            buttons.append([InlineKeyboardButton("❌ Close", callback_data="close_data")])

        markup = InlineKeyboardMarkup(buttons)
        if is_callback:
            return await send_or_edit_text(target, text, markup)
        return await target.reply_text(text, reply_markup=markup, disable_web_page_preview=True)

    # User does not have a clone yet -> Ask for @BotFather forward
    back_cb = "start" if is_callback else "close_data"
    await set_pending_input(client, user_id, action="awaiting_botfather_forward", back_cb=back_cb)

    text = (
        "<b>✨ Create Your Own Clone Bot</b>\n\n"
        "Follow these simple steps to create your own File Store Bot:\n\n"
        "1️⃣ Open @BotFather and create a new bot with <code>/newbot</code> (or open an existing bot's token message).\n"
        "2️⃣ <b>Forward</b> the message containing the Bot Token from @BotFather directly to this chat.\n\n"
        "⚠️ <i>Do not send the token as plain text — you must forward the original message from @BotFather.</i>\n\n"
        "Send /cancel anytime to cancel."
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="clone_cancel_input")]])
    if is_callback:
        return await send_or_edit_text(target, text, markup)
    return await target.reply_text(text, reply_markup=markup, disable_web_page_preview=True)


async def show_manage_clone_panel(target, clone_doc: dict, is_callback: bool = True):
    bot_id = clone_doc["bot_id"]
    owner_id = clone_doc["owner_id"]
    bot_username = clone_doc.get("bot_username") or "Unknown"
    status = clone_doc.get("status", "active")
    status_label = "✅ Active" if status == "active" else "⛔ Inactive"
    toggle_label = "⛔ Deactivate" if status == "active" else "✅ Activate"

    has_msg = "Custom" if clone_doc.get("start_msg") else "Default"
    has_pic = "Set" if clone_doc.get("start_pic") else "None"
    btn_count = sum(len(r) for r in (clone_doc.get("start_buttons") or []))

    text = (
        "<b>🛠 Clone Bot Customize Panel</b>\n\n"
        f"• <b>Bot:</b> @{bot_username}\n"
        f"• <b>Status:</b> {status_label}\n"
        f"• <b>Start Message:</b> {has_msg}\n"
        f"• <b>Start Picture:</b> {has_pic}\n"
        f"• <b>Custom Buttons:</b> {btn_count}\n\n"
        "Customize your clone's appearance, manage its file settings, or control its status below:"
    )

    buttons = [
        [
            InlineKeyboardButton("📝 Start Message", callback_data=f"clone_msg_menu#{bot_id}"),
            InlineKeyboardButton("🖼 Start Picture", callback_data=f"clone_pic_menu#{bot_id}"),
        ],
        [
            InlineKeyboardButton("🔘 Start Buttons", callback_data=f"clone_btns_menu#{bot_id}"),
        ],
        [
            InlineKeyboardButton("⚙️ Bot Settings (Caption, Shortener, FSub...)", callback_data=f"settings#{owner_id}#{bot_id}"),
        ],
        [
            InlineKeyboardButton("🔁 Restart", callback_data=f"clone_restart#{bot_id}"),
            InlineKeyboardButton(toggle_label, callback_data=f"clone_toggle#{bot_id}"),
        ],
        [InlineKeyboardButton("🗑 Delete Clone", callback_data=f"clone_delete#{bot_id}")],
        [InlineKeyboardButton("« Back", callback_data="clone_card")],
    ]
    markup = InlineKeyboardMarkup(buttons)

    if is_callback:
        return await send_or_edit_text(target, text, markup)
    return await target.reply_text(text, reply_markup=markup, disable_web_page_preview=True)


# ---- /clone Command ----
@Client.on_message(filters.command("clone") & filters.private)
async def clone_command(client: Client, message: Message):
    return await send_clone_entry(client, message, is_callback=False)


# ---- Clone Callback Dispatcher (called from plugins/callback.py) ----
async def handle_clone_callback(client: Client, query: CallbackQuery) -> bool:
    data = query.data
    user_id = query.from_user.id

    if data == "create_clone" or data == "clone_card":
        await send_clone_entry(client, query, is_callback=True)
        return True

    if data == "clone_cancel_input":
        await clear_pending_input(client, user_id)
        existing = await clone_db.get_user_clone(user_id)
        if existing:
            await send_clone_entry(client, query, is_callback=True)
        else:
            await send_or_edit_text(
                query,
                "❌ Clone creation cancelled.",
                InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Home", callback_data="start")]]),
            )
        return True

    if data.startswith("manage_clone#"):
        bot_id = int(data.split("#")[1])
        await clear_pending_input(client, user_id)
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or int(clone_doc["owner_id"]) != int(user_id):
            await query.answer("⚠️ This clone does not belong to you.", show_alert=True)
            return True
        await show_manage_clone_panel(query, clone_doc, is_callback=True)
        return True

    # ---- Start Message Menu ----
    if data.startswith("clone_msg_menu#"):
        bot_id = int(data.split("#")[1])
        await clear_pending_input(client, user_id)
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or int(clone_doc["owner_id"]) != int(user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True

        current_msg = clone_doc.get("start_msg")
        preview = f"<blockquote>{current_msg}</blockquote>" if current_msg else "<i>Default Clone Start Message</i>"
        text = (
            "<b>📝 Start Message Settings</b>\n\n"
            f"<b>Current Message:</b>\n{preview}\n\n"
            "When you set a custom start message, the default message will be replaced with yours."
        )
        buttons = [
            [InlineKeyboardButton("✏️ Set Start Message", callback_data=f"clone_setmsg#{bot_id}")],
            [InlineKeyboardButton("♻️ Reset to Default", callback_data=f"clone_delmsg#{bot_id}")],
            [InlineKeyboardButton("« Back", callback_data=f"manage_clone#{bot_id}")],
        ]
        await send_or_edit_text(query, text, InlineKeyboardMarkup(buttons))
        return True

    if data.startswith("clone_setmsg#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or int(clone_doc["owner_id"]) != int(user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True

        await set_pending_input(
            client,
            user_id,
            action="clone_setmsg",
            back_cb=f"clone_msg_menu#{bot_id}",
            data={"bot_id": bot_id},
        )
        text = (
            "<b>📝 Send Your New Start Message</b>\n\n"
            "HTML formatting is supported.\n"
            "Optional placeholders:\n"
            "• <code>{mention}</code> or <code>{}</code> — User's clickable name\n"
            "• <code>{bot_mention}</code> — Your bot's name\n\n"
            "Send /cancel to cancel."
        )
        await send_or_edit_text(
            query,
            text,
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=f"clone_msg_menu#{bot_id}")]]),
        )
        return True

    if data.startswith("clone_delmsg#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or int(clone_doc["owner_id"]) != int(user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        if not clone_doc.get("start_msg"):
            await query.answer("ℹ️ Already using the default start message.", show_alert=True)
            return True

        await clone_db.update_clone_settings(bot_id, {"start_msg": None})
        running = RUNNING_CLONES.get(bot_id)
        if running:
            running.custom_start_txt = None
        await query.answer("✅ Reset to default start message!", show_alert=True)
        clone_doc = await clone_db.get_clone(bot_id)
        await show_manage_clone_panel(query, clone_doc, is_callback=True)
        return True

    # ---- Start Picture Menu ----
    if data.startswith("clone_pic_menu#"):
        bot_id = int(data.split("#")[1])
        await clear_pending_input(client, user_id)
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or int(clone_doc["owner_id"]) != int(user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True

        has_pic = "✅ Custom Picture Set" if clone_doc.get("start_pic") else "❌ None (No picture on /start)"
        text = (
            "<b>🖼 Start Picture Settings</b>\n\n"
            f"<b>Current Status:</b> {has_pic}\n\n"
            "By default, your clone bot does not show any picture on /start unless you set one here."
        )
        buttons = [
            [InlineKeyboardButton("🖼 Set Start Picture", callback_data=f"clone_setpic#{bot_id}")],
            [InlineKeyboardButton("🗑 Remove Picture", callback_data=f"clone_delpic#{bot_id}")],
            [InlineKeyboardButton("« Back", callback_data=f"manage_clone#{bot_id}")],
        ]
        await send_or_edit_text(query, text, InlineKeyboardMarkup(buttons))
        return True

    if data.startswith("clone_setpic#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or int(clone_doc["owner_id"]) != int(user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True

        await set_pending_input(
            client,
            user_id,
            action="clone_setpic",
            back_cb=f"clone_pic_menu#{bot_id}",
            data={"bot_id": bot_id},
        )
        text = (
            "<b>🖼 Send a Photo</b>\n\n"
            "Send the image you want to display as the Start Picture in your clone bot.\n\n"
            "Send /cancel to cancel."
        )
        await send_or_edit_text(
            query,
            text,
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=f"clone_pic_menu#{bot_id}")]]),
        )
        return True

    if data.startswith("clone_delpic#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or int(clone_doc["owner_id"]) != int(user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        if not clone_doc.get("start_pic"):
            await query.answer("ℹ️ No start picture is currently set.", show_alert=True)
            return True

        await clone_db.update_clone_settings(bot_id, {"start_pic": None})
        running = RUNNING_CLONES.get(bot_id)
        if running:
            running.custom_start_pic = None
        await query.answer("✅ Start picture removed!", show_alert=True)
        clone_doc = await clone_db.get_clone(bot_id)
        await show_manage_clone_panel(query, clone_doc, is_callback=True)
        return True

    # ---- Start Buttons Menu ----
    if data.startswith("clone_btns_menu#"):
        bot_id = int(data.split("#")[1])
        await clear_pending_input(client, user_id)
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or int(clone_doc["owner_id"]) != int(user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True

        saved_btns = clone_doc.get("start_buttons") or []
        if saved_btns:
            lines = []
            for row in saved_btns:
                lines.append(" | ".join(f"[{b['text']}]({b['url']})" for b in row))
            btn_preview = "\n".join(lines)
        else:
            btn_preview = "<i>No custom buttons set.</i>"

        text = (
            "<b>🔘 Custom Start Buttons</b>\n\n"
            "Your custom buttons will be shown <b>below</b> your clone bot's default buttons (Help, About, Create Your Own Clone).\n\n"
            f"<b>Current Custom Buttons:</b>\n{btn_preview}"
        )
        buttons = [
            [InlineKeyboardButton("➕ Set Start Buttons", callback_data=f"clone_setbtns#{bot_id}")],
            [InlineKeyboardButton("🗑 Remove All Buttons", callback_data=f"clone_delbtns#{bot_id}")],
            [InlineKeyboardButton("« Back", callback_data=f"manage_clone#{bot_id}")],
        ]
        await send_or_edit_text(query, text, InlineKeyboardMarkup(buttons))
        return True

    if data.startswith("clone_setbtns#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or int(clone_doc["owner_id"]) != int(user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True

        await set_pending_input(
            client,
            user_id,
            action="clone_setbtns",
            back_cb=f"clone_btns_menu#{bot_id}",
            data={"bot_id": bot_id},
        )
        text = (
            "<b>🔘 Send Your Custom Start Buttons</b>\n\n"
            "Use this format (one row per line, use <code>|</code> for multiple buttons in the same row):\n\n"
            "<code>My Channel - https://t.me/YourChannel</code>\n"
            "<code>Website - https://example.com | Support - https://t.me/YourSupport</code>\n\n"
            "Send /cancel to cancel."
        )
        await send_or_edit_text(
            query,
            text,
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=f"clone_btns_menu#{bot_id}")]]),
        )
        return True

    if data.startswith("clone_delbtns#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or int(clone_doc["owner_id"]) != int(user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        if not clone_doc.get("start_buttons"):
            await query.answer("ℹ️ No custom buttons are set.", show_alert=True)
            return True

        await clone_db.update_clone_settings(bot_id, {"start_buttons": []})
        running = RUNNING_CLONES.get(bot_id)
        if running:
            running.custom_start_buttons = []
        await query.answer("✅ All custom buttons removed!", show_alert=True)
        clone_doc = await clone_db.get_clone(bot_id)
        await show_manage_clone_panel(query, clone_doc, is_callback=True)
        return True

    # ---- Toggle / Restart / Delete ----
    if data.startswith("clone_toggle#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or int(clone_doc["owner_id"]) != int(user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True

        if clone_doc["status"] == "active":
            await stop_clone(bot_id)
            await clone_db.set_status(bot_id, "inactive")
            await query.answer("⛔ Clone deactivated.")
        else:
            try:
                await start_clone(clone_doc["bot_token"], user_id)
                await query.answer("✅ Clone activated.")
            except Exception as e:
                await query.answer(f"❌ Failed to activate: {e}", show_alert=True)
                return True

        clone_doc = await clone_db.get_clone(bot_id)
        await show_manage_clone_panel(query, clone_doc, is_callback=True)
        return True

    if data.startswith("clone_restart#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or int(clone_doc["owner_id"]) != int(user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True

        await query.answer("🔁 Restarting clone...")
        try:
            await restart_clone(bot_id)
        except Exception as e:
            await send_or_edit_text(
                query,
                f"❌ <b>Restart Failed:</b>\n<code>{e}</code>",
                InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=f"manage_clone#{bot_id}")]]),
            )
            return True

        clone_doc = await clone_db.get_clone(bot_id)
        await show_manage_clone_panel(query, clone_doc, is_callback=True)
        return True

    if data.startswith("clone_delete_confirm#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or int(clone_doc["owner_id"]) != int(user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True

        await delete_clone(bot_id)
        await send_or_edit_text(
            query,
            "✅ Your cloned bot and all of its data have been permanently deleted.",
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Home", callback_data="start")]]),
        )
        return True

    if data.startswith("clone_delete#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or int(clone_doc["owner_id"]) != int(user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True

        btn = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Yes, Delete", callback_data=f"clone_delete_confirm#{bot_id}"),
            InlineKeyboardButton("❌ No", callback_data=f"manage_clone#{bot_id}"),
        ]])
        await send_or_edit_text(
            query,
            "⚠️ <b>Are you sure you want to delete your clone?</b>\n\n"
            "This will permanently stop the cloned bot and erase all of its saved files and user data. This action cannot be undone.",
            btn,
        )
        return True

    return False


# ---- Centralized Per-User Input Handler (replaces client.listen) ----
@Client.on_message(filters.private & ~filters.service, group=-1)
async def clone_and_settings_input_handler(client: Client, message: Message):
    if not message.from_user:
        return

    user_id = message.from_user.id
    bot_id = await get_client_bot_id(client)
    state_key = (bot_id, user_id)

    state = PENDING_INPUTS.get(state_key)
    if not state:
        return

    # Allow standard commands to interrupt and execute normally
    if message.text:
        first_word = message.text.strip().split()[0].lower().split("@")[0]
        if first_word in ("/start", "/clone", "/settings", "/stats", "/restart", "/broadcast", "/pin_broadcast"):
            PENDING_INPUTS.pop(state_key, None)
            return

        if first_word == "/cancel":
            PENDING_INPUTS.pop(state_key, None)
            back_cb = state.get("back_cb", "start")
            await message.reply_text(
                "❌ Process cancelled.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=back_cb)]]),
            )
            await message.stop_propagation()
            return

    action = state["action"]
    data = state.get("data", {})
    back_cb = state.get("back_cb", "start")
    back_markup = InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=back_cb)]])

    # 1. @BotFather Forwarded Token Handling
    if action == "awaiting_botfather_forward":
        # Double-check 1 clone limit
        existing = await clone_db.get_user_clone(user_id)
        if existing:
            PENDING_INPUTS.pop(state_key, None)
            await send_clone_entry(client, message, is_callback=False)
            await message.stop_propagation()
            return

        fwd_user = getattr(message, "forward_from", None)
        if not fwd_user and getattr(message, "forward_origin", None):
            fwd_user = getattr(message.forward_origin, "sender_user", None)

        is_botfather = bool(
            fwd_user
            and (
                (getattr(fwd_user, "username", None) or "").lower() == "botfather"
                or getattr(fwd_user, "id", None) == 93372553
            )
        )
        if not is_botfather:
            await message.reply_text(
                "❌ <b>Invalid Message!</b>\n\n"
                "Please <b>forward</b> the token message directly from @BotFather (do not send plain text).\n\n"
                "Send /cancel to cancel.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="clone_cancel_input")]]),
            )
            await message.stop_propagation()
            return

        raw_text = message.text or message.caption or ""
        match = re.search(r"\b(\d{6,}:[A-Za-z0-9_-]{30,})\b", raw_text)
        if not match:
            await message.reply_text(
                "❌ Could not find a valid Bot Token in that forwarded message.\n"
                "Please forward the exact message from @BotFather containing your HTTP API token.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="clone_cancel_input")]]),
            )
            await message.stop_propagation()
            return

        token = match.group(1).strip()
        PENDING_INPUTS.pop(state_key, None)

        wait_msg = await message.reply_text("<i>⏳ Verifying token and starting your clone bot, please wait...</i>")
        try:
            me = await start_clone(token, user_id)
        except Exception as e:
            await wait_msg.edit_text(
                f"❌ <b>Failed to create clone:</b>\n<code>{e}</code>\n\n"
                "Please check your BotFather token and try again with /clone.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="start")]]),
            )
            await message.stop_propagation()
            return

        await wait_msg.edit_text(
            f"✨ <b>Successfully Cloned Your Bot!</b>\n\n"
            f"🤖 <b>Bot:</b> @{me.username}\n\n"
            f"You can now start @{me.username} or customize it using the button below:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"⚙️ Customize @{me.username}", callback_data=f"manage_clone#{me.id}")],
                [InlineKeyboardButton("« Back to Home", callback_data="start")],
            ]),
        )
        await message.stop_propagation()
        return

    # 2. Clone Start Picture
    if action == "clone_setpic":
        target_bot_id = int(data["bot_id"])
        if not message.photo:
            await message.reply_text("❌ Please send a valid photo (or /cancel to cancel).", reply_markup=back_markup)
            await message.stop_propagation()
            return

        PENDING_INPUTS.pop(state_key, None)
        file_id = message.photo.file_id
        await clone_db.update_clone_settings(target_bot_id, {"start_pic": file_id})
        running = RUNNING_CLONES.get(target_bot_id)
        if running:
            running.custom_start_pic = file_id

        await message.reply_text("✅ Start picture updated successfully!")
        clone_doc = await clone_db.get_clone(target_bot_id)
        if clone_doc:
            await show_manage_clone_panel(message, clone_doc, is_callback=False)
        await message.stop_propagation()
        return

    # 3. Clone Start Message
    if action == "clone_setmsg":
        target_bot_id = int(data["bot_id"])
        if not message.text:
            await message.reply_text("❌ Please send a text message (or /cancel to cancel).", reply_markup=back_markup)
            await message.stop_propagation()
            return

        PENDING_INPUTS.pop(state_key, None)
        new_msg = message.text
        await clone_db.update_clone_settings(target_bot_id, {"start_msg": new_msg})
        running = RUNNING_CLONES.get(target_bot_id)
        if running:
            running.custom_start_txt = new_msg

        await message.reply_text("✅ Start message updated successfully!")
        clone_doc = await clone_db.get_clone(target_bot_id)
        if clone_doc:
            await show_manage_clone_panel(message, clone_doc, is_callback=False)
        await message.stop_propagation()
        return

    # 4. Clone Custom Start Buttons
    if action == "clone_setbtns":
        target_bot_id = int(data["bot_id"])
        if not message.text:
            await message.reply_text("❌ Please send button text and links (or /cancel to cancel).", reply_markup=back_markup)
            await message.stop_propagation()
            return

        try:
            parsed_buttons = parse_custom_buttons(message.text)
        except ValueError as e:
            await message.reply_text(
                f"❌ {e}\n\n"
                "Example format:\n"
                "<code>My Channel - https://t.me/YourChannel</code>\n"
                "<code>Site - https://example.com | Support - https://t.me/Support</code>",
                reply_markup=back_markup,
            )
            await message.stop_propagation()
            return

        PENDING_INPUTS.pop(state_key, None)
        await clone_db.update_clone_settings(target_bot_id, {"start_buttons": parsed_buttons})
        running = RUNNING_CLONES.get(target_bot_id)
        if running:
            running.custom_start_buttons = parsed_buttons

        await message.reply_text("✅ Custom start buttons updated successfully!")
        clone_doc = await clone_db.get_clone(target_bot_id)
        if clone_doc:
            await show_manage_clone_panel(message, clone_doc, is_callback=False)
        await message.stop_propagation()
        return

    # 5. Settings Inputs (shared for Main Bot & Clone Bot Settings)
    target_uid = int(data["target_uid"])
    clone_bot_id = data.get("clone_bot_id")
    cur_db = await resolve_target_db(client, clone_bot_id)

    if action == "set_caption":
        if not message.text:
            await message.reply_text("❌ Please send a valid caption text.", reply_markup=back_markup)
            await message.stop_propagation()
            return
        try:
            message.text.format(file_name="file_name", file_size="file_size")
        except Exception as e:
            PENDING_INPUTS.pop(state_key, None)
            await message.reply_text(f"❌ Invalid format placeholder used: <code>{e}</code>", reply_markup=back_markup)
            await message.stop_propagation()
            return

        PENDING_INPUTS.pop(state_key, None)
        await cur_db.update_user_info(target_uid, {"custom_caption": message.text})
        await message.reply_text(
            f"✅ Successfully updated file caption:\n\n{message.text}",
            disable_web_page_preview=True,
            reply_markup=back_markup,
        )
        await message.stop_propagation()
        return

    if action == "set_shortlink_url":
        if not message.text:
            await message.reply_text("❌ Please send a valid shortener domain/URL.", reply_markup=back_markup)
            await message.stop_propagation()
            return
        PENDING_INPUTS[state_key] = {
            "action": "set_shortlink_api",
            "back_cb": back_cb,
            "data": {"target_uid": target_uid, "clone_bot_id": clone_bot_id, "url": message.text.strip()},
        }
        await message.reply_text("🔑 Now send your Shortener API key (or /cancel to cancel):")
        await message.stop_propagation()
        return

    if action == "set_shortlink_api":
        if not message.text:
            await message.reply_text("❌ Please send a valid API key.", reply_markup=back_markup)
            await message.stop_propagation()
            return
        PENDING_INPUTS.pop(state_key, None)
        await cur_db.update_user_info(
            target_uid,
            {"base_site": data["url"], "shortener_api": message.text.strip()},
        )
        await message.reply_text("✅ Successfully configured shortener!", reply_markup=back_markup)
        await message.stop_propagation()
        return

    if action == "set_verify_url":
        if not message.text:
            await message.reply_text("❌ Please send a valid verify shortener URL.", reply_markup=back_markup)
            await message.stop_propagation()
            return
        PENDING_INPUTS[state_key] = {
            "action": "set_verify_api",
            "back_cb": back_cb,
            "data": {"target_uid": target_uid, "clone_bot_id": clone_bot_id, "url": message.text.strip()},
        }
        await message.reply_text("🔑 Now send your Verify Shortener API key (or /cancel to cancel):")
        await message.stop_propagation()
        return

    if action == "set_verify_api":
        if not message.text:
            await message.reply_text("❌ Please send a valid API key.", reply_markup=back_markup)
            await message.stop_propagation()
            return
        PENDING_INPUTS.pop(state_key, None)
        await cur_db.update_user_info(
            target_uid,
            {"verify_site": data["url"], "verify_api": message.text.strip(), "verify": True},
        )
        await message.reply_text("✅ Successfully configured verification!", reply_markup=back_markup)
        await message.stop_propagation()
        return

    if action == "set_verify_time":
        if not message.text:
            await message.reply_text("❌ Please send a valid time like <code>10m</code> or <code>2h</code>.", reply_markup=back_markup)
            await message.stop_propagation()
            return
        arg = message.text.strip().lower()
        try:
            if arg.endswith("s"):
                seconds = int(arg[:-1])
            elif arg.endswith("m"):
                seconds = int(arg[:-1]) * 60
            elif arg.endswith("h"):
                seconds = int(arg[:-1]) * 3600
            elif arg.endswith("d"):
                seconds = int(arg[:-1]) * 86400
            else:
                seconds = int(arg)
        except Exception:
            await message.reply_text("❌ Invalid format. Example: <code>10m</code> or <code>2h</code>", reply_markup=back_markup)
            await message.stop_propagation()
            return

        PENDING_INPUTS.pop(state_key, None)
        await cur_db.update_user_info(target_uid, {"verify_expire": seconds})
        await message.reply_text(
            f"✅ Verification time updated to <b>{seconds} seconds</b>.",
            reply_markup=back_markup,
        )
        await message.stop_propagation()
        return

    if action == "set_tutorial":
        if not message.text:
            await message.reply_text("❌ Please send a valid tutorial URL.", reply_markup=back_markup)
            await message.stop_propagation()
            return
        PENDING_INPUTS.pop(state_key, None)
        await cur_db.update_user_info(target_uid, {"how_to_download": message.text.strip()})
        await message.reply_text("✅ Successfully saved tutorial link!", reply_markup=back_markup)
        await message.stop_propagation()
        return

    if action == "set_force_channel":
        if not message.text:
            await message.reply_text("❌ Please send channel ID(s) separated by spaces.", reply_markup=back_markup)
            await message.stop_propagation()
            return
        PENDING_INPUTS.pop(state_key, None)
        target_client = await resolve_target_client(client, clone_bot_id)
        channel_ids = message.text.split()
        added_channels, failed_channels = [], []
        settings = await cur_db.get_user(target_uid)
        channels = list(settings.get("fsub_channels") or [])

        for ch_id in channel_ids:
            try:
                ch_int = int(ch_id)
                chat = await target_client.get_chat(ch_int)
                try:
                    await target_client.create_chat_invite_link(chat.id)
                except Exception:
                    failed_channels.append(f"{chat.title} (<code>{ch_int}</code>) - ❌ Bot is not admin")
                    continue
                if ch_int not in channels:
                    channels.append(ch_int)
                    added_channels.append(f"{chat.title} (<code>{ch_int}</code>) ✅")
            except Exception as e:
                failed_channels.append(f"<code>{ch_id}</code> - ❌ {str(e)}")

        await cur_db.update_user_info(target_uid, {"fsub_channels": channels})
        text = "<b>📢 Force Subscribe Update Result:</b>\n\n"
        if added_channels:
            text += "✅ Added:\n" + "\n".join(added_channels) + "\n\n"
        if failed_channels:
            text += "⚠️ Failed:\n" + "\n".join(failed_channels)
        await message.reply_text(text, reply_markup=back_markup)
        await message.stop_propagation()
        return

    if action == "set_log_channel":
        PENDING_INPUTS.pop(state_key, None)
        if not message.forward_from_chat or message.forward_from_chat.type != enums.ChatType.CHANNEL:
            await message.reply_text("❌ That message was not forwarded from a channel.", reply_markup=back_markup)
            await message.stop_propagation()
            return

        chat_id = message.forward_from_chat.id
        target_client = await resolve_target_client(client, clone_bot_id)
        try:
            chat = await target_client.get_chat(chat_id)
            t = await target_client.send_message(chat.id, "Test!")
            await t.delete()
        except Exception as e:
            await message.reply_text(f"❌ Something went wrong:\n\n<code>{e}</code>", reply_markup=back_markup)
            await message.stop_propagation()
            return

        await cur_db.update_user_info(target_uid, {"log_channel": chat.id})
        await message.reply_text(
            f"✅ Successfully added your log channel: <b>{chat.title}</b>",
            reply_markup=back_markup,
        )
        await message.stop_propagation()
        return
