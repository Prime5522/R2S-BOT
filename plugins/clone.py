import io
import re
import time
from bson.binary import Binary
from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from pyrogram.errors import UserNotParticipant
from config import (
    MAIN_BOT_USERNAME, MAX_CLONE_PER_USER, PICS,
    CLONE_CREATION_FSUB_CHANNEL, CLONE_CREATION_FSUB_INVITE,
    MODERATOR_DURATION_HOURS,
)
from Script import script
from database import get_db, get_clone_database
from database.clonedb import clone_db, has_clone_access, is_owner, active_moderators
from clone_manager import start_clone, stop_clone, restart_clone, delete_clone, change_clone_bot, RUNNING_CLONES
from utils import sc, format_duration, short_duration, resolve_user_ref, parse_duration, mod_expiry_ts, mod_left_text, mod_is_permanent
from bot_commands import set_staff_commands, clear_staff_commands
from plugins.send_file import MIN_AUTODELETE_SECONDS, MAX_AUTODELETE_SECONDS

# Per-(bot_id, user_id) input state store — completely isolated across users
PENDING_INPUTS: dict = {}

# ✨ মূল বট ও সব ক্লোনের স্টার্ট মেসেজে একই লেবেলের বাটন — ফন্ট প্রিমিয়াম স্টাইলে
CLONE_BTN_LABEL = sc("Create Your Own Clone")

DEFAULT_CLONE_START_TXT = (
    "<b>Hello {mention} 👋,\n\n"
    "Welcome to {bot_mention}!\n"
    "I am your personal File Storage Bot. 📁\n"
    "Send me any file, document, video, or audio and I will store it and generate a shareable link.\n\n"
    "👇 Use the buttons below to explore or create your own clone bot!</b>"
)


async def get_client_bot_id(client: Client) -> int:
    bot_id = getattr(client, "bot_id", None)
    if not bot_id:
        me = await client.get_me()
        bot_id = me.id
        client.bot_id = bot_id
        client.username = me.username
        client.mention = me.mention
        client.first_name = me.first_name
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


