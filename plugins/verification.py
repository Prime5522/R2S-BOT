import random, string, pytz, asyncio
from datetime import datetime, timedelta, date, time
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import *
from Script import script
from database import db, get_db
from utils import temp, logger, looks_like_link_code, str_to_b64

# -------------------------- TOKEN VALIDITY CHECK --------------------------
async def check_token(bot, userid: int, token: str) -> bool:
    tokens = temp.TOKENS.get(userid, {})
    return token in tokens and tokens[token] is False

# -------------------------- TOKEN GENERATOR --------------------------
async def get_token(bot, userid: int, link: str, owner_uid: int, file_id) -> str:
    db = get_db(bot)   # ✨ মূল বট হলে মূল db, ক্লোন হলে ক্লোনের নিজস্ব db
    token = "".join(random.choices(string.ascii_letters + string.digits, k=7))

    if userid not in temp.TOKENS:
        temp.TOKENS[userid] = {}
    temp.TOKENS[userid][token] = False

    full_link = f"{link}verify-{userid}-{owner_uid}:{file_id}-{token}"

    owner = await db.get_user(owner_uid)
    return await db.get_verify_link(owner, full_link)

# -------------------------- GET VERIFICATION STATUS --------------------------
# ⚠️ নোট: temp.VERIFIED/temp.TOKENS ক্যাশ পুরো process-এর জন্য একটাই (মূল বট +
# সব ক্লোন শেয়ার করে)। এতে persistent DB ডাটা সব সময় সঠিক ক্লোনের নিজস্ব db-তেই
# সেভ/রিড হয় (এটাই গুরুত্বপূর্ণ), শুধু এই in-memory ক্যাশটা (temporary, রিস্টার্টে
# মুছে যায়) যদি একই Telegram user_id মূল বট ও কোনো ক্লোনে একইসাথে ভেরিফাই করে,
# তাহলে সামান্য ওভারল্যাপ হতে পারে — সেটা ঠিক করতে চাইলে আলাদাভাবে জানাবেন।
async def get_verify_status(bot, userid: int) -> dict | None:
    db = get_db(bot)
    status = temp.VERIFIED.get(userid)
    if not status:
        status = await db.get_verified(userid)
    if status:
        temp.VERIFIED[userid] = status
    return status

# -------------------------- UPDATE VERIFICATION STATUS --------------------------
async def update_verify_status(bot, userid: int, date_temp: str, time_temp: str):
    db = get_db(bot)
    status = await get_verify_status(bot, userid) or {}
    status["date"] = date_temp
    status["time"] = time_temp
    temp.VERIFIED[userid] = status
    await db.update_verification(userid, date_temp, time_temp)

# -------------------------- VERIFY USER --------------------------
async def verify_user(bot, userid: int, token: str, owner_uid: int):
    db = get_db(bot)   # ✨ মূল বট হলে মূল db, ক্লোন হলে ক্লোনের নিজস্ব db
    temp.TOKENS[userid][token] = True

    uinfo = await db.get_user(owner_uid)
    expire_seconds = uinfo.get("verify_expire", VERIFY_EXPIRE)

    tz = pytz.timezone("Asia/Kolkata")
    expiry = datetime.now(tz) + timedelta(seconds=expire_seconds)

    await update_verify_status(
        bot,
        userid,
        expiry.strftime("%Y-%m-%d"),
        expiry.strftime("%H:%M:%S")
    )

# -------------------------- CHECK USER VERIFICATION --------------------------
async def check_verification(bot, userid: int) -> bool:
    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.now(tz)
    current_time = time(now.hour, now.minute, now.second)
    today = date.today()

    status = await get_verify_status(bot, userid)
    if not status:
        return False

    try:
        exp_date = datetime.strptime(status["date"], "%Y-%m-%d").date()
        exp_time = datetime.strptime(status["time"], "%H:%M:%S").time()
    except Exception as e:
        logger.error(f"Invalid verification time format: {e}")
        return False

    return not (exp_date < today or (exp_date == today and exp_time < current_time))

