"""
clone_manager.py
-----------------
প্রতিটা ক্লোন = একই process-এর ভেতরে চলা একটা নতুন pyrogram Client,
যেটা মূল বটের মতোই plugins/ ফোল্ডারের সবকিছু শেয়ার করে, কিন্তু নিজের
bot_token আর নিজের আলাদা ডাটাবেস (get_clone_database) নিয়ে চলে।

এই ফাইলটা কোনো pyrogram handler না (@Client.on_... কিছু নেই), তাই এটা
plugins/ ফোল্ডারে না রেখে bot.py-র পাশে রাখা হয়েছে — এতে pyrogram-এর
প্লাগিন-লোডার এটাকে আলাদা handler হিসেবে লোড করার চেষ্টা করবে না।
"""

import logging
import time

from pyrogram import Client
from pyrogram.errors import RPCError

from config import API_ID, API_HASH
from database import get_clone_database, drop_clone_database
from database.clonedb import clone_db

logger = logging.getLogger(__name__)

# bot_id -> চলমান Client instance
RUNNING_CLONES: dict = {}


async def start_clone(bot_token: str, owner_id: int):
    """
    একটা নতুন bot_token দিয়ে ক্লোন বট চালু করে।
    - টোকেন ভুল/ইনভ্যালিড হলে pyrogram নিজেই Client.start() এ এরর দেবে,
      সেটা এখান থেকে caller-এর কাছে bubble up হয়ে যাবে (caller handle করবে)।
    - একই bot_id আগে থেকে DB-তে থাকলে (যেমন restart/activate করার সময়)
      তার আগের db_name, start_pic, start_msg সব বহাল থাকবে।
    """
    temp_name = f"clone_{owner_id}_{int(time.time())}"

    clone_client = Client(
        name=temp_name,
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=bot_token,
        plugins={"root": "plugins"},
        workers=50,
        sleep_threshold=15,
        in_memory=True,   # ডিস্কে আলাদা session ফাইল লিখবে না
    )

    await clone_client.start()
    me = await clone_client.get_me()
    bot_id = me.id

    # যদি আগে থেকেই এই bot_id এর রেকর্ড থাকে (restart/activate কেস),
    # তাহলে সেই পুরোনো db_name, start_pic, start_msg বহাল রাখবো।
    existing = await clone_db.get_clone(bot_id)
    db_name = existing["db_name"] if existing else f"clone_{bot_id}"

    clone_doc = await clone_db.save_clone(
        owner_id=owner_id,
        bot_id=bot_id,
        bot_username=me.username,
        bot_token=bot_token,
        db_name=db_name,
        status="active",
    )

    # ✅ এই Client instance-কে তার নিজের পরিচয় ও ডাটাবেস দিয়ে সাজানো
    clone_client.is_clone = True
    clone_client.owner_id = owner_id
    clone_client.username = me.username
    clone_client.mention = me.mention
    clone_client.clone_db = get_clone_database(bot_id, db_name)
    clone_client.custom_start_pic = clone_doc.get("start_pic")
    clone_client.custom_start_txt = clone_doc.get("start_msg")

    RUNNING_CLONES[bot_id] = clone_client
    logger.info(f"Clone started: @{me.username} ({bot_id}) owner={owner_id}")
    return me


async def stop_clone(bot_id: int):
    """চলমান ক্লোন ক্লায়েন্ট বন্ধ করে (ডাটা/DB রেকর্ড মুছবে না, শুধু বট অফলাইন হবে)।"""
    bot_id = int(bot_id)
    running = RUNNING_CLONES.pop(bot_id, None)
    if running:
        try:
            await running.stop()
        except Exception as e:
            logger.warning(f"Error while stopping clone {bot_id}: {e}")


async def restart_clone(bot_id: int):
    """একটা নির্দিষ্ট ক্লোন বন্ধ করে আবার চালু করা (শুধু সেই একটা ক্লোন, বাকি সব অক্ষত)।"""
    clone_doc = await clone_db.get_clone(bot_id)
    if not clone_doc:
        raise ValueError("ক্লোন খুঁজে পাওয়া যায়নি।")
    await stop_clone(bot_id)
    return await start_clone(clone_doc["bot_token"], clone_doc["owner_id"])


async def delete_clone(bot_id: int):
    """ক্লোন সম্পূর্ণ ডিলিট — বট বন্ধ, মেটাডেটা মুছে, নিজস্ব ডাটাবেসও ড্রপ।"""
    clone_doc = await clone_db.get_clone(bot_id)
    await stop_clone(bot_id)
    await clone_db.delete_clone(bot_id)
    if clone_doc:
        await drop_clone_database(bot_id, clone_doc["db_name"])


async def load_all_clones():
    """
    মূল বট স্টার্ট হওয়ার সময় একবার কল হবে — DB-তে যতগুলো status='active'
    ক্লোন আছে, সবগুলোকে ব্যাকগ্রাউন্ডে আবার চালু করে দেবে (হোস্ট রিস্টার্ট
    হলেও ইউজারের কিছু করা লাগবে না)।
    """
    clones = await clone_db.get_all_active_clones()
    for c in clones:
        try:
            await start_clone(c["bot_token"], c["owner_id"])
        except (RPCError, Exception) as e:
            logger.error(f"❌ Failed to restore clone @{c.get('bot_username')}: {e}")
