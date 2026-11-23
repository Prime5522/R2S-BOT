import secrets
import string
import time
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
from config import DB_URL, DB_NAME, AUTH_CHANNELS, VERIFY_EXPIRE, HOW_TO_VERIFY, VERIFY, VERIFIED_LOG, CLONE_DB_URL, DEFAULT_AUTO_DELETE_TIME
import httpx

client = AsyncIOMotorClient(DB_URL)
mydb = client[DB_NAME]

_CODE_ALPHABET = string.ascii_letters + string.digits
_CODE_LEN = 22


def _new_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LEN))


class Database:
    def __init__(self, custom_db=None):
        active_db = custom_db if custom_db is not None else mydb
        self.users = active_db.users
        self.files = active_db.files
        self.banned = active_db.banned

    def new_user(self, user_id, name):
        return {
            "user_id": user_id,
            "name": name,
            "verification_status": {
                "date": "1999-12-31",
                "time": "23:59:59"
            },
            "shortener_api": None,
            "base_site": None,
            "verify_api": None,
            "verify_site": None,
            "verify_expire": None,
            "custom_caption": None,
            "fsub_channels": [],
            "log_channel": None,
            "protect_content": False,
            "how_to_download": None,
            "verify": False,
            "permanent_link_mode": False,
            "auto_delete": True,
            "auto_delete_time": DEFAULT_AUTO_DELETE_TIME,
            "auto_delete_msg": None,
            "batch_mode": False,
            "batch_status_id": None,
            "media_list": [],
            "confirm_msgs": [],
            "user_files": []
        }

    async def add_user(self, user_id, name):
        if not await self.is_user_exist(user_id):
            user = self.new_user(user_id, name)
            await self.users.insert_one(user)

    async def is_user_exist(self, user_id):
        return bool(await self.users.find_one({'user_id': int(user_id)}))

    async def total_users_count(self):
        return await self.users.count_documents({})

    async def get_all_users(self):
        return self.users.find({})

    async def delete_user(self, user_id):
        await self.users.delete_many({'user_id': int(user_id)})

    # ================= ✨ Link storage (clean short codes) ✨ =================
    async def create_link(self, owner_uid: int, items: list = None, db_msg_id: int = None) -> str:
        """
        ছোট, পরিষ্কার কোড (যেমন Xk3J9aBq2LmZp0TrYw7NcD) বানিয়ে ডাটাবেসে সেভ করে।
        - ক্লোন বট: items = [ফাইলের তথ্য...]
        - মূল বট: db_msg_id = DB_CHANNEL-এর মেসেজ আইডি
        """
        for _ in range(6):
            code = _new_code()
            try:
                await self.files.insert_one({
                    "_id": code,
                    "owner_uid": int(owner_uid),
                    "items": items,
                    "db_msg_id": db_msg_id,
                    "created": int(time.time()),
                })
                return code
            except DuplicateKeyError:
                continue
        raise RuntimeError("Could not generate a unique link code")

    async def get_link(self, code: str):
        return await self.files.find_one({"_id": code})

    # পুরনো লিংকের জন্য (c_xxxxx আইডি) — আগের মতোই কাজ করবে
    async def save_clone_file(self, owner_uid: int, items: list) -> str:
        return await self.create_link(owner_uid, items=items)

    async def get_clone_file(self, stored_id: str):
        return await self.files.find_one({"_id": stored_id})

    # ================= ✨ Ban system ✨ =================
    async def ban_user(self, user_id: int, reason: str = None, by: int = None):
        await self.banned.update_one(
            {"user_id": int(user_id)},
            {"$set": {"user_id": int(user_id), "reason": reason, "by": by, "at": int(time.time())}},
            upsert=True,
        )

    async def unban_user(self, user_id: int) -> bool:
        res = await self.banned.delete_one({"user_id": int(user_id)})
        return res.deleted_count > 0

    async def is_banned(self, user_id: int) -> bool:
        return bool(await self.banned.find_one({"user_id": int(user_id)}))

    async def get_banned(self) -> list:
        return await self.banned.find({}).to_list(length=None)

    async def banned_count(self) -> int:
        return await self.banned.count_documents({})

    # Verification
    async def update_verification(self, user_id, date, time):
        status = {'date': str(date), 'time': str(time)}
        await self.users.update_one(
            {'user_id': int(user_id)},
            {'$set': {'verification_status': status}}
        )

    async def get_verified(self, user_id):
        default = {'date': "1999-12-31", 'time': "23:59:59"}
        user = await self.users.find_one({'user_id': int(user_id)})
        if user:
            return user.get("verification_status", default)
        return default

    async def get_all_verified_users(self):
        cursor = self.users.find({"verification_status.date": {"$ne": "1999-12-31"}})
        verified_users = []
        async for user in cursor:
            verified_users.append(user)
        return verified_users

    async def get_verified_users_count(self):
        return await self.users.count_documents({"verification_status.date": {"$ne": "1999-12-31"}})

    async def get_user(self, user_id: int):
        user = await self.users.find_one({"user_id": user_id})
        if not user:
            user = self.new_user(user_id, "Unknown")
            await self.users.insert_one(user)
        return user

    async def update_user_info(self, user_id: int, value: dict):
        await self.users.update_one({"user_id": user_id}, {"$set": value})

    async def reset_user(self, user_id: int):
        user = await self.get_user(user_id)
        default_user = self.new_user(user_id, user.get("name", "Unknown"))
        await self.users.update_one({"user_id": user_id}, {"$set": default_user})
        return default_user

    async def get_short_link(self, user: dict, link: str):
        api_key = user.get("shortener_api")
        base_site = user.get("base_site")
        if not api_key or not base_site:
            return link
        base_site = base_site.replace("https://", "").replace("http://", "").strip("/")
        try:
            async with httpx.AsyncClient() as http_client:
                response = await http_client.get(
                    f"https://{base_site}/api",
                    params={"api": api_key, "url": link},
                    timeout=10
                )
            if response.status_code != 200:
                return link
            data = response.json()
            if data.get("status") == "success":
                for key in ["shortenedUrl", "short", "url", "result", "shortenedUrl2"]:
                    if key in data and isinstance(data[key], str):
                        return data[key]
            return link
        except Exception as e:
            print(f"❌ Shortener error: {e}")
            return link

    async def get_verify_link(self, user: dict, link: str):
        api_key = user.get("verify_api")
        base_site = user.get("verify_site")
        if not api_key or not base_site:
            return link
        base_site = base_site.replace("https://", "").replace("http://", "").strip("/")
        try:
            async with httpx.AsyncClient() as http_client:
                response = await http_client.get(
                    f"https://{base_site}/api",
                    params={"api": api_key, "url": link},
                    timeout=10
                )
            if response.status_code != 200:
                return link
            data = response.json()
            if data.get("status") == "success":
                for key in ["shortenedUrl", "short", "url", "result", "shortenedUrl2"]:
                    if key in data and isinstance(data[key], str):
                        return data[key]
            return link
        except Exception as e:
            print(f"❌ Verify error: {e}")
            return link

    async def add_media(self, user_id, file_id):
        await self.users.update_one({"user_id": user_id}, {"$push": {"media_list": file_id}}, upsert=True)

    async def get_media(self, user_id):
        user = await self.users.find_one({"user_id": user_id})
        return user.get("media_list", []) if user else []

    async def clear_media(self, user_id):
        await self.users.update_one({"user_id": user_id}, {"$set": {"media_list": []}})

    async def add_confirm_msg(self, user_id, msg_id):
        await self.users.update_one({"user_id": user_id}, {"$push": {"confirm_msgs": msg_id}}, upsert=True)

    async def get_confirm_msgs(self, user_id):
        user = await self.users.find_one({"user_id": user_id})
        return user.get("confirm_msgs", []) if user else []

    async def clear_confirm_msgs(self, user_id):
        await self.users.update_one({"user_id": user_id}, {"$set": {"confirm_msgs": []}})

    async def add_user_file(self, user_id, msg_id):
        await self.users.update_one({"user_id": user_id}, {"$push": {"user_files": msg_id}}, upsert=True)

    async def get_user_files(self, user_id):
        user = await self.users.find_one({"user_id": user_id})
        return user.get("user_files", []) if user else []

    async def clear_user_files(self, user_id):
        await self.users.update_one({"user_id": user_id}, {"$set": {"user_files": []}})


db = Database()

_clone_mongo_clients: dict = {}
_clone_db_cache: dict = {}


def get_clone_database(bot_id: int, db_name: str, db_url: str = None) -> "Database":
    if bot_id in _clone_db_cache:
        return _clone_db_cache[bot_id]
    mongo_client = AsyncIOMotorClient(db_url or CLONE_DB_URL)
    clone_mongo_db = mongo_client[db_name]
    _clone_mongo_clients[bot_id] = mongo_client
    _clone_db_cache[bot_id] = Database(custom_db=clone_mongo_db)
    return _clone_db_cache[bot_id]


async def drop_clone_database(bot_id: int, db_name: str):
    mongo_client = _clone_mongo_clients.get(bot_id)
    if mongo_client is None:
        mongo_client = AsyncIOMotorClient(CLONE_DB_URL)
        
    try:
        await mongo_client.drop_database(db_name)
    finally:
        _clone_mongo_clients.pop(bot_id, None)
        _clone_db_cache.pop(bot_id, None)


def get_db(client) -> "Database":
    return getattr(client, "clone_db", db)
