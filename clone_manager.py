import logging
import time

from pyrogram import Client
from pyrogram.errors import RPCError

from config import API_ID, API_HASH, BOT_TOKEN, MAX_CLONE_PER_USER
from database import get_clone_database, drop_clone_database
from database.clonedb import clone_db

logger = logging.getLogger(__name__)

RUNNING_CLONES: dict = {}


async def start_clone(bot_token: str, owner_id: int):
    if bot_token.strip() == BOT_TOKEN.strip():
        raise ValueError("You cannot clone the main bot itself! Please create a new bot in @BotFather.")

    temp_name = f"clone_{owner_id}_{int(time.time())}"

    clone_client = Client(
        name=temp_name,
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=bot_token,
        plugins={"root": "plugins"},
        workers=30,
        sleep_threshold=15,
        in_memory=True,
    )

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
    )

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

    RUNNING_CLONES[bot_id] = clone_client
    logger.info(f"Clone started: @{me.username} ({bot_id}) owner={owner_id}")
    return me


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
