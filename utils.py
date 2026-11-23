from pyrogram import Client, filters
from pyrogram.types import Message
from base64 import standard_b64encode, standard_b64decode
from typing import Any
import random
import re
import string
from datetime import datetime, timedelta, date, time
import pytz
import logging
import time as _time
import secrets

from database import db
from config import *

# ✅ logger सही तरीके से बनाओ
logger = logging.getLogger(__name__)


class temp:
    ME = None
    BOT = None
    U_NAME = None
    B_NAME = None
    TOKENS = {}      # {userid: {token: bool}}
    VERIFIED = {}    # {userid: {"date": "YYYY-MM-DD", "time": "HH:MM:SS"}}


# -------------------------- Base64 Encode / Decode -------------------------- #
def str_to_b64(__str: str) -> str:
    return standard_b64encode(__str.encode("ascii")).decode("ascii")


def b64_to_str(b64: str) -> str:
    return standard_b64decode(b64.encode("ascii")).decode("ascii")


# -------------------------- File & Hash Helpers -------------------------- #
def get_file_id(message: "Message") -> Any:
    media_types = (
        "audio", "document", "photo", "sticker", "animation",
        "video", "voice", "video_note"
    )
    if message.media:
        for attr in media_types:
            media = getattr(message, attr, None)
            if media:
                setattr(media, "message_type", attr)
                return media


def get_hash(media_msg: Message) -> str:
    media = get_file_id(media_msg)
    return getattr(media, "file_unique_id", "")[:6]


def humanbytes(size):
    if not size:
        return "0 B"
    power = 2 ** 10
    n = 0
    Dic_powerN = {0: '', 1: 'Ki', 2: 'Mi', 3: 'Gi', 4: 'Ti'}
    while size > power:
        size /= power
        n += 1
    return f"{round(size, 2)} {Dic_powerN[n]}B"


# -------------------------- TOKEN VALIDITY CHECK -------------------------- #
async def check_token(bot, userid, token: str) -> bool:
    user = await bot.get_users(userid)
    tokens = temp.TOKENS.get(user.id, {})
    return tokens.get(token) is False


# -------------------------- TOKEN GENERATOR -------------------------- #
async def get_token(bot, userid, link: str) -> str:
    user = await bot.get_users(userid)
    token = "".join(random.choices(string.ascii_letters + string.digits, k=7))
    temp.TOKENS[user.id] = {token: False}
    full_link = f"{link}verify-{user.id}-{token}"

    if hasattr(db, "get_verify_link"):
        short_link = await db.get_verify_link(full_link)
    else:
        short_link = full_link

    return short_link


# -------------------------- GET VERIFICATION STATUS -------------------------- #
async def get_verify_status(userid: int) -> dict | None:
    status = temp.VERIFIED.get(userid)
    if not status and hasattr(db, "get_verified"):
        status = await db.get_verified(userid)
        if status:
            temp.VERIFIED[userid] = status
    return status


# -------------------------- UPDATE VERIFICATION STATUS -------------------------- #
async def update_verify_status(userid: int, date_temp: str, time_temp: str):
    status = await get_verify_status(userid) or {}
    status["date"] = date_temp
    status["time"] = time_temp
    temp.VERIFIED[userid] = status
    if hasattr(db, "update_verification"):
        await db.update_verification(userid, date_temp, time_temp)


# -------------------------- VERIFY USER -------------------------- #
async def verify_user(bot, userid: int, token: str, owner_uid: int):
    user = await bot.get_users(int(userid))
    temp.TOKENS[user.id] = {token: True}

    uinfo = await db.get_user(owner_uid)
    expire_seconds = uinfo.get("verify_expire", VERIFY_EXPIRE)

    tz = pytz.timezone("Asia/Kolkata")
    expiry = datetime.now(tz) + timedelta(seconds=expire_seconds)
    date_str = expiry.strftime("%Y-%m-%d")
    time_str = expiry.strftime("%H:%M:%S")

    await update_verify_status(user.id, date_str, time_str)


# -------------------------- CHECK USER VERIFICATION -------------------------- #
async def check_verification(bot, userid: int) -> bool:
    user = await bot.get_users(int(userid))
    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.now(tz)

    current_time = time(now.hour, now.minute, now.second)
    today = date.today()
    status = await get_verify_status(user.id)

    if not status:
        return False

    try:
        exp_date = datetime.strptime(status["date"], "%Y-%m-%d").date()
        exp_time = datetime.strptime(status["time"], "%H:%M:%S").time()
    except Exception as e:
        logger.error(f"Invalid verification time format: {e}")
        return False

    if exp_date < today or (exp_date == today and exp_time < current_time):
        return False
    return True


# ================= ✨ "Sᴜᴘᴇʀ Pʀᴇᴍɪᴜᴍ" স্টাইল টেক্সট হেল্পার ✨ =================
_SMALLCAPS_MAP = {
    'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ꜰ', 'g': 'ɢ',
    'h': 'ʜ', 'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ',
    'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ', 's': 'ꜱ', 't': 'ᴛ', 'u': 'ᴜ',
    'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x', 'y': 'ʏ', 'z': 'ᴢ',
}