async def send_or_edit_text(
    target,
    text: str,
    reply_markup: InlineKeyboardMarkup = None,
    disable_web_page_preview: bool = True,
):
    """
    ✨ target হতে পারে একটা CallbackQuery (বাটনে ক্লিক করলে) অথবা সরাসরি একটা
    Message (যেমন কোনো টেক্সট পাঠানোর পর)। দুই ক্ষেত্রেই সঠিকভাবে কাজ করবে।
    """
    if isinstance(target, CallbackQuery):
        msg = target.message
        if msg.text:
            try:
                return await msg.edit_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=enums.ParseMode.HTML,
                    disable_web_page_preview=disable_web_page_preview,
                )
            except Exception:
                pass
        try:
            await msg.delete()
        except Exception:
            pass
        return await msg.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=disable_web_page_preview,
        )

    # target একটা সরাসরি Message (ইউজার কিছু পাঠানোর পর রিপ্লাই হিসেবে)
    return await target.reply_text(
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
    bot_mention = getattr(client, "mention", None)
    if not bot_mention:
        me = await client.get_me()
        bot_mention = me.mention
        client.bot_id = me.id
        client.username = me.username
        client.mention = me.mention
        client.first_name = me.first_name

    if getattr(client, "is_clone", False):
        start_pic = getattr(client, "custom_start_pic", None)
        start_pic_bytes = getattr(client, "custom_start_pic_bytes", None)
        # ✨ ওনার নিজে পিকচার সেট না করলে কোনো পিকচার দেখাবে না (মূল বটের পিকচার
        # আর ইনহেরিট হবে না) — শুধু টেক্সট আকারে /start দেখাবে, যতক্ষণ না ওনার
        # নিজে "Start Picture" থেকে একটা সেট করে।
        custom_txt = getattr(client, "custom_start_txt", None)
        template = custom_txt if custom_txt else DEFAULT_CLONE_START_TXT
        caption_text = format_start_text(template, user_mention, bot_mention)

        buttons = [
            [
                InlineKeyboardButton(sc("• Help •"), callback_data="help"),
                InlineKeyboardButton(sc("• About •"), callback_data="about"),
            ],
            [
                InlineKeyboardButton(
                    f"✨ {CLONE_BTN_LABEL}",
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

        return start_pic, start_pic_bytes, caption_text, InlineKeyboardMarkup(buttons)

    start_pic = PICS if PICS else None
    caption_text = format_start_text(script.START_TXT, user_mention, bot_mention)
    buttons = [
        [
            InlineKeyboardButton(sc("• Updates •"), url="https://t.me/PrimeXBots"),
            InlineKeyboardButton(sc("• Support •"), url="https://t.me/Prime_Support_group"),
        ],
        [
            InlineKeyboardButton(sc("• Help •"), callback_data="help"),
            InlineKeyboardButton(sc("• About •"), callback_data="about"),
        ],
        [
            InlineKeyboardButton(f"✨ {CLONE_BTN_LABEL}", callback_data="create_clone"),
        ],
    ]
    return start_pic, None, caption_text, InlineKeyboardMarkup(buttons)


async def send_start_reply_safely(
    client: Client,
    reply_target: Message,
    start_pic,
    start_pic_bytes,
    caption_text: str,
    reply_markup: InlineKeyboardMarkup,
):
    """
    ✨ পিকচার পাঠানো এখন bytes (raw) কে সবসময় প্রথমে ট্রাই করে — এতে কোনো
    পুরনো/ইনভ্যালিড file_id-র উপর নির্ভর করতে হয় না, তাই "পিকচার দেখাচ্ছে না"
    সমস্যাটা আর হবে না। file_id (start_pic) শুধু bytes না থাকলে fallback
    হিসেবে ব্যবহার হয় (পুরনো ডাটা/মূল বটের PICS এর জন্য)।
    """
    if start_pic_bytes:
        try:
            raw = bytes(start_pic_bytes)
            bio = io.BytesIO(raw)
            bio.name = "start.jpg"
            return await reply_target.reply_photo(
                photo=bio,
                caption=caption_text,
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            pass  # bytes দিয়ে না হলে নিচে file_id দিয়ে ট্রাই করবে

    if start_pic:
        try:
            return await reply_target.reply_photo(
                photo=start_pic,
                caption=caption_text,
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            pass  # file_id টাও কাজ না করলে নিচে টেক্সট হিসেবে পাঠাবে

    return await reply_target.reply_text(
        text=caption_text,
        reply_markup=reply_markup,
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True,
    )


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


# ================= ✨ CLONE-CREATION FORCE SUBSCRIBE (main bot only) ✨ =================
# এটা ক্লোন ওনারের নিজের fsub সেটিং থেকে আলাদা — এটা শুধু মূল বটে নতুন ক্লোন
# তৈরি করার সময়(টোকেন জমা দেওয়ার সময়) চেক হয়, /start কে ব্লক করে না।

async def _is_fsub_member(client: Client, channel_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(channel_id, user_id)
        return member.status not in (enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED)
    except UserNotParticipant:
        return False
    except Exception:
        # চ্যানেল আইডি ভুল/বট অ্যাডমিন না থাকলে চেকটা স্কিপ করে দেয় (ইউজারকে আটকায় না)
        return True


async def _get_fsub_invite_link(client: Client, channel_id: int) -> str:
    if CLONE_CREATION_FSUB_INVITE:
        return CLONE_CREATION_FSUB_INVITE
    try:
        chat = await client.get_chat(channel_id)
        if chat.username:
            return f"https://t.me/{chat.username}"
    except Exception:
        pass
    try:
        return await client.export_chat_invite_link(channel_id)
    except Exception:
        return "https://t.me/"


async def _finalize_clone_creation(client: Client, reply_target, user_id: int, token: str, owner_mention: str):
    wait_msg = await reply_target.reply_text("<i>⏳ Verifying token and starting your clone bot, please wait...</i>")
    try:
        me = await start_clone(token, user_id, owner_mention=owner_mention)
    except Exception as e:
        await wait_msg.edit_text(
            f"❌ <b>Failed to create clone:</b>\n<code>{e}</code>\n\n"
            "Please check your BotFather token and try again with /clone.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="start")]]),
        )
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


# মডারেটরের সময়সীমা বর্ণনা (0 = স্থায়ী)
if MODERATOR_DURATION_HOURS <= 0:
    MOD_FOR_TXT = " — <b>with no time limit</b> (until you remove them)."
else:
    MOD_FOR_TXT = f" for <b>{format_duration(MODERATOR_DURATION_HOURS * 3600)}</b>, then it ends automatically."


async def start_creation_flow(client: Client, target, is_callback: bool):
    user_id = target.from_user.id
    await clear_pending_input(client, user_id)
    back_cb = "start" if is_callback else "close_data"
    await set_pending_input(client, user_id, action="awaiting_botfather_forward", back_cb=back_cb)

    text = (
        "<b>✨ Create Your Own Clone Bot</b>\n\n"
        "Follow these quick steps to create your personal File Store Bot:\n\n"
        "1️⃣ Open @BotFather and create a new bot with <code>/newbot</code> (or open an existing bot's token message).\n"
        "2️⃣ <b>Forward</b> the message containing the Bot Token from @BotFather directly to this chat.\n\n"
        "⚠️ <i>Do not send the token as plain text — you must forward the original message from @BotFather.</i>\n\n"
        "Send /cancel anytime to cancel."
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="clone_cancel_input")]])
    if is_callback:
        return await send_or_edit_text(target, text, markup)
    return await target.reply_text(text, reply_markup=markup, disable_web_page_preview=True)


async def show_moderated_list(target, clones: list, is_callback: bool):
    """যে ইউজারের নিজের ক্লোন নেই কিন্তু অন্য ক্লোনের মডারেটর — তার জন্য লিস্ট"""
    now = time.time()
    text = "<b>👮 You are a moderator</b>\n\nYou have temporary full access to these clone bots:\n"
    buttons = []
    uid = target.from_user.id
    for c in clones:
        mod = next((m for m in active_moderators(c) if int(m["user_id"]) == int(uid)), None)
        left = mod_left_text(mod["expires_at"]) if mod else "—"
        text += f"\n• @{c.get('bot_username')} — ⏳ {left}"
        buttons.append([InlineKeyboardButton(sc(f"⚙️ Manage @{c.get('bot_username')}"), callback_data=f"manage_clone#{c['bot_id']}")])
    buttons.append([InlineKeyboardButton(f"✨ {CLONE_BTN_LABEL}", callback_data="clone_create_new")])
    buttons.append([InlineKeyboardButton("« Back", callback_data="start")])
    markup = InlineKeyboardMarkup(buttons)
    if is_callback:
        return await send_or_edit_text(target, text, markup)
    return await target.reply_text(text, reply_markup=markup, disable_web_page_preview=True)


async def send_clone_entry(client: Client, target, is_callback: bool = False):
    user_id = target.from_user.id

    if getattr(client, "is_clone", False):
        text = (
            f"<b>✨ {CLONE_BTN_LABEL}</b>\n\n"
            "Clone creation and customization are managed on our main bot.\n"
            "Click the button below to continue:"
        )
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton(sc("🚀 Open Clone Panel"), url=f"https://t.me/{MAIN_BOT_USERNAME}?start=clone")]]
        )
        if is_callback:
            return await send_or_edit_text(target, text, markup)
        return await target.reply_text(text, reply_markup=markup, disable_web_page_preview=True)

    await clear_pending_input(client, user_id)
    existing = await clone_db.get_user_clone(user_id)

    if existing:
        # ✨ আগে থেকেই ক্লোন থাকলে এক্সট্রা ক্লিক ছাড়াই সরাসরি কাস্টমাইজ প্যানেলে নিয়ে যাওয়া হয়
        return await show_manage_clone_panel(target, existing, is_callback=is_callback)

    # ✨ অন্য কারো ক্লোনের (মেয়াদ-থাকা) মডারেটর হলে সেই প্যানেল
    moderated = await clone_db.get_moderated_clones(user_id)
    if moderated:
        if len(moderated) == 1:
            return await show_manage_clone_panel(target, moderated[0], is_callback=is_callback)
        return await show_moderated_list(target, moderated, is_callback)

    return await start_creation_flow(client, target, is_callback)


async def _get_owner_settings(clone_doc: dict):
    clone_user_db = get_clone_database(int(clone_doc["bot_id"]), clone_doc["db_name"])
    owner_settings = await clone_user_db.get_user(int(clone_doc["owner_id"]))
    return clone_user_db, owner_settings


async def show_manage_clone_panel(target, clone_doc: dict, is_callback: bool = True):
    bot_id = clone_doc["bot_id"]
    owner_id = int(clone_doc["owner_id"])
    viewer_id = int(target.from_user.id)
    viewer_is_owner = viewer_id == owner_id
    bot_username = clone_doc.get("bot_username") or "Unknown"
    status = clone_doc.get("status", "active")
    status_label = "✅ Active" if status == "active" else "⛔ Inactive"
    toggle_label = "⛔ Deactivate" if status == "active" else "✅ Activate"

    _, owner_settings = await _get_owner_settings(clone_doc)
    protect_on = bool(owner_settings.get("protect_content", False))
    autodel_on = bool(owner_settings.get("auto_delete", True))

    text = (
        f"<b>💎 {sc('Clone Control Panel')}</b>\n"
        "<code>━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"🤖 <b>{sc('Bot')}:</b> @{bot_username}\n"
        f"{'🟢' if status == 'active' else '🔴'} <b>{sc('Status')}:</b> {status_label}\n"
        "<code>━━━━━━━━━━━━━━━━━━━━</code>\n\n"
        f"<blockquote>✨ {sc('Your clone is a fully independent bot with its own database. Tap a category below to customize every part of it.')}</blockquote>\n\n"
        f"🎨 {sc('Start Screen')}  •  📝 {sc('Caption')}  •  🔗 {sc('Shortener')}\n"
        f"📢 {sc('Force Sub')}  •  ⏱ {sc('Auto Delete')}  •  👮 {sc('Moderators')}"
    )
    if not viewer_is_owner:
        mod = next((m for m in active_moderators(clone_doc) if int(m["user_id"]) == viewer_id), None)
        if mod:
            if mod_is_permanent(mod["expires_at"]):
                text += "\n\n👮 <i>You are a moderator of this bot.</i>"
            else:
                text += (
                "\n\n👮 <i>You are a moderator of this bot.</i>" if mod_is_permanent(mod["expires_at"])
                else f"\n\n👮 <i>You are a temporary moderator — {mod_left_text(mod['expires_at'])}.</i>"
            )

    sfx = f"{owner_id}#{bot_id}"
    buttons = [
        [InlineKeyboardButton(sc("🎨 Start Screen (Picture / Message / Buttons)"), callback_data=f"clone_appearance#{bot_id}")],
        [
            InlineKeyboardButton(sc("📄 About Page"), callback_data=f"clone_about_view#{bot_id}"),
            InlineKeyboardButton(sc("❓ Help Page"), callback_data=f"clone_help_view#{bot_id}"),
        ],
        [InlineKeyboardButton(sc("📎 File Delivery Buttons"), callback_data=f"clone_filebtns_view#{bot_id}")],
        [
            InlineKeyboardButton(sc("📝 File Caption"), callback_data=f"caption_setgs#{sfx}"),
            InlineKeyboardButton(
                sc(f"🛡 Protect: {'ON ✅' if protect_on else 'OFF ❌'}"),
                callback_data=f"clone_quick_protect#{bot_id}",
            ),
        ],
        # ✨ Verify Settings ও Tutorial এখন Shortener-এর ভিতরে
        [
            InlineKeyboardButton(sc("🔗 Shortener Link"), callback_data=f"shortlink_setgs#{sfx}"),
            InlineKeyboardButton(sc("📢 Force Subscribe"), callback_data=f"force_channel_setgs#{sfx}"),
        ],
        [
            InlineKeyboardButton(sc("📜 Log Channel"), callback_data=f"log_channel_setgs#{sfx}"),
            InlineKeyboardButton(sc("🔗 Permanent Link"), callback_data=f"permanent_link_setgs#{sfx}"),
        ],
        [
            InlineKeyboardButton(sc(f"⏱ Auto Delete: {'ON ✅' if autodel_on else 'OFF ❌'}"), callback_data=f"autodelete_setgs#{sfx}"),
        ],
        [
            InlineKeyboardButton(sc("📊 Status"), callback_data=f"clone_status#{bot_id}"),
        ],
    ]
    if viewer_is_owner:
        buttons[-1].append(InlineKeyboardButton(sc("👮 Moderator"), callback_data=f"clone_mods#{bot_id}"))
    buttons += [
        [
            InlineKeyboardButton(sc("📑 Full Details"), callback_data=f"clone_details#{bot_id}"),
            InlineKeyboardButton(sc("🔄 Reset All"), callback_data=f"clone_reset#{bot_id}"),
        ],
        # ✨ Restart / Deactivate / Delete / Change Bot — সব এই এক বাটনের ভিতরে
        [InlineKeyboardButton(sc("⚙️ Clone Bot Control"), callback_data=f"clone_control#{bot_id}")],
        # Back সরাসরি Home-এ যায় (আগে "clone_card"-এ যেত যা একই প্যানেল আবার খুলত)
        [InlineKeyboardButton(sc("« Back"), callback_data="start")],
    ]

    markup = InlineKeyboardMarkup(buttons)
    if is_callback:
        return await send_or_edit_text(target, text, markup)
    return await target.reply_text(text, reply_markup=markup, disable_web_page_preview=True)


# ================= ✨ BOT CONTROL ✨ =================

async def show_control_view(target, clone_doc: dict):
    bot_id = clone_doc["bot_id"]
    viewer_is_owner = is_owner(clone_doc, target.from_user.id)
    active = clone_doc.get("status", "active") == "active"
    text = (
        f"<b>⚙️ {sc('Bot Control')}</b>\n"
        "<code>━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"🤖 @{clone_doc.get('bot_username')}  •  {'🟢 Active' if active else '🔴 Inactive'}\n"
        "<code>━━━━━━━━━━━━━━━━━━━━</code>\n\n"
        f"<blockquote>🔁 <b>Restart</b> — {sc('refresh the bot')}\n"
        f"{'⛔ <b>Deactivate</b>' if active else '✅ <b>Activate</b>'} — {sc('turn the bot off / on')}\n"
    )
    if viewer_is_owner:
        text += (
            f"🔄 <b>Change Bot</b> — {sc('move everything to a new bot token')}\n"
            f"🗑 <b>Delete Clone</b> — {sc('remove this clone forever')}"
        )
    text += "</blockquote>"

    buttons = [[
        InlineKeyboardButton(sc("🔁 Restart"), callback_data=f"clone_restart#{bot_id}"),
        InlineKeyboardButton(sc("⛔ Deactivate" if active else "✅ Activate"), callback_data=f"clone_toggle#{bot_id}"),
    ]]
    if viewer_is_owner:
        buttons.append([InlineKeyboardButton(sc("🔄 Change Bot"), callback_data=f"clone_changebot#{bot_id}")])
        buttons.append([InlineKeyboardButton(sc("🗑 Delete Clone"), callback_data=f"clone_delete#{bot_id}")])
    buttons.append([InlineKeyboardButton(sc("« Back"), callback_data=f"manage_clone#{bot_id}")])
    return await send_or_edit_text(target, text, InlineKeyboardMarkup(buttons))


# ================= ✨ STORAGE CHANNEL ✨ =================

async def show_storage_view(target, clone_doc: dict):
    bot_id = clone_doc["bot_id"]
    owner_id = clone_doc["owner_id"]
    channel = clone_doc.get("storage_channel")
    text = (
        f"<b>📦 {sc('Storage Channel')}</b>\n"
        "<code>━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"<b>Status:</b> {'Connected ✅' if channel else 'Not set ⚠️'}"
        + (f"\n<b>Channel ID:</b> <code>{channel}</code>" if channel else "")
        + "\n<code>━━━━━━━━━━━━━━━━━━━━</code>\n\n"
        "<blockquote>Your files are saved in this private channel. If your bot is ever banned, "
        "connect a new bot to the same channel and your links keep working.</blockquote>\n\n"
        "<b>How to set it up:</b>\n"
        "1️⃣ Create a <b>private channel</b>\n"
        f"2️⃣ Add @{clone_doc.get('bot_username')} as <b>admin</b> (Post Messages)\n"
        "3️⃣ Tap <b>Set Channel</b> and forward any message from that channel"
    )
    buttons = [[InlineKeyboardButton(sc("📌 Change Channel" if channel else "📌 Set Channel"), callback_data=f"clone_storage_set#{bot_id}")]]
    if channel:
        buttons.append([InlineKeyboardButton(sc("🗑 Remove Channel"), callback_data=f"clone_storage_rm#{bot_id}")])
    buttons.append([InlineKeyboardButton(sc("« Back"), callback_data=f"permanent_link_setgs#{owner_id}#{bot_id}")])
    return await send_or_edit_text(target, text, InlineKeyboardMarkup(buttons))


# ================= ✨ STATUS (popup) ✨ =================

async def build_status_popup(clone_doc: dict) -> str:
    """টেলিগ্রাম অ্যালার্ট পপ-আপের সীমা ২০০ অক্ষর — তাই ছোট করে সাজানো"""
    bot_id = int(clone_doc["bot_id"])
    running = RUNNING_CLONES.get(bot_id)
    cdb = get_clone_database(bot_id, clone_doc["db_name"])
    owner_settings = await cdb.get_user(int(clone_doc["owner_id"]))

    users = await cdb.total_users_count()
    links = await cdb.files.count_documents({})
    banned = await cdb.banned_count()
    mods = len(active_moderators(clone_doc))

    online = "🟢 Online" if running else "🔴 Offline"
    state = "Active" if clone_doc.get("status") == "active" else "Inactive"
    uptime = short_duration(time.time() - running.started_at) if running and getattr(running, "started_at", None) else "—"
    ad = f"{short_duration(owner_settings.get('auto_delete_time') or 300)}" if owner_settings.get("auto_delete", True) else "OFF"

    text = (
        f"📊 @{clone_doc.get('bot_username')}\n"
        f"{online} • {state}\n"
        f"⏱ Uptime: {uptime}\n"
        f"👥 Users: {users}  🔗 Links: {links}\n"
        f"🚫 Banned: {banned}  👮 Mods: {mods}\n"
        f"🗑 Auto Delete: {ad}"
    )
    return text[:200]


# ================= ✨ MODERATOR PANEL ✨ =================

async def show_mods_view(target, clone_doc: dict):
    bot_id = clone_doc["bot_id"]
    mods = active_moderators(clone_doc)
    now = time.time()

    text = (
        "<b>👮 Moderators</b>\n\n"
        f"A moderator gets <b>full access</b> to manage this clone{MOD_FOR_TXT}"
        "<i>(Only you can add/remove moderators, transfer or delete the clone.)</i>\n"
    )
    if mods:
        text += "\n<b>Active moderators:</b>\n"
        for m in mods:
            text += f"• <a href='tg://user?id={m['user_id']}'>{m.get('name') or m['user_id']}</a> (<code>{m['user_id']}</code>) — ⏳ {mod_left_text(m['expires_at'])}\n"
    else:
        text += "\nNo active moderators."

    buttons = [
        [
            InlineKeyboardButton(sc("➕ Add"), callback_data=f"clone_modadd#{bot_id}"),
            InlineKeyboardButton(sc("➖ Remove"), callback_data=f"clone_modrm_list#{bot_id}"),
        ],
        [InlineKeyboardButton(sc("🔄 Transfer Ownership"), callback_data=f"clone_transfer#{bot_id}")],
        [InlineKeyboardButton(sc("« Back"), callback_data=f"manage_clone#{bot_id}")],
    ]
    return await send_or_edit_text(target, text, InlineKeyboardMarkup(buttons))


async def show_mod_remove_list(target, clone_doc: dict):
    bot_id = clone_doc["bot_id"]
    mods = active_moderators(clone_doc)
    back = f"clone_mods#{bot_id}"
    if not mods:
        return await send_or_edit_text(
            target, "<b>➖ Remove Moderator</b>\n\nThere are no active moderators to remove.",
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=back)]]),
        )
    buttons = [
        [InlineKeyboardButton(f"❌ {m.get('name') or m['user_id']} ({m['user_id']})", callback_data=f"clone_modrm#{bot_id}#{m['user_id']}")]
        for m in mods
    ]
    if len(mods) > 1:
        buttons.append([InlineKeyboardButton("🗑 Remove All", callback_data=f"clone_modrm#{bot_id}#all")])
    buttons.append([InlineKeyboardButton("« Back", callback_data=back)])
    return await send_or_edit_text(
        target, "<b>➖ Remove Moderator</b>\n\nTap a moderator to remove their access right now:",
        InlineKeyboardMarkup(buttons),
    )


