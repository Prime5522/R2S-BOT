import asyncio
import logging
import time

from pyrogram import Client
from pyrogram.errors import RPCError
from session_store import fingerprint, SESSION_DEAD_ERRORS

from config import API_ID, API_HASH, BOT_TOKEN, MAX_CLONE_PER_USER
from database import get_clone_database, drop_clone_database
from database.clonedb import clone_db
from bot_commands import set_public_commands, set_staff_commands, clear_staff_commands

logger = logging.getLogger(__name__)

RUNNING_CLONES: dict = {}


async def start_clone(bot_token: str, owner_id: int, owner_mention: str = None):
    if bot_token.strip() == BOT_TOKEN.strip():
        raise ValueError("You cannot clone the main bot itself! Please create a new bot in @BotFather.")

    temp_name = f"clone_{owner_id}_{int(time.time())}"
    fp = fingerprint(bot_token, API_ID)

    def make_client(session_string=None):
        return Client(
            name=temp_name,
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=bot_token,
            session_string=session_string,
            plugins={"root": "plugins"},
            workers=30,
            sleep_threshold=15,
            in_memory=True,
        )

    # ✨ আগে সেভ করা সেশন থাকলে সেটা দিয়ে চালু — Telegram-এ নতুন লগইন কল লাগে না
    saved = await clone_db.get_clone_by_token(bot_token)
    saved_session = saved.get("session_string") if saved and saved.get("session_fp") == fp else None
    used_saved = False

    clone_client = make_client(saved_session)
    try:
        await clone_client.start()
        used_saved = bool(saved_session)
    except SESSION_DEAD_ERRORS:
        if not saved_session:
            raise
        logger.warning(f"Saved session of clone {saved.get('bot_username')} is dead; logging in with token.")
        await clone_db.clear_session(saved["bot_id"])
        clone_client = make_client(None)
        await clone_client.start()
    me = await clone_client.get_me()
    bot_id = me.id

    user_existing = await clone_db.get_user_clone(owner_id)
    if user_existing and int(user_existing["bot_id"]) != int(bot_id):
        await clone_client.stop()
        raise ValueError(
            f"You already have a cloned bot (@{user_existing.get('bot_username')}). "
            f"Only {MAX_CLONE_PER_USER} clone per user is allowed."
        )

    existing = await clone_db.get_clone(bot_id)
    if existing and int(existing["owner_id"]) != int(owner_id):
        is_same_active_token = (
            existing.get("bot_token") == bot_token
            and existing.get("status") == "active"
            and bot_id in RUNNING_CLONES
        )
        if is_same_active_token:
            await clone_client.stop()
            raise ValueError("This bot is already active and cloned by another user.")
        await stop_clone(bot_id)
        await drop_clone_database(bot_id, existing["db_name"])
        await clone_db.delete_clone(bot_id)
        existing = None

    if bot_id in RUNNING_CLONES:
        try:
            await RUNNING_CLONES[bot_id].stop()
        except Exception:
            pass

    db_name = existing["db_name"] if existing else f"clone_{bot_id}"

    clone_doc = await clone_db.save_clone(
        owner_id=owner_id,
        bot_id=bot_id,
        bot_username=me.username,
        bot_token=bot_token,
        db_name=db_name,
        status="active",
        owner_mention=owner_mention,
    )

    # ✨ নতুন লগইন হলে সেশন সেভ করে রাখা হয় (পরের রিস্টার্টে লগইন কল বাঁচে)
    if not used_saved:
        try:
            await clone_db.save_session(bot_id, await clone_client.export_session_string(), fp)
        except Exception as e:
            logger.warning(f"Could not save session for @{me.username}: {e}")

    clone_client.is_clone = True
    clone_client.bot_id = bot_id
    clone_client.owner_id = int(owner_id)
    clone_client.username = me.username
    clone_client.first_name = me.first_name
    clone_client.mention = me.mention
    clone_client.clone_db = get_clone_database(bot_id, db_name)
    clone_client.custom_start_pic = clone_doc.get("start_pic")
    raw_pic_bytes = clone_doc.get("start_pic_bytes")
    clone_client.custom_start_pic_bytes = bytes(raw_pic_bytes) if raw_pic_bytes else None
    clone_client.custom_start_txt = clone_doc.get("start_msg")
    clone_client.custom_start_buttons = clone_doc.get("start_buttons") or []
    clone_client.custom_about_txt = clone_doc.get("about_text")
    clone_client.custom_help_txt = clone_doc.get("help_text")
    clone_client.custom_file_buttons = clone_doc.get("file_buttons") or []
    clone_client.owner_mention = clone_doc.get("owner_mention")
    clone_client.moderators = clone_doc.get("moderators") or []
    clone_client.storage_channel = clone_doc.get("storage_channel")
    clone_client.started_at = time.time()

    RUNNING_CLONES[bot_id] = clone_client

    # ✨ ক্লোন হওয়ার সাথে সাথেই কমান্ড মেনু সেট (সবার জন্য + ওনার/মডারেটরদের জন্য আলাদা)
    try:
        await set_public_commands(clone_client)
        await set_staff_commands(clone_client, int(owner_id))
        for m in clone_client.moderators:
            if m.get("expires_at", 0) > time.time():
                await set_staff_commands(clone_client, int(m["user_id"]))
    except Exception as e:
        logger.warning(f"Command setup failed for @{me.username}: {e}")
    logger.info(f"Clone started: @{me.username} ({bot_id}) owner={owner_id}")
    return me