def sc(text: str) -> str:
    """
    'Sᴜᴘᴇʀ Pʀᴇᴍɪᴜᴍ' স্টাইলের টেক্সটে কনভার্ট করে — প্রতিটা শব্দের প্রথম অক্ষর
    সাধারণ বড় হাতের, আর বাকি অক্ষরগুলো small-caps ইউনিকোডে। ইমোজি, সংখ্যা,
    চিহ্ন অপরিবর্তিত থাকে।
    """
    out_words = []
    for word in text.split(' '):
        if not word:
            out_words.append(word)
            continue
        result = []
        first_letter_done = False
        for ch in word:
            low = ch.lower()
            if low.isalpha() and low in _SMALLCAPS_MAP:
                if not first_letter_done:
                    result.append(ch.upper())
                    first_letter_done = True
                else:
                    result.append(_SMALLCAPS_MAP[low])
            else:
                result.append(ch)
        out_words.append(''.join(result))
    return ' '.join(out_words)


# ================= ✨ NEW HELPERS ✨ =================
_CODE_ALPHABET = string.ascii_letters + string.digits
LINK_CODE_LENGTH = 22  # t.me start-param সীমা ৬৪ — verify লিংকেও এটা ঢুকে যায়


def new_link_code(length: int = LINK_CODE_LENGTH) -> str:
    """পরিষ্কার, প্যাডিং(=) ছাড়া র‍্যান্ডম লিংক কোড — যেমন: Xk3J9aBq2LmZp0TrYw7NcD"""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def looks_like_link_code(raw: str) -> bool:
    return raw.isalnum() and len(raw) >= 16


def parse_duration(text: str) -> int:
    """'30s', '10m', '2h', '1d' বা শুধু সেকেন্ড সংখ্যা → সেকেন্ড। ভুল হলে ValueError।"""
    arg = (text or "").strip().lower()
    if not arg:
        raise ValueError("empty")
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if arg[-1] in mult:
        return int(arg[:-1].strip()) * mult[arg[-1]]
    return int(arg)


def format_duration(seconds) -> str:
    """৩০০ → '5 minutes', ৫৪০০ → '1 hour 30 minutes'"""
    seconds = int(seconds)
    parts = []
    for name, sec in (("day", 86400), ("hour", 3600), ("minute", 60), ("second", 1)):
        if seconds >= sec:
            v, seconds = divmod(seconds, sec)
            parts.append(f"{v} {name}{'s' if v != 1 else ''}")
    return " ".join(parts) or "0 seconds"


def short_duration(seconds) -> str:
    """৭৩০০ → '2h 1m' (ছোট আকারে, Status পপ-আপের জন্য)"""
    seconds = int(seconds)
    d, r = divmod(seconds, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def _admin_ids() -> list:
    return list(ADMINS) if isinstance(ADMINS, (list, tuple, set)) else [ADMINS]


def active_moderators_of(client) -> list:
    now = _time.time()
    return [m for m in (getattr(client, "moderators", None) or []) if m.get("expires_at", 0) > now]


def is_bot_staff(client, user_id: int) -> bool:
    """
    মূল বট: ADMINS।
    ক্লোন বট: ক্লোনের ওনার + এখনো মেয়াদ আছে এমন মডারেটর।
    """
    user_id = int(user_id)
    if getattr(client, "is_clone", False):
        if user_id == int(getattr(client, "owner_id", 0) or 0):
            return True
        return any(int(m["user_id"]) == user_id for m in active_moderators_of(client))
    return user_id in _admin_ids()


async def resolve_user_ref(client, message):
    """
    মেসেজ থেকে ইউজার বের করে: ফরোয়ার্ড করা মেসেজ / সংখ্যার ID / @username।
    রিটার্ন: dict(id, name, mention, is_bot) অথবা None।
    """
    fwd = getattr(message, "forward_from", None)
    if not fwd and getattr(message, "forward_origin", None):
        fwd = getattr(message.forward_origin, "sender_user", None)
    if fwd:
        return {"id": fwd.id, "name": fwd.first_name or str(fwd.id), "mention": fwd.mention, "is_bot": bool(fwd.is_bot)}

    # ফরোয়ার্ড করা মেসেজ কিন্তু প্রেরকের আইডি লুকানো — টেক্সট থেকে ইউজার অনুমান করা হবে না
    if getattr(message, "forward_date", None) or getattr(message, "forward_origin", None):
        return None

    text = (message.text or "").strip()
    if not text:
        return None
    token = text.split()[0]
    ref = None
    if token.lstrip("-").isdigit():
        ref = int(token)
    elif re.fullmatch(r"@[A-Za-z][A-Za-z0-9_]{4,31}", token):
        ref = token
    if ref is None:
        return None
    try:
        u = await client.get_users(ref)
        return {"id": u.id, "name": u.first_name or str(u.id), "mention": u.mention, "is_bot": bool(u.is_bot)}
    except Exception:
        if isinstance(ref, int):
            return {"id": ref, "name": str(ref), "mention": f"<code>{ref}</code>", "is_bot": False}
        return None
