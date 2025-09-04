from pyrogram import Client, filters
from pyrogram.types import Message
from base64 import standard_b64encode, standard_b64decode
from typing import Any
import random
import string
from datetime import datetime, timedelta, date, time
import pytz
import logging

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
