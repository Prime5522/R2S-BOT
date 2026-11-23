"""
✨ ব্যান সিস্টেম: /ban  /unban  /banlist
- মূল বটে শুধু ADMINS, ক্লোন বটে ওনার + (মেয়াদ-থাকা) মডারেটর।
- ব্যান করা ইউজার বটের কোনো কিছুই (মেসেজ/বাটন) ব্যবহার করতে পারে না।
"""
from types import SimpleNamespace

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery

from database import get_db
from utils import is_bot_staff, resolve_user_ref

BAN_TEXT = "🚫 <b>You are banned from using this bot.</b>"


# ---------------------- Ban gate (সবার আগে চলে) ---------------------- #
@Client.on_message(filters.private & ~filters.service, group=-5)
async def ban_gate_message(client: Client, message: Message):
    if not message.from_user:
        return
    uid = message.from_user.id
    if is_bot_staff(client, uid):
        return
    if await get_db(client).is_banned(uid):
        try:
            await message.reply_text(BAN_TEXT)
        except Exception:
            pass
        message.stop_propagation()


@Client.on_callback_query(group=-5)
async def ban_gate_callback(client: Client, query: CallbackQuery):
    uid = query.from_user.id
    if is_bot_staff(client, uid):
        return
    if await get_db(client).is_banned(uid):
        await query.answer("🚫 You are banned from using this bot.", show_alert=True)
        query.stop_propagation()


# ---------------------- Helpers ---------------------- #
async def _staff(_, client, message):
    return bool(message.from_user) and is_bot_staff(client, message.from_user.id)

staff_filter = filters.create(_staff)


async def _target_from(client: Client, message: Message, skip_args: int = 1):
    """/ban 12345 | /ban @name | ফরোয়ার্ড করা মেসেজে রিপ্লাই — যেকোনোটা থেকে ইউজার বের করে"""
    if len(message.command) > 1:
        fake = SimpleNamespace(text=message.command[1], forward_from=None, forward_origin=None, forward_date=None)
        res = await resolve_user_ref(client, fake)
        if res:
            return res
    if message.reply_to_message:
        res = await resolve_user_ref(client, message.reply_to_message)
        if res:
            return res
    return None


# ---------------------- /ban ---------------------- #
@Client.on_message(filters.command("ban") & filters.private & staff_filter)
async def ban_command(client: Client, message: Message):
    target = await _target_from(client, message)
    if not target:
        return await message.reply_text(
            "<b>Usage:</b>\n"
            "<code>/ban 123456789 optional reason</code>\n"
            "<code>/ban @username optional reason</code>\n"
            "or reply to a forwarded message of the user with /ban"
        )
    uid = target["id"]
    if is_bot_staff(client, uid):
        return await message.reply_text("⚠️ You can't ban the owner or a moderator.")
    if target.get("is_bot"):
        return await message.reply_text("⚠️ You can't ban a bot.")

    reason = " ".join(message.command[2:]).strip() or None
    cur_db = get_db(client)
    if await cur_db.is_banned(uid):
        return await message.reply_text(f"ℹ️ {target['mention']} (<code>{uid}</code>) is already banned.")
    await cur_db.ban_user(uid, reason=reason, by=message.from_user.id)
    await message.reply_text(
        f"🚫 <b>Banned:</b> {target['mention']} (<code>{uid}</code>)"
        + (f"\n📝 <b>Reason:</b> {reason}" if reason else "")
    )


# ---------------------- /unban ---------------------- #
@Client.on_message(filters.command("unban") & filters.private & staff_filter)
async def unban_command(client: Client, message: Message):
    target = await _target_from(client, message)
    if not target:
        return await message.reply_text(
            "<b>Usage:</b>\n<code>/unban 123456789</code>\n<code>/unban @username</code>"
        )
    uid = target["id"]
    if await get_db(client).unban_user(uid):
        await message.reply_text(f"✅ <b>Unbanned:</b> {target['mention']} (<code>{uid}</code>)")
    else:
        await message.reply_text(f"ℹ️ <code>{uid}</code> is not in the ban list.")


# ---------------------- /banlist ---------------------- #
@Client.on_message(filters.command("banlist") & filters.private & staff_filter)
async def banlist_command(client: Client, message: Message):
    banned = await get_db(client).get_banned()
    if not banned:
        return await message.reply_text("✅ No banned users.")

    lines = []
    for i, b in enumerate(banned, 1):
        line = f"{i}. <code>{b['user_id']}</code>"
        if b.get("reason"):
            line += f" — {b['reason']}"
        lines.append(line)

    header = f"🚫 <b>Banned Users ({len(banned)})</b>\n\n"
    chunk = header
    for line in lines:
        if len(chunk) + len(line) + 1 > 3900:
            await message.reply_text(chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        await message.reply_text(chunk)
      