async def change_clone_bot(old_bot_id: int, new_token: str):
    """
    ✨ Change Bot: একই ক্লোন (সেটিংস, ইউজার, মডারেটর, স্টোরেজ চ্যানেল, লিংক) থাকবে —
    শুধু বট বদলে নতুন টোকেনের বট হবে। পুরনো পার্মানেন্ট লিংক নিজে থেকে নতুন বটে যাবে।
    """
    new_token = new_token.strip()
    doc = await clone_db.get_clone(old_bot_id)
    if not doc:
        raise ValueError("Clone not found.")
    if new_token == BOT_TOKEN.strip():
        raise ValueError("You cannot use the main bot as your clone.")
    if new_token == doc.get("bot_token"):
        raise ValueError("This is already your current bot's token.")

    # নতুন টোকেন ঠিক আছে কিনা — আলাদা অস্থায়ী ক্লায়েন্টে যাচাই
    tmp = Client(
        name=f"chg_{old_bot_id}_{int(time.time())}",
        api_id=API_ID, api_hash=API_HASH, bot_token=new_token, in_memory=True,
    )
    await tmp.start()
    try:
        me = await tmp.get_me()
        if await clone_db.get_clone(me.id):
            raise ValueError("This bot is already registered as a clone.")
        session = await tmp.export_session_string()
    finally:
        await tmp.stop()

    await stop_clone(old_bot_id)
    await clone_db.replace_clone_bot(old_bot_id, me.id, me.username, new_token, session, fingerprint(new_token, API_ID))
    return await start_clone(new_token, int(doc["owner_id"]), owner_mention=doc.get("owner_mention"))


async def stop_clone(bot_id: int):
    bot_id = int(bot_id)
    running = RUNNING_CLONES.pop(bot_id, None)
    if running:
        try:
            await running.stop()
        except Exception as e:
            logger.warning(f"Error while stopping clone {bot_id}: {e}")


async def restart_clone(bot_id: int):
    clone_doc = await clone_db.get_clone(bot_id)
    if not clone_doc:
        raise ValueError("Clone not found.")
    await stop_clone(bot_id)
    return await start_clone(clone_doc["bot_token"], clone_doc["owner_id"])


async def delete_clone(bot_id: int):
    clone_doc = await clone_db.get_clone(bot_id)
    await stop_clone(bot_id)
    await clone_db.delete_clone(bot_id)
    if clone_doc:
        await drop_clone_database(bot_id, clone_doc["db_name"])


async def load_all_clones():
    clones = await clone_db.get_all_active_clones()
    for c in clones:
        try:
            await start_clone(c["bot_token"], c["owner_id"])
        except (RPCError, Exception) as e:
            logger.error(f"Failed to restore clone @{c.get('bot_username')}: {e}")
        await asyncio.sleep(1)  # একসাথে সব ক্লোনের লগইন/কানেকশন ঝাঁপিয়ে না পড়তে


async def moderator_cleanup_loop(interval: int = 600):
    """মেয়াদ-শেষ মডারেটরদের নিজে থেকে সরিয়ে দেয় (ডাটাবেস + কমান্ড মেনু)"""
    while True:
        await asyncio.sleep(interval)
        for bot_id, client in list(RUNNING_CLONES.items()):
            try:
                expired = await clone_db.purge_expired_moderators(bot_id)
                if not expired:
                    continue
                doc = await clone_db.get_clone(bot_id)
                client.moderators = (doc or {}).get("moderators") or []
                for uid in expired:
                    await clear_staff_commands(client, uid)
            except Exception as e:
                logger.warning(f"Moderator cleanup failed for {bot_id}: {e}")