# -------------------------- VERIFY CASE HANDLER --------------------------
async def handle_verify_case(client, message, raw: str):
    db = get_db(client)   # ✨ মূল বট হলে মূল db, ক্লোন হলে ক্লোনের নিজস্ব db
    try:
        _, userid, data, token = raw.split("-", 3)
        owner_uid, file_id = data.split(":", 1)   # file_id এখন লিংক-কোড (স্ট্রিং) — পুরনো লিংকে সংখ্যা/c_xxx
        owner_uid = int(owner_uid)
    except Exception:
        return await message.reply_text("<b>⚠️ Invalid or expired link. Try again!</b>")

    # ✅ link misuse रोकना
    if str(message.from_user.id) != str(userid):
        return await message.reply_text("<b>⚠️ This link is not for you!</b>")

    # ✅ token validity check
    if not await check_token(client, int(userid), token):
        return await message.reply_text("<b>⚠️ Link expired or already used!</b>")

    # ✅ verified होने के बाद file button देना
    bot_username = getattr(client, "username", None) or (await client.get_me()).username
    if looks_like_link_code(file_id):
        file_url = f"https://t.me/{bot_username}?start={file_id}"          # নতুন ছোট লিংক
    else:
        file_url = f"https://t.me/{bot_username}?start=file_{str_to_b64(f'{owner_uid}:{file_id}')}"  # পুরনো লিংক
    btn = [[
        InlineKeyboardButton(
            "Cʟɪᴄᴋ Hᴇʀᴇ Tᴏ Gᴇᴛ Fɪʟᴇ..🍁",
            url=file_url
        )
    ]]

    await message.reply_photo(
        photo=VERIFY_IMG,
        caption=script.VERIFIED_COMPLETE_TEXT.format(message.from_user.mention),
        reply_markup=InlineKeyboardMarkup(btn)    
    )

    # ✅ user को verify कर दो
    await verify_user(client, int(userid), token, owner_uid)

    # ✅ log channel निकालना (owner DB से), fallback = LOG_CHANNEL
    owner = await db.get_user(owner_uid)
    log_channel = owner.get("log_channel") or LOG_CHANNEL

    # ✅ log send करना
    await client.send_message(
        log_channel,
        script.VERIFIED_LOG_TEXT.format(
            message.from_user.mention,
            message.from_user.id,
            datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%d %B %Y")
        )
    )
    return True

# -------------------------- VERIFICATION ENTRY -------------------------- #
async def av_verification(client, message, owner_uid: int = None, file_id="0"):
    db = get_db(client)   # ✨ মূল বট হলে মূল db, ক্লোন হলে ক্লোনের নিজস্ব db
    user_id = message.from_user.id

    owner = await db.get_user(owner_uid)
    download = owner.get("how_to_download", HOW_TO_VERIFY)
    verify = owner.get("verify", VERIFY)

    if verify and not await check_verification(client, user_id):
        # ✅ अब token में owner_uid + file_id bhi होगा
        bot_username = getattr(client, "username", None) or (await client.get_me()).username
        verify_url = await get_token(
            client,
            user_id,
            f"https://t.me/{bot_username}?start=",
            owner_uid,
            file_id
        )

        btn = [[
            InlineKeyboardButton("✅️ ᴠᴇʀɪғʏ ✅️", url=verify_url),
            InlineKeyboardButton("⁉️ ʜᴏᴡ ᴛᴏ ᴠᴇʀɪғʏ ⁉️", url=download)
        ], [
            InlineKeyboardButton(
                "😁 ʙᴜʏ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ - ɴᴏ ɴᴇᴇᴅ ᴛᴏ ᴠᴇʀɪғʏ 😁",
                callback_data='seeplans'
            )
        ]]

        d = await message.reply_text(
            text=script.VERIFICATION_TEXT.format(message.from_user.mention),
            protect_content=False,
            reply_markup=InlineKeyboardMarkup(btn),
            disable_web_page_preview=True,
            parse_mode=ParseMode.HTML
        )

        # 10 min बाद msg delete
        await asyncio.sleep(600)
        try:
            await d.delete()
            await message.delete()
        except:
            pass
        return False

    return True