async def _refresh_running_mods(bot_id: int):
    running = RUNNING_CLONES.get(int(bot_id))
    if running:
        doc = await clone_db.get_clone(bot_id)
        running.moderators = (doc or {}).get("moderators") or []
    return running


# ================= ✨ START APPEARANCE SUB-MENU ✨ =================

async def show_appearance_menu(target, clone_doc: dict):
    bot_id = clone_doc["bot_id"]
    has_msg = bool(clone_doc.get("start_msg"))
    has_pic = bool(clone_doc.get("start_pic") or clone_doc.get("start_pic_bytes"))
    saved_btns = clone_doc.get("start_buttons") or []
    btn_count = sum(len(r) for r in saved_btns)

    text = (
        f"<b>🎨 {sc('Start Screen')}</b>\n\n"
        f"{sc('This is exactly what a user sees the moment they press')} <code>/start</code> "
        f"{sc('on your clone bot — the picture, the welcome text, and any extra buttons below it.')}\n\n"
        f"🖼 <b>{sc('Picture')}:</b> {sc('Set ✅') if has_pic else sc('Default')}\n"
        f"📝 <b>{sc('Welcome Message')}:</b> {sc('Custom ✅') if has_msg else sc('Default')}\n"
        f"🔘 <b>{sc('Extra Buttons')}:</b> {btn_count} {sc('set')}\n\n"
        f"👇 {sc('Tap a section below to view, change or delete it:')}"
    )
    buttons = [
        [InlineKeyboardButton(sc("🖼 Start Picture"), callback_data=f"clone_viewpic#{bot_id}")],
        [InlineKeyboardButton(sc("📝 Welcome Message"), callback_data=f"clone_viewmsg#{bot_id}")],
        [InlineKeyboardButton(sc("🔘 Extra Buttons"), callback_data=f"clone_viewbtns#{bot_id}")],
        [InlineKeyboardButton(sc("« Back"), callback_data=f"manage_clone#{bot_id}")],
    ]
    return await send_or_edit_text(target, text, InlineKeyboardMarkup(buttons))


async def show_pic_view(client: Client, target, clone_doc: dict):
    bot_id = clone_doc["bot_id"]
    pic = clone_doc.get("start_pic")
    pic_bytes = clone_doc.get("start_pic_bytes")
    back_cb = f"clone_appearance#{bot_id}"
    chat_id = target.message.chat.id if isinstance(target, CallbackQuery) else target.chat.id

    if pic or pic_bytes:
        buttons = [
            [InlineKeyboardButton("🖼 Change Picture", callback_data=f"clone_setpic#{bot_id}")],
            [InlineKeyboardButton("🗑 Delete Picture", callback_data=f"clone_delpic#{bot_id}")],
            [InlineKeyboardButton("« Back", callback_data=back_cb)],
        ]
        caption = "<b>🖼 Current Start Picture</b>\n\nThis is the photo shown on <code>/start</code>."
        if isinstance(target, CallbackQuery):
            try:
                await target.message.delete()
            except Exception:
                pass
        if pic:
            return await client.send_photo(chat_id, photo=pic, caption=caption, reply_markup=InlineKeyboardMarkup(buttons))
        bio = io.BytesIO(bytes(pic_bytes))
        bio.name = "start.jpg"
        return await client.send_photo(chat_id, photo=bio, caption=caption, reply_markup=InlineKeyboardMarkup(buttons))

    text = "<b>🖼 Start Picture</b>\n\nNo custom picture set — your clone is using the default picture."
    buttons = [
        [InlineKeyboardButton("🖼 Set Start Picture", callback_data=f"clone_setpic#{bot_id}")],
        [InlineKeyboardButton("« Back", callback_data=back_cb)],
    ]
    return await send_or_edit_text(target, text, InlineKeyboardMarkup(buttons))


