from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid

import time
import asyncio
import logging

from database import get_db
from utils import is_bot_staff


# ✨ প্রতিটা বটের (মূল বট / প্রতিটা ক্লোন) নিজস্ব লক ও ক্যান্সেল ফ্ল্যাগ —
# একটা ক্লোনের ব্রডকাস্ট অন্য বটের ব্রডকাস্টকে আটকায় না।
_LOCKS: dict = {}
_CANCEL: dict = {}


def _bot_key(bot) -> int:
    return int(getattr(bot, "bot_id", 0) or 0)


def get_readable_time(seconds):
    periods = [('days', 86400), ('hour', 3600), ('min', 60), ('sec', 1)]
    result = ''
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result += f'{int(period_value)}{period_name}'
    return result


async def _staff(_, client, message):
    return bool(message.from_user) and is_bot_staff(client, message.from_user.id)

staff_filter = filters.create(_staff)


async def users_broadcast(cur_db, user_id, message, is_pin):
    try:
        m = await message.copy(chat_id=user_id)
        if is_pin:
            await m.pin(both_sides=True)
        return True, "Success"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await users_broadcast(cur_db, user_id, message, is_pin)
    except InputUserDeactivated:
        await cur_db.delete_user(int(user_id))
        logging.info(f"{user_id} - Removed from Database, since deleted account.")
        return False, "Deleted"
    except UserIsBlocked:
        logging.info(f"{user_id} - Blocked the bot.")
        await cur_db.delete_user(user_id)
        return False, "Blocked"
    except PeerIdInvalid:
        await cur_db.delete_user(int(user_id))
        logging.info(f"{user_id} - PeerIdInvalid")
        return False, "Error"
    except Exception as e:
        logging.error(f"Error broadcasting to {user_id}: {e}")
        return False, "Error"


@Client.on_callback_query(filters.regex(r'^broadcast_cancel'), group=-1)
async def broadcast_cancel(bot, query):
    if not is_bot_staff(bot, query.from_user.id):
        await query.answer("⚠️ Not allowed!", show_alert=True)
        return query.stop_propagation()
    _, ident = query.data.split("#")
    if ident == 'users':
        await query.message.edit("Trying to cancel users broadcasting...")
        _CANCEL[_bot_key(bot)] = True
    query.stop_propagation()


async def process_broadcast(bot, message, is_pin: bool):
    key = _bot_key(bot)
    lock = _LOCKS.setdefault(key, asyncio.Lock())
    if lock.locked():
        return await message.reply('Currently broadcast processing, Wait for complete.')

    cur_db = get_db(bot)
    await bot.send_message(chat_id=message.chat.id, text="Broadcast started...", reply_markup=ReplyKeyboardRemove())

    users = await cur_db.get_all_users()
    b_msg = message.reply_to_message
    b_sts = await message.reply_text(text='<b>Broadcasting your messages to users ⌛️</b>')

    start_time = time.time()
    total_users = await cur_db.total_users_count()
    done = 0
    success = 0
    failed = 0
    skipped = 0

    async with lock:
        _CANCEL[key] = False
        async for user in users:
            if _CANCEL.get(key):
                _CANCEL[key] = False
                time_taken = get_readable_time(time.time() - start_time)
                await b_sts.edit(
                    f"❌ Users broadcast cancelled!\nCompleted in {time_taken}\n\n"
                    f"Total Users: <code>{total_users}</code>\n"
                    f"Completed: <code>{done}</code>\n"
                    f"Success: <code>{success}</code>"
                )
                return

            uid = int(user['user_id'])
            # ব্যান করা ইউজারকে ব্রডকাস্ট পাঠানো হয় না
            if await cur_db.is_banned(uid):
                skipped += 1
                done += 1
                continue

            success_flag, sts = await users_broadcast(cur_db, uid, b_msg, is_pin)

            if sts == 'Success':
                success += 1
            elif sts == 'Error':
                failed += 1
            done += 1

            if done % 20 == 0:
                btn = [[InlineKeyboardButton('CANCEL', callback_data='broadcast_cancel#users')]]
                try:
                    await b_sts.edit(
                        f"📢 Users broadcast in progress...\n\n"
                        f"Total Users: <code>{total_users}</code>\n"
                        f"Completed: <code>{done}</code>\n"
                        f"Success: <code>{success}</code>",
                        reply_markup=InlineKeyboardMarkup(btn)
                    )
                except Exception:
                    pass

        time_taken = get_readable_time(time.time() - start_time)
        await b_sts.edit(
            f"✅ Users broadcast completed!\nCompleted in {time_taken}\n\n"
            f"Total Users: <code>{total_users}</code>\n"
            f"Completed: <code>{done}</code>\n"
            f"Success: <code>{success}</code>\n"
            f"Failed: <code>{failed}</code>\n"
            f"Skipped (banned): <code>{skipped}</code>"
        )


# /broadcast (শুধু পাঠায়) — মূল বটে ADMINS, ক্লোন বটে ওনার + মডারেটর
@Client.on_message(filters.command("broadcast") & filters.private & staff_filter)
async def broadcast_only(bot, message):
    if not message.reply_to_message:
        return await message.reply_text("⚠️ Reply to the message you want to broadcast with /broadcast")
    await process_broadcast(bot, message, is_pin=False)


# /pin_broadcast (পাঠায় + পিন করে)
@Client.on_message(filters.command("pin_broadcast") & filters.private & staff_filter)
async def broadcast_with_pin(bot, message):
    if not message.reply_to_message:
        return await message.reply_text("⚠️ Reply to the message you want to broadcast with /pin_broadcast")
    await process_broadcast(bot, message, is_pin=True)
