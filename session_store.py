"""
✨ সেশন সেভ সিস্টেম
প্রতিবার রিস্টার্টে Telegram-এ নতুন করে "বট টোকেন দিয়ে লগইন" (auth.ImportBotAuthorization) করলে
একই API_ID থেকে অনেকগুলো লগইন কল যায় — এটাই Telegram-এর 500 এরর / রেট-লিমিটের বড় কারণ।
এখন প্রথমবার লগইনের পর সেশন ডাটাবেসে সেভ হয়; পরের বার সরাসরি সেটা দিয়ে চালু হয়, কোনো লগইন কল লাগে না।

নিরাপত্তা: সেশন তখনই ব্যবহার হয় যখন টোকেন + API_ID আগেরটার সাথে মেলে।
সেশন নষ্ট/অচল হলে নিজে থেকে মুছে টোকেন দিয়ে আবার লগইন করে।
"""
import hashlib
import logging

from pyrogram.errors import Unauthorized, AuthKeyDuplicated
from pyrogram.storage import MemoryStorage

logger = logging.getLogger(__name__)

# এই ত্রুটিগুলো মানে সেভ করা সেশন আর কাজ করছে না → মুছে টোকেন দিয়ে লগইন
SESSION_DEAD_ERRORS = (Unauthorized, AuthKeyDuplicated)


def fingerprint(bot_token: str, api_id) -> str:
    return hashlib.sha256(f"{bot_token.strip()}:{api_id}".encode()).hexdigest()


def load_main_session_sync(db_url: str, db_name: str, bot_token: str, api_id):
    """মূল বটের সেভ করা সেশন (Bot.__init__ সিঙ্ক্রোনাস, তাই pymongo দিয়ে পড়া হয়)"""
    try:
        from pymongo import MongoClient
        cli = MongoClient(db_url, serverSelectionTimeoutMS=8000)
        doc = cli[db_name].bot_sessions.find_one({"_id": "main"})
        cli.close()
        if doc and doc.get("fp") == fingerprint(bot_token, api_id) and doc.get("session"):
            return doc["session"]
    except Exception as e:
        logger.warning(f"Could not load saved main session: {e}")
    return None


async def save_main_session(mydb, session: str, bot_token: str, api_id):
    await mydb.bot_sessions.update_one(
        {"_id": "main"},
        {"$set": {"session": session, "fp": fingerprint(bot_token, api_id)}},
        upsert=True,
    )


async def clear_main_session(mydb):
    await mydb.bot_sessions.delete_one({"_id": "main"})


def reset_to_token_login(client):
    """
    সেভ করা সেশন বাতিল করে ক্লায়েন্টকে একদম নতুন (খালি) স্টোরেজে ফিরিয়ে দেয়,
    যাতে পরের start()-এ বট টোকেন দিয়ে নতুন লগইন হয়।
    """
    client.session_string = None
    client.storage = MemoryStorage(client.name)