async def show_msg_view(target, clone_doc: dict):
    bot_id = clone_doc["bot_id"]
    msg = clone_doc.get("start_msg")
    back_cb = f"clone_appearance#{bot_id}"

    if msg:
        text = f"<b>📝 Current Start Message</b>\n\n<blockquote>{msg}</blockquote>"
        buttons = [
            [InlineKeyboardButton("✏️ Edit Message", callback_data=f"clone_setmsg#{bot_id}")],
            [InlineKeyboardButton("♻️ Reset to Default", callback_data=f"clone_delmsg#{bot_id}")],
            [InlineKeyboardButton("« Back", callback_data=back_cb)],
        ]
    else:
        text = "<b>📝 Start Message</b>\n\nNo custom message set — your clone is using the default welcome text."
        buttons = [
            [InlineKeyboardButton("📝 Set Start Message", callback_data=f"clone_setmsg#{bot_id}")],
            [InlineKeyboardButton("« Back", callback_data=back_cb)],
        ]
    return await send_or_edit_text(target, text, InlineKeyboardMarkup(buttons))


async def show_btns_view(target, clone_doc: dict):
    bot_id = clone_doc["bot_id"]
    saved_rows = clone_doc.get("start_buttons") or []
    back_cb = f"clone_appearance#{bot_id}"

    text = "<b>🔘 Start Buttons</b>\n\nThese appear below your clone's default Home buttons.\n"
    buttons = []
    if saved_rows:
        text += "\n👇 <i>Live preview is below — tap Edit or Clear to change them.</i>"
        for row in saved_rows:
            btn_row = [InlineKeyboardButton(b["text"], url=b["url"]) for b in row if b.get("text") and b.get("url")]
            if btn_row:
                buttons.append(btn_row)
        buttons.append([InlineKeyboardButton("✏️ Edit Buttons", callback_data=f"clone_setbtns#{bot_id}")])
        buttons.append([InlineKeyboardButton("🗑 Clear All", callback_data=f"clone_delbtns#{bot_id}")])
    else:
        text += "\nNo extra buttons set yet."
        buttons.append([InlineKeyboardButton("🔘 Set Start Buttons", callback_data=f"clone_setbtns#{bot_id}")])
    buttons.append([InlineKeyboardButton("« Back", callback_data=back_cb)])
    return await send_or_edit_text(target, text, InlineKeyboardMarkup(buttons))


# ================= ✨ ABOUT / HELP CUSTOMIZATION ✨ =================

async def show_about_view(target, clone_doc: dict):
    bot_id = clone_doc["bot_id"]
    about = clone_doc.get("about_text")
    back_cb = f"manage_clone#{bot_id}"

    text = (
        "<b>📄 About Page</b>\n\n"
        "You can customize the top part of your bot's About page.\n"
        f"⚠️ <i>Note: the line \"Cʟᴏɴᴇ Fʀᴏᴍ: @{MAIN_BOT_USERNAME}\" always stays at the bottom and cannot be removed.</i>\n"
    )
    if about:
        text += f"\n<b>Current custom text:</b>\n<blockquote>{about}</blockquote>"
        buttons = [
            [InlineKeyboardButton("✏️ Edit About Text", callback_data=f"clone_setabout#{bot_id}")],
            [InlineKeyboardButton("♻️ Reset to Default", callback_data=f"clone_delabout#{bot_id}")],
            [InlineKeyboardButton("« Back", callback_data=back_cb)],
        ]
    else:
        text += "\nUsing the default About text right now."
        buttons = [
            [InlineKeyboardButton("📝 Set Custom About Text", callback_data=f"clone_setabout#{bot_id}")],
            [InlineKeyboardButton("« Back", callback_data=back_cb)],
        ]
    return await send_or_edit_text(target, text, InlineKeyboardMarkup(buttons))


async def show_help_view(target, clone_doc: dict):
    bot_id = clone_doc["bot_id"]
    help_txt = clone_doc.get("help_text")
    back_cb = f"manage_clone#{bot_id}"

    text = "<b>❓ Help Page</b>\n\nCustomize what users see when they tap \"Help\" on your clone bot.\n"
    if help_txt:
        text += f"\n<b>Current custom text:</b>\n<blockquote>{help_txt}</blockquote>"
        buttons = [
            [InlineKeyboardButton("✏️ Edit Help Text", callback_data=f"clone_sethelp#{bot_id}")],
            [InlineKeyboardButton("♻️ Reset to Default", callback_data=f"clone_delhelp#{bot_id}")],
            [InlineKeyboardButton("« Back", callback_data=back_cb)],
        ]
    else:
        text += "\nUsing the default Help text right now."
        buttons = [
            [InlineKeyboardButton("📝 Set Custom Help Text", callback_data=f"clone_sethelp#{bot_id}")],
            [InlineKeyboardButton("« Back", callback_data=back_cb)],
        ]
    return await send_or_edit_text(target, text, InlineKeyboardMarkup(buttons))


# ================= ✨ FILE DELIVERY BUTTONS ✨ =================

async def show_filebtns_view(target, clone_doc: dict):
    bot_id = clone_doc["bot_id"]
    saved_rows = clone_doc.get("file_buttons") or []
    back_cb = f"manage_clone#{bot_id}"

    text = (
        "<b>📎 File Delivery Buttons</b>\n\n"
        "ᴛʜᴇsᴇ ʙᴜᴛᴛᴏɴs ᴀᴘᴘᴇᴀʀ ᴜɴᴅᴇʀ ᴇᴠᴇʀʏ ꜰɪʟᴇ ʏᴏᴜʀ ʙᴏᴛ ᴅᴇʟɪᴠᴇʀs ᴛᴏ ᴜsᴇʀs\n"
        "<i>(not on the /start message — a separate thing from Start Buttons).</i>\n"
    )
    buttons = []
    if saved_rows:
        text += "\n👇 <i>Live preview below:</i>"
        for row in saved_rows:
            btn_row = [InlineKeyboardButton(b["text"], url=b["url"]) for b in row if b.get("text") and b.get("url")]
            if btn_row:
                buttons.append(btn_row)
        buttons.append([InlineKeyboardButton("✏️ Edit Buttons", callback_data=f"clone_setfilebtns#{bot_id}")])
        buttons.append([InlineKeyboardButton("🗑 Clear All", callback_data=f"clone_delfilebtns#{bot_id}")])
    else:
        text += "\nNo file-delivery buttons set yet."
        buttons.append([InlineKeyboardButton("🔘 Set File Buttons", callback_data=f"clone_setfilebtns#{bot_id}")])
    buttons.append([InlineKeyboardButton("« Back", callback_data=back_cb)])
    return await send_or_edit_text(target, text, InlineKeyboardMarkup(buttons))


# ================= ✨ FULL DETAILS ✨ =================

async def show_clone_details(target, clone_doc: dict):
    bot_id = clone_doc["bot_id"]
    bot_username = clone_doc.get("bot_username") or "Unknown"
    status = clone_doc.get("status", "active")
    owner_mention = clone_doc.get("owner_mention") or f"<code>{clone_doc.get('owner_id')}</code>"

    _, owner_settings = await _get_owner_settings(clone_doc)

    has_msg = clone_doc.get("start_msg")
    has_pic = bool(clone_doc.get("start_pic") or clone_doc.get("start_pic_bytes"))
    start_btn_count = sum(len(r) for r in (clone_doc.get("start_buttons") or []))
    file_btn_count = sum(len(r) for r in (clone_doc.get("file_buttons") or []))
    has_about = bool(clone_doc.get("about_text"))
    has_help = bool(clone_doc.get("help_text"))

    text = (
        f"<b>📑 Full Clone Details</b>\n\n"
        f"🤖 <b>Bot:</b> @{bot_username} (<code>{bot_id}</code>)\n"
        f"👤 <b>Owner:</b> {owner_mention}\n"
        f"📌 <b>Status:</b> {'✅ Active' if status == 'active' else '⛔ Inactive'}\n\n"
        f"<b>🎨 Start Screen:</b>\n"
        f"• Picture: {'Set ✅' if has_pic else 'Default'}\n"
        f"• Message: {'Custom ✅ — ' + has_msg[:60] + ('...' if len(has_msg) > 60 else '') if has_msg else 'Default'}\n"
        f"• Extra Buttons: {start_btn_count}\n\n"
        f"<b>📄 Pages:</b>\n"
        f"• About: {'Custom ✅' if has_about else 'Default'}  |  Help: {'Custom ✅' if has_help else 'Default'}\n\n"
        f"<b>📎 File Delivery:</b>\n"
        f"• Buttons attached to every file: {file_btn_count}\n\n"
        f"<b>⚙️ File &amp; Bot Settings:</b>\n"
        f"• Caption: {'Custom' if owner_settings.get('custom_caption') else 'Default'}\n"
        f"• Protect Content: {'ON ✅' if owner_settings.get('protect_content') else 'OFF ❌'}\n"
        f"• Shortener: {'Set' if owner_settings.get('shortener_api') else 'None'}\n"
        f"• Verification: {'ON' if owner_settings.get('verify') else 'OFF'}\n"
        f"• Force Sub Channels: {len(owner_settings.get('fsub_channels') or [])}\n"
        f"• Log Channel: {'Set' if owner_settings.get('log_channel') else 'None'}\n"
        f"• Permanent Link Mode: {'ON' if owner_settings.get('permanent_link_mode') else 'OFF'}\n"
        f"• Auto Delete: {format_duration(owner_settings.get('auto_delete_time') or 300) if owner_settings.get('auto_delete', True) else 'OFF'}\n"
        f"• Active Moderators: {len(active_moderators(clone_doc))}\n"
    )
    buttons = [[InlineKeyboardButton("« Back", callback_data=f"manage_clone#{bot_id}")]]
    return await send_or_edit_text(target, text, InlineKeyboardMarkup(buttons))


@Client.on_message(filters.command("clone") & filters.private)
async def clone_command(client: Client, message: Message):
    return await send_clone_entry(client, message, is_callback=False)


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

    if data == "clone_fsub_recheck":
        bot_id = await get_client_bot_id(client)
        state_key = (bot_id, user_id)
        state = PENDING_INPUTS.get(state_key)
        pending_token = (state or {}).get("data", {}).get("pending_token")

        if not pending_token:
            await query.answer("⚠️ No pending clone creation found. Please start again with /clone.", show_alert=True)
            return True

        if CLONE_CREATION_FSUB_CHANNEL:
            is_member = await _is_fsub_member(client, CLONE_CREATION_FSUB_CHANNEL, user_id)
            if not is_member:
                await query.answer("❌ You haven't joined the channel yet!", show_alert=True)
                return True

        owner_mention = state["data"].get("pending_owner_mention") or query.from_user.mention
        PENDING_INPUTS.pop(state_key, None)
        await query.answer("✅ Verified! Creating your clone...")
        await _finalize_clone_creation(client, query.message, user_id, pending_token, owner_mention)
        return True

    if data.startswith("manage_clone#"):
        bot_id = int(data.split("#")[1])
        await clear_pending_input(client, user_id)
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ This clone does not belong to you.", show_alert=True)
            return True
        await show_manage_clone_panel(query, clone_doc, is_callback=True)
        return True

    if data.startswith("clone_quick_protect#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        clone_user_db = get_clone_database(bot_id, clone_doc["db_name"])
        owner_settings = await clone_user_db.get_user(user_id)
        new_val = not bool(owner_settings.get("protect_content", False))
        await clone_user_db.update_user_info(user_id, {"protect_content": new_val})
        await query.answer(f"🛡 Content Protection is now {'ON' if new_val else 'OFF'}")
        await show_manage_clone_panel(query, clone_doc, is_callback=True)
        return True

    if data.startswith("clone_setmsg#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True

        await set_pending_input(
            client,
            user_id,
            action="clone_setmsg",
            back_cb=f"clone_viewmsg#{bot_id}",
            data={"bot_id": bot_id},
        )
        current_msg = clone_doc.get("start_msg")
        current_info = f"\n<b>Current Message:</b>\n<blockquote>{current_msg}</blockquote>\n" if current_msg else ""
        text = (
            "<b>📝 Send Your Custom Start Message</b>\n"
            f"{current_info}\n"
            "HTML formatting is supported.\n"
            "Optional placeholders:\n"
            "• <code>{mention}</code> or <code>{}</code> — User's clickable name\n"
            "• <code>{bot_mention}</code> — Your bot's name\n\n"
            "Send /cancel to cancel."
        )
        await send_or_edit_text(
            query,
            text,
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=f"clone_viewmsg#{bot_id}")]]),
        )
        return True

    if data.startswith("clone_delmsg#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
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
        await show_msg_view(query, clone_doc)
        return True

    if data.startswith("clone_setpic#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True

        await set_pending_input(
            client,
            user_id,
            action="clone_setpic",
            back_cb=f"clone_viewpic#{bot_id}",
            data={"bot_id": bot_id},
        )
        text = (
            "<b>🖼 Send Your Start Picture</b>\n\n"
            "Send the photo you want to show when users press /start in your clone bot.\n\n"
            "Send /cancel to cancel."
        )
        await send_or_edit_text(
            query,
            text,
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=f"clone_viewpic#{bot_id}")]]),
        )
        return True

    if data.startswith("clone_delpic#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        if not (clone_doc.get("start_pic") or clone_doc.get("start_pic_bytes")):
            await query.answer("ℹ️ No start picture is currently set.", show_alert=True)
            return True

        await clone_db.update_clone_settings(bot_id, {"start_pic": None, "start_pic_bytes": None})
        running = RUNNING_CLONES.get(bot_id)
        if running:
            running.custom_start_pic = None
            running.custom_start_pic_bytes = None
        await query.answer("✅ Start picture removed!", show_alert=True)
        clone_doc = await clone_db.get_clone(bot_id)
        await show_pic_view(client, query, clone_doc)
        return True

    if data.startswith("clone_setbtns#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True

        await set_pending_input(
            client,
            user_id,
            action="clone_setbtns",
            back_cb=f"clone_viewbtns#{bot_id}",
            data={"bot_id": bot_id},
        )
        text = (
            "<b>🔘 Send Your Custom Start Buttons</b>\n\n"
            "These buttons will appear <b>below</b> your clone bot's default buttons.\n\n"
            "<b>Format</b> (one row per line, use <code>|</code> for multiple buttons in one row):\n"
            "<code>Updates Channel - https://t.me/PrimeXBots</code>\n"
            "<code>Support Group - https://t.me/Prime_Support_group</code>\n\n"
            "Send /cancel to cancel."
        )
        await send_or_edit_text(
            query,
            text,
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=f"clone_viewbtns#{bot_id}")]]),
        )
        return True

    if data.startswith("clone_delbtns#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
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
        await show_btns_view(query, clone_doc)
        return True

    if data.startswith("clone_appearance#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        await clear_pending_input(client, user_id)
        await show_appearance_menu(query, clone_doc)
        return True

    if data.startswith("clone_viewpic#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        await show_pic_view(client, query, clone_doc)
        return True

    if data.startswith("clone_viewmsg#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        await show_msg_view(query, clone_doc)
        return True

    if data.startswith("clone_viewbtns#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        await show_btns_view(query, clone_doc)
        return True

    if data.startswith("clone_about_view#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        await clear_pending_input(client, user_id)
        await show_about_view(query, clone_doc)
        return True

    if data.startswith("clone_setabout#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        await set_pending_input(client, user_id, action="clone_setabout", back_cb=f"clone_about_view#{bot_id}", data={"bot_id": bot_id})
        text = (
            "<b>📝 Send Your Custom About Text</b>\n\n"
            "This will replace the top part of your About page.\n"
            f"The footer line (\"Cʟᴏɴᴇ Fʀᴏᴍ: @{MAIN_BOT_USERNAME}\") will still be added automatically — you don't need to include it.\n\n"
            "HTML formatting is supported. Send /cancel to cancel."
        )
        await send_or_edit_text(query, text, InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=f"clone_about_view#{bot_id}")]]))
        return True

    if data.startswith("clone_delabout#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        if not clone_doc.get("about_text"):
            await query.answer("ℹ️ Already using the default About text.", show_alert=True)
            return True
        await clone_db.update_clone_settings(bot_id, {"about_text": None})
        running = RUNNING_CLONES.get(bot_id)
        if running:
            running.custom_about_txt = None
        await query.answer("✅ Reset to default About text!", show_alert=True)
        clone_doc = await clone_db.get_clone(bot_id)
        await show_about_view(query, clone_doc)
        return True

    if data.startswith("clone_help_view#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        await clear_pending_input(client, user_id)
        await show_help_view(query, clone_doc)
        return True

    if data.startswith("clone_sethelp#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        await set_pending_input(client, user_id, action="clone_sethelp", back_cb=f"clone_help_view#{bot_id}", data={"bot_id": bot_id})
        text = (
            "<b>📝 Send Your Custom Help Text</b>\n\n"
            "This will replace the text shown when users tap \"Help\" on your clone bot.\n\n"
            "HTML formatting is supported. Send /cancel to cancel."
        )
        await send_or_edit_text(query, text, InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=f"clone_help_view#{bot_id}")]]))
        return True

    if data.startswith("clone_delhelp#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        if not clone_doc.get("help_text"):
            await query.answer("ℹ️ Already using the default Help text.", show_alert=True)
            return True
        await clone_db.update_clone_settings(bot_id, {"help_text": None})
        running = RUNNING_CLONES.get(bot_id)
        if running:
            running.custom_help_txt = None
        await query.answer("✅ Reset to default Help text!", show_alert=True)
        clone_doc = await clone_db.get_clone(bot_id)
        await show_help_view(query, clone_doc)
        return True

    if data.startswith("clone_filebtns_view#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        await clear_pending_input(client, user_id)
        await show_filebtns_view(query, clone_doc)
        return True

    if data.startswith("clone_setfilebtns#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        await set_pending_input(client, user_id, action="clone_setfilebtns", back_cb=f"clone_filebtns_view#{bot_id}", data={"bot_id": bot_id})
        text = (
            "<b>🔘 Send Your File Delivery Buttons</b>\n\n"
            "These buttons will appear <b>under every file</b> your bot delivers to users "
            "(this is separate from the Start Buttons shown on /start).\n\n"
            "<b>Format</b> (one row per line, use <code>|</code> for multiple buttons in one row):\n"
            "<code>Updates Channel - https://t.me/PrimeXBots</code>\n"
            "<code>Support Group - https://t.me/Prime_Support_group</code>\n\n"
            "Send /cancel to cancel."
        )
        await send_or_edit_text(query, text, InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=f"clone_filebtns_view#{bot_id}")]]))
        return True

    if data.startswith("clone_delfilebtns#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        if not clone_doc.get("file_buttons"):
            await query.answer("ℹ️ No file delivery buttons are set.", show_alert=True)
            return True
        await clone_db.update_clone_settings(bot_id, {"file_buttons": []})
        running = RUNNING_CLONES.get(bot_id)
        if running:
            running.custom_file_buttons = []
        await query.answer("✅ All file delivery buttons removed!", show_alert=True)
        clone_doc = await clone_db.get_clone(bot_id)
        await show_filebtns_view(query, clone_doc)
        return True

    if data.startswith("clone_reset_confirm#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True

        reset_values = {
            "start_pic": None,
            "start_pic_bytes": None,
            "start_msg": None,
            "start_buttons": [],
            "about_text": None,
            "help_text": None,
            "file_buttons": [],
        }
        await clone_db.update_clone_settings(bot_id, reset_values)
        running = RUNNING_CLONES.get(bot_id)
        if running:
            running.custom_start_pic = None
            running.custom_start_pic_bytes = None
            running.custom_start_txt = None
            running.custom_start_buttons = []
            running.custom_about_txt = None
            running.custom_help_txt = None
            running.custom_file_buttons = []

        await query.answer("✅ All customization has been reset to default!", show_alert=True)
        clone_doc = await clone_db.get_clone(bot_id)
        await show_manage_clone_panel(query, clone_doc, is_callback=True)
        return True

    if data.startswith("clone_reset#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True

        btn = InlineKeyboardMarkup([[
            InlineKeyboardButton(sc("✅ Yes, Reset Everything"), callback_data=f"clone_reset_confirm#{bot_id}"),
            InlineKeyboardButton(sc("❌ No"), callback_data=f"manage_clone#{bot_id}"),
        ]])
        await send_or_edit_text(
            query,
            f"<b>⚠️ {sc('Reset All Clone Settings?')}</b>\n\n"
            f"{sc('This will reset your Start Picture, Start Message, Start Buttons, About text, Help text, and File Delivery Buttons back to default.')}\n\n"
            f"{sc('Note: your bot token, stored files, and users are NOT affected — only appearance/customization settings reset.')}",
            btn,
        )
        return True

    if data.startswith("clone_details#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        await show_clone_details(query, clone_doc)
        return True

    if data.startswith("clone_toggle#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True

        if clone_doc["status"] == "active":
            await stop_clone(bot_id)
            await clone_db.set_status(bot_id, "inactive")
            await query.answer("⛔ Clone deactivated.")
        else:
            try:
                await start_clone(clone_doc["bot_token"], clone_doc["owner_id"])
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
        if not clone_doc or not has_clone_access(clone_doc, user_id):
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
        if not clone_doc or not is_owner(clone_doc, user_id):
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
        if not clone_doc or not is_owner(clone_doc, user_id):
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

    if data == "clone_create_new":
        if await clone_db.get_user_clone(user_id):
            await send_clone_entry(client, query, is_callback=True)
            return True
        await start_creation_flow(client, query, is_callback=True)
        return True

    # ---------------- ✨ Status popup ✨ ----------------
    if data.startswith("clone_status#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        await query.answer(await build_status_popup(clone_doc), show_alert=True)
        return True

    # ---------------- ✨ Moderator panel ✨ (শুধু ওনার) ----------------
    if data.startswith("clone_mods#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not is_owner(clone_doc, user_id):
            await query.answer("⚠️ Only the clone owner can manage moderators.", show_alert=True)
            return True
        await clear_pending_input(client, user_id)
        await show_mods_view(query, clone_doc)
        return True

    if data.startswith("clone_modadd#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not is_owner(clone_doc, user_id):
            await query.answer("⚠️ Only the clone owner can manage moderators.", show_alert=True)
            return True
        await set_pending_input(client, user_id, action="mod_add", back_cb=f"clone_mods#{bot_id}", data={"bot_id": bot_id})
        await send_or_edit_text(
            query,
            "<b>➕ Add Moderator</b>\n\n"
            "Send the user's <b>numeric ID</b>, their <b>@username</b>, or <b>forward any message</b> from them.\n\n"
            f"They will get <b>full access</b> to this clone{MOD_FOR_TXT}\n\n"
            "Send /cancel to cancel.",
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=f"clone_mods#{bot_id}")]]),
        )
        return True

    if data.startswith("clone_modrm_list#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not is_owner(clone_doc, user_id):
            await query.answer("⚠️ Only the clone owner can manage moderators.", show_alert=True)
            return True
        await show_mod_remove_list(query, clone_doc)
        return True

    if data.startswith("clone_modrm#"):
        _, bot_id_s, target_s = data.split("#")
        bot_id = int(bot_id_s)
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not is_owner(clone_doc, user_id):
            await query.answer("⚠️ Only the clone owner can manage moderators.", show_alert=True)
            return True
        if target_s == "all":
            removed = [int(m["user_id"]) for m in (clone_doc.get("moderators") or [])]
            await clone_db.clear_moderators(bot_id)
        else:
            removed = [int(target_s)]
            await clone_db.remove_moderator(bot_id, int(target_s))
        running = await _refresh_running_mods(bot_id)
        if running:
            for uid in removed:
                await clear_staff_commands(running, uid)
        await query.answer("✅ Moderator access removed.")
        clone_doc = await clone_db.get_clone(bot_id)
        await show_mods_view(query, clone_doc)
        return True

    # ---------------- ✨ Transfer ownership ✨ (শুধু ওনার) ----------------
    if data.startswith("clone_transfer#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not is_owner(clone_doc, user_id):
            await query.answer("⚠️ Only the clone owner can transfer it.", show_alert=True)
            return True
        await set_pending_input(client, user_id, action="transfer_owner", back_cb=f"clone_mods#{bot_id}", data={"bot_id": bot_id})
        await send_or_edit_text(
            query,
            "<b>🔄 Transfer Ownership</b>\n\n"
            "Send the <b>numeric ID</b>, <b>@username</b>, or <b>forward a message</b> of the person who should become the new owner.\n\n"
            "⚠️ <i>All your clone settings move to them and you lose control of this bot. "
            "The new owner must not already have a clone.</i>\n\n"
            "Send /cancel to cancel.",
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=f"clone_mods#{bot_id}")]]),
        )
        return True

    if data.startswith("clone_transfer_confirm#"):
        _, bot_id_s, new_uid_s = data.split("#")
        bot_id, new_uid = int(bot_id_s), int(new_uid_s)
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not is_owner(clone_doc, user_id):
            await query.answer("⚠️ Only the clone owner can transfer it.", show_alert=True)
            return True
        if await clone_db.get_user_clones_count(new_uid) >= MAX_CLONE_PER_USER:
            await query.answer("⚠️ That user already has a clone. Transfer cancelled.", show_alert=True)
            await show_mods_view(query, clone_doc)
            return True

        new_mention = f"<code>{new_uid}</code>"
        new_name = str(new_uid)
        try:
            u = await client.get_users(new_uid)
            new_mention, new_name = u.mention, (u.first_name or str(new_uid))
        except Exception:
            pass

        # ওনারের সেটিংস (ক্যাপশন, শর্টনার, ভেরিফাই, ফোর্স-সাব...) নতুন ওনারের নামে কপি
        cdb = get_clone_database(bot_id, clone_doc["db_name"])
        old_settings = await cdb.get_user(int(clone_doc["owner_id"]))
        keys = [
            "custom_caption", "shortener_api", "base_site", "verify_api", "verify_site", "verify_expire",
            "fsub_channels", "log_channel", "protect_content", "how_to_download", "verify",
            "permanent_link_mode", "auto_delete", "auto_delete_time", "auto_delete_msg",
        ]
        fields = {k: old_settings[k] for k in keys if k in old_settings}
        await cdb.users.update_one(
            {"user_id": new_uid},
            {"$set": fields, "$setOnInsert": {"user_id": new_uid, "name": new_name}},
            upsert=True,
        )

        old_owner = int(clone_doc["owner_id"])
        await clone_db.update_clone_settings(bot_id, {
            "owner_id": new_uid, "owner_mention": new_mention, "moderators": [],
        })
        running = RUNNING_CLONES.get(bot_id)
        if running:
            for m in (running.moderators or []):
                await clear_staff_commands(running, int(m["user_id"]))
            running.owner_id = new_uid
            running.owner_mention = new_mention
            running.moderators = []
            await clear_staff_commands(running, old_owner)
            await set_staff_commands(running, new_uid)

        try:
            await client.send_message(
                new_uid,
                f"🎉 <b>You are now the owner of @{clone_doc.get('bot_username')}!</b>\n\n"
                "Send /clone here to open its control panel.",
            )
        except Exception:
            pass

        await query.answer("✅ Ownership transferred!", show_alert=True)
        await send_or_edit_text(
            query,
            f"✅ <b>Ownership of @{clone_doc.get('bot_username')} has been transferred to</b> {new_mention}.",
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Home", callback_data="start")]]),
        )
        return True

    # ---------------- ✨ Bot Control মেনু ✨ ----------------
    if data.startswith("clone_control#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        await show_control_view(query, clone_doc)
        return True

    # ---------------- ✨ Change Bot (শুধু ওনার) ✨ ----------------
    if data.startswith("clone_changebot#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not is_owner(clone_doc, user_id):
            await query.answer("⚠️ Only the clone owner can change the bot.", show_alert=True)
            return True
        await set_pending_input(client, user_id, action="change_bot_token",
                                back_cb=f"clone_control#{bot_id}", data={"bot_id": bot_id})
        await send_or_edit_text(
            query,
            f"<b>🔄 {sc('Change Bot')}</b>\n"
            "<code>━━━━━━━━━━━━━━━━━━━━</code>\n\n"
            "<blockquote>Everything stays: settings, users, moderators, storage channel and your "
            "permanent links. Only the bot itself is replaced.</blockquote>\n\n"
            "1️⃣ Create a new bot in @BotFather\n"
            "2️⃣ <b>Forward</b> the BotFather message containing the new token here\n\n"
            f"⚠️ <i>@{clone_doc.get('bot_username')} will stop working after the change. "
            "If you use a Storage Channel, add the new bot there as admin.</i>\n\n"
            "Send /cancel to cancel.",
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=f"clone_control#{bot_id}")]]),
        )
        return True

    # ---------------- ✨ Storage channel ✨ ----------------
    if data.startswith("clone_storage#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        await clear_pending_input(client, user_id)
        await show_storage_view(query, clone_doc)
        return True

    if data.startswith("clone_storage_set#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        await set_pending_input(client, user_id, action="set_storage_channel",
                                back_cb=f"clone_storage#{bot_id}", data={"bot_id": bot_id})
        await send_or_edit_text(
            query,
            f"<b>📌 {sc('Set Storage Channel')}</b>\n\n"
            f"Make sure @{clone_doc.get('bot_username')} is an <b>admin</b> of your private channel "
            "(with Post Messages), then <b>forward any message from that channel</b> here.\n\n"
            "You can also send the channel ID (like <code>-1001234567890</code>).\n\n"
            "Send /cancel to cancel.",
            InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=f"clone_storage#{bot_id}")]]),
        )
        return True

    if data.startswith("clone_storage_rm#"):
        bot_id = int(data.split("#")[1])
        clone_doc = await clone_db.get_clone(bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            await query.answer("⚠️ Access denied!", show_alert=True)
            return True
        await clone_db.update_clone_settings(bot_id, {"storage_channel": None})
        running = RUNNING_CLONES.get(bot_id)
        if running:
            running.storage_channel = None
        # স্টোরেজ চ্যানেল ছাড়া পার্মানেন্ট লিংক চলে না — তাই বন্ধ করে দেওয়া হয়
        cdb = get_clone_database(bot_id, clone_doc["db_name"])
        await cdb.update_user_info(int(clone_doc["owner_id"]), {"permanent_link_mode": False})
        await query.answer("🗑 Storage channel removed. Permanent Link turned OFF.", show_alert=True)
        clone_doc = await clone_db.get_clone(bot_id)
        await show_storage_view(query, clone_doc)
        return True

    return False


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

    if message.text:
        first_word = message.text.strip().split()[0].lower().split("@")[0]
        if first_word in ("/start", "/clone", "/settings", "/stats", "/restart", "/broadcast", "/pin_broadcast",
                          "/batch", "/done", "/ban", "/unban", "/banlist"):
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

    if action == "awaiting_botfather_forward":
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

        # ✨ ক্লোন তৈরির আগে — টোকেন জমা দেওয়ার সময় — মূল বটের চ্যানেলে জয়েন বাধ্যতামূলক
        if CLONE_CREATION_FSUB_CHANNEL:
            is_member = await _is_fsub_member(client, CLONE_CREATION_FSUB_CHANNEL, user_id)
            if not is_member:
                state["data"]["pending_token"] = token
                state["data"]["pending_owner_mention"] = message.from_user.mention
                invite_link = await _get_fsub_invite_link(client, CLONE_CREATION_FSUB_CHANNEL)
                btn = InlineKeyboardMarkup([
                    [InlineKeyboardButton(sc("📢 Join Channel"), url=invite_link)],
                    [InlineKeyboardButton(sc("✅ I've Joined"), callback_data="clone_fsub_recheck")],
                ])
                await message.reply_text(
                    f"<b>⚠️ {sc('One Last Step!')}</b>\n\n"
                    f"{sc('Please join our channel to create your clone bot. After joining, tap the button below.')}",
                    reply_markup=btn,
                )
                await message.stop_propagation()
                return

        PENDING_INPUTS.pop(state_key, None)
        await _finalize_clone_creation(client, message, user_id, token, message.from_user.mention)
        await message.stop_propagation()
        return

    if action == "clone_setpic":
        target_bot_id = int(data["bot_id"])
        if not message.photo:
            await message.reply_text("❌ Please send a valid photo (or /cancel to cancel).", reply_markup=back_markup)
            await message.stop_propagation()
            return

        wait_pic = await message.reply_text("<i>⏳ Saving start picture...</i>")
        try:
            bio = await client.download_media(message.photo, in_memory=True)
            img_bytes = bio.getvalue()
        except Exception as e:
            await wait_pic.edit_text(f"❌ Failed to process picture: <code>{e}</code>", reply_markup=back_markup)
            await message.stop_propagation()
            return

        PENDING_INPUTS.pop(state_key, None)
        await clone_db.update_clone_settings(
            target_bot_id,
            {"start_pic": None, "start_pic_bytes": Binary(img_bytes)},
        )
        running = RUNNING_CLONES.get(target_bot_id)
        if running:
            running.custom_start_pic = None
            running.custom_start_pic_bytes = img_bytes

        await wait_pic.edit_text("✅ Start picture updated successfully!")
        clone_doc = await clone_db.get_clone(target_bot_id)
        if clone_doc:
            await show_pic_view(client, message, clone_doc)
        await message.stop_propagation()
        return

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
            await show_msg_view(message, clone_doc)
        await message.stop_propagation()
        return

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
                "<code>Updates Channel - https://t.me/PrimeXBots</code>\n"
                "<code>Support Group - https://t.me/Prime_Support_group</code>",
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
            await show_btns_view(message, clone_doc)
        await message.stop_propagation()
        return

    if action == "clone_setabout":
        target_bot_id = int(data["bot_id"])
        if not message.text:
            await message.reply_text("❌ Please send a text message (or /cancel to cancel).", reply_markup=back_markup)
            await message.stop_propagation()
            return

        PENDING_INPUTS.pop(state_key, None)
        new_about = message.text
        await clone_db.update_clone_settings(target_bot_id, {"about_text": new_about})
        running = RUNNING_CLONES.get(target_bot_id)
        if running:
            running.custom_about_txt = new_about

        await message.reply_text("✅ About text updated successfully!")
        clone_doc = await clone_db.get_clone(target_bot_id)
        if clone_doc:
            await show_about_view(message, clone_doc)
        await message.stop_propagation()
        return

    if action == "clone_sethelp":
        target_bot_id = int(data["bot_id"])
        if not message.text:
            await message.reply_text("❌ Please send a text message (or /cancel to cancel).", reply_markup=back_markup)
            await message.stop_propagation()
            return

        PENDING_INPUTS.pop(state_key, None)
        new_help = message.text
        await clone_db.update_clone_settings(target_bot_id, {"help_text": new_help})
        running = RUNNING_CLONES.get(target_bot_id)
        if running:
            running.custom_help_txt = new_help

        await message.reply_text("✅ Help text updated successfully!")
        clone_doc = await clone_db.get_clone(target_bot_id)
        if clone_doc:
            await show_help_view(message, clone_doc)
        await message.stop_propagation()
        return

    if action == "clone_setfilebtns":
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
                "<code>Updates Channel - https://t.me/PrimeXBots</code>\n"
                "<code>Support Group - https://t.me/Prime_Support_group</code>",
                reply_markup=back_markup,
            )
            await message.stop_propagation()
            return

        PENDING_INPUTS.pop(state_key, None)
        await clone_db.update_clone_settings(target_bot_id, {"file_buttons": parsed_buttons})
        running = RUNNING_CLONES.get(target_bot_id)
        if running:
            running.custom_file_buttons = parsed_buttons

        await message.reply_text("✅ File delivery buttons updated successfully!")
        clone_doc = await clone_db.get_clone(target_bot_id)
        if clone_doc:
            await show_filebtns_view(message, clone_doc)
        await message.stop_propagation()
        return

    if action == "set_storage_channel":
        target_bot_id = int(data["bot_id"])
        clone_doc = await clone_db.get_clone(target_bot_id)
        if not clone_doc or not has_clone_access(clone_doc, user_id):
            PENDING_INPUTS.pop(state_key, None)
            await message.reply_text("⚠️ Access denied.")
            await message.stop_propagation()
            return

        chat_id = None
        fc = getattr(message, "forward_from_chat", None)
        if not fc and getattr(message, "forward_origin", None):
            fc = getattr(message.forward_origin, "chat", None)
        if fc:
            chat_id = fc.id
        elif message.text and re.fullmatch(r"-100\d{5,}", message.text.strip()):
            chat_id = int(message.text.strip())

        if not chat_id:
            await message.reply_text(
                "❌ Please <b>forward a message from your channel</b> (or send its ID like <code>-1001234567890</code>).\n\n"
                "Send /cancel to cancel.",
                reply_markup=back_markup,
            )
            await message.stop_propagation()
            return

        running = RUNNING_CLONES.get(target_bot_id)
        if not running:
            await message.reply_text("⚠️ Your clone bot is not running. Activate it first, then try again.", reply_markup=back_markup)
            await message.stop_propagation()
            return

        try:
            test = await running.send_message(chat_id, "✅ Storage channel connected successfully.")
            try:
                await test.delete()
            except Exception:
                pass
        except Exception:
            await message.reply_text(
                f"❌ @{clone_doc.get('bot_username')} can't post in that channel.\n\n"
                "Add the bot as an <b>admin</b> with <b>Post Messages</b> permission, then forward a message again.",
                reply_markup=back_markup,
            )
            await message.stop_propagation()
            return

        PENDING_INPUTS.pop(state_key, None)
        await clone_db.update_clone_settings(target_bot_id, {"storage_channel": chat_id})
        running.storage_channel = chat_id
        await message.reply_text(
            f"✅ <b>Storage channel connected!</b>\n\n<code>{chat_id}</code>\n\n"
            "New files will now be saved there. You can turn on Permanent Link.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                "🔗 Permanent Link", callback_data=f"permanent_link_setgs#{clone_doc['owner_id']}#{target_bot_id}")]]),
        )
        await message.stop_propagation()
        return

    if action == "change_bot_token":
        target_bot_id = int(data["bot_id"])
        clone_doc = await clone_db.get_clone(target_bot_id)
        if not clone_doc or not is_owner(clone_doc, user_id):
            PENDING_INPUTS.pop(state_key, None)
            await message.reply_text("⚠️ Only the clone owner can change the bot.")
            await message.stop_propagation()
            return

        fwd_user = getattr(message, "forward_from", None)
        if not fwd_user and getattr(message, "forward_origin", None):
            fwd_user = getattr(message.forward_origin, "sender_user", None)
        is_botfather = bool(
            fwd_user and (
                (getattr(fwd_user, "username", None) or "").lower() == "botfather"
                or getattr(fwd_user, "id", None) == 93372553
            )
        )
        match = re.search(r"\b(\d{6,}:[A-Za-z0-9_-]{30,})\b", message.text or message.caption or "")
        if not is_botfather or not match:
            await message.reply_text(
                "❌ Please <b>forward</b> the message from @BotFather that contains the new bot's token.\n\n"
                "Send /cancel to cancel.",
                reply_markup=back_markup,
            )
            await message.stop_propagation()
            return

        PENDING_INPUTS.pop(state_key, None)
        wait_msg = await message.reply_text("<i>⏳ Verifying the new token and moving your clone, please wait...</i>")
        try:
            new_me = await change_clone_bot(target_bot_id, match.group(1).strip())
        except Exception as e:
            await wait_msg.edit_text(
                f"❌ <b>Could not change the bot:</b>\n<code>{e}</code>\n\nYour current bot was not changed.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=f"manage_clone#{target_bot_id}")]]),
            )
            await message.stop_propagation()
            return

        note = ""
        if clone_doc.get("storage_channel"):
            note = f"\n\n📦 <b>Important:</b> add @{new_me.username} as <b>admin</b> of your Storage Channel so files keep working."
        await wait_msg.edit_text(
            f"✅ <b>Bot changed successfully!</b>\n\n"
            f"🤖 <b>New bot:</b> @{new_me.username}\n\n"
            "All settings, users, moderators and permanent links were kept."
            + note,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"⚙️ Customize @{new_me.username}", callback_data=f"manage_clone#{new_me.id}")],
            ]),
        )
        await message.stop_propagation()
        return

    if action == "mod_add":
        target_bot_id = int(data["bot_id"])
        clone_doc = await clone_db.get_clone(target_bot_id)
        if not clone_doc or not is_owner(clone_doc, user_id):
            PENDING_INPUTS.pop(state_key, None)
            await message.reply_text("⚠️ Only the clone owner can add moderators.")
            await message.stop_propagation()
            return

        res = await resolve_user_ref(client, message)
        if not res:
            await message.reply_text(
                "❌ Couldn't find that user. Send a numeric ID, @username or forward a message from them (or /cancel).",
                reply_markup=back_markup,
            )
            await message.stop_propagation()
            return
        if res["is_bot"]:
            await message.reply_text("❌ A bot can't be a moderator.", reply_markup=back_markup)
            await message.stop_propagation()
            return
        if int(res["id"]) == int(clone_doc["owner_id"]):
            await message.reply_text("ℹ️ You are the owner already.", reply_markup=back_markup)
            await message.stop_propagation()
            return

        PENDING_INPUTS.pop(state_key, None)
        expires_at = mod_expiry_ts(MODERATOR_DURATION_HOURS)
        await clone_db.add_moderator(target_bot_id, res["id"], expires_at, user_id, name=res["name"])
        running = await _refresh_running_mods(target_bot_id)
        if running:
            await set_staff_commands(running, res["id"])

        try:
            await client.send_message(
                res["id"],
                f"👮 <b>You are now a moderator of @{clone_doc.get('bot_username')}!</b>\n\n"
                f"You have full access{MOD_FOR_TXT}\n"
                "Send /clone here to open its control panel, or use the staff commands inside that bot "
                "(/broadcast, /ban, /unban, /banlist).",
            )
        except Exception:
            pass

        await message.reply_text(
            f"✅ {res['mention']} (<code>{res['id']}</code>) is now a moderator"
            f"{' with <b>no time limit</b>.' if MODERATOR_DURATION_HOURS <= 0 else ' for <b>' + format_duration(MODERATOR_DURATION_HOURS * 3600) + '</b>.'}"
        )
        clone_doc = await clone_db.get_clone(target_bot_id)
        await show_mods_view(message, clone_doc)
        await message.stop_propagation()
        return

    if action == "transfer_owner":
        target_bot_id = int(data["bot_id"])
        clone_doc = await clone_db.get_clone(target_bot_id)
        if not clone_doc or not is_owner(clone_doc, user_id):
            PENDING_INPUTS.pop(state_key, None)
            await message.reply_text("⚠️ Only the clone owner can transfer it.")
            await message.stop_propagation()
            return

        res = await resolve_user_ref(client, message)
        if not res:
            await message.reply_text(
                "❌ Couldn't find that user. Send a numeric ID, @username or forward a message from them (or /cancel).",
                reply_markup=back_markup,
            )
            await message.stop_propagation()
            return
        if res["is_bot"]:
            await message.reply_text("❌ A bot can't own a clone.", reply_markup=back_markup)
            await message.stop_propagation()
            return
        if int(res["id"]) == int(user_id):
            await message.reply_text("ℹ️ You are the owner already.", reply_markup=back_markup)
            await message.stop_propagation()
            return
        if await clone_db.get_user_clones_count(res["id"]) >= MAX_CLONE_PER_USER:
            await message.reply_text("❌ That user already has a clone, so they can't receive another one.", reply_markup=back_markup)
            await message.stop_propagation()
            return

        PENDING_INPUTS.pop(state_key, None)
        await message.reply_text(
            f"⚠️ <b>Transfer @{clone_doc.get('bot_username')} to</b> {res['mention']} (<code>{res['id']}</code>)?\n\n"
            "You will <b>lose all control</b> of this bot. This cannot be undone.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Yes, Transfer", callback_data=f"clone_transfer_confirm#{target_bot_id}#{res['id']}"),
                    InlineKeyboardButton("❌ No", callback_data=f"clone_mods#{target_bot_id}"),
                ]
            ]),
        )
        await message.stop_propagation()
        return

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

    if action == "set_autodelete_time":
        if not message.text:
            await message.reply_text("❌ Please send a time like <code>30s</code>, <code>5m</code> or <code>2h</code>.", reply_markup=back_markup)
            await message.stop_propagation()
            return
        try:
            seconds = parse_duration(message.text)
        except Exception:
            await message.reply_text("❌ Invalid format. Example: <code>30s</code>, <code>5m</code>, <code>2h</code>", reply_markup=back_markup)
            await message.stop_propagation()
            return
        if seconds < MIN_AUTODELETE_SECONDS or seconds > MAX_AUTODELETE_SECONDS:
            await message.reply_text(
                f"❌ Time must be between <b>{format_duration(MIN_AUTODELETE_SECONDS)}</b> and <b>{format_duration(MAX_AUTODELETE_SECONDS)}</b>.",
                reply_markup=back_markup,
            )
            await message.stop_propagation()
            return

        PENDING_INPUTS.pop(state_key, None)
        await cur_db.update_user_info(target_uid, {"auto_delete_time": seconds})
        await message.reply_text(
            f"✅ Auto Delete time updated to <b>{format_duration(seconds)}</b>.",
            reply_markup=back_markup,
        )
        await message.stop_propagation()
        return

    if action == "set_autodelete_msg":
        if not message.text:
            await message.reply_text("❌ Please send the message as text.", reply_markup=back_markup)
            await message.stop_propagation()
            return
        PENDING_INPUTS.pop(state_key, None)
        await cur_db.update_user_info(target_uid, {"auto_delete_msg": message.text})
        await message.reply_text("✅ Auto Delete message updated!", reply_markup=back_markup)
        await message.stop_propagation()
        return
