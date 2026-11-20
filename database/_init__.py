from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL, DB_NAME, AUTH_CHANNELS, VERIFY_EXPIRE, HOW_TO_VERIFY, VERIFY, VERIFIED_LOG, CLONE_DB_URL
import httpx

# MongoDB Connection (মূল বটের ডাটাবেস)
client = AsyncIOMotorClient(DB_URL)
mydb = client[DB_NAME]

class Database:
    # ✨ custom_db দিলে এই Database ইনস্ট্যান্স সেই (ক্লোনের নিজস্ব) mongo
    # database-এর উপর কাজ করবে, না দিলে মূল বটের mydb ব্যবহার হবে।
    def __init__(self, custom_db=None):
        self.users = (custom_db if custom_db is not None else mydb).users

    # 🧑‍💻 USER SYSTEM ------------------------------  
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
            "verify_expire": None,            # পরিবর্তিত: ডিফল্ট সময় থাকবে না, ফলব্যাক কাজ করবে
            "custom_caption": None,
            "fsub_channels": [],              # পরিবর্তিত: ডিফল্ট FSub চ্যানেল খালি থাকবে
            "log_channel": None,              # পরিবর্তিত: ডিফল্ট লগ চ্যানেল থাকবে না
            "protect_content": False,
            "how_to_download": None,          # পরিবর্তিত: ডিফল্ট টিউটোরিয়াল লিঙ্ক থাকবে না
            "verify": False,                  # পরিবর্তিত: ডিফল্ট ভেরিফিকেশন বন্ধ থাকবে
            "permanent_link_mode": False,
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

    # ✅ VERIFICATION SYSTEM -----------------------  
    async def update_verification(self, user_id, date, time):
        status = {
            'date': str(date),
            'time': str(time)
        }
        await self.users.update_one(
            {'user_id': int(user_id)},
            {'$set': {'verification_status': status}}
        )

    async def get_verified(self, user_id):
        default = {
            'date': "1999-12-31",
            'time': "23:59:59"
        }
        user = await self.users.find_one({'user_id': int(user_id)})
        if user:
            return user.get("verification_status", default)
        return default

    async def get_all_verified_users(self):
        cursor = self.users.find({
            "verification_status.date": {"$ne": "1999-12-31"}
        })
        verified_users = []
        async for user in cursor:
            verified_users.append(user)
        return verified_users

    async def get_verified_users_count(self):
        return await self.users.count_documents({
            "verification_status.date": {"$ne": "1999-12-31"}
        })

    # ---- Get User ----  
    async def get_user(self, user_id: int):
        user = await self.users.find_one({"user_id": user_id})
        if not user:
            user = self.new_user(user_id, "Unknown")
            await self.users.insert_one(user)
        return user

    # ---- Update User ----  
    async def update_user_info(self, user_id: int, value: dict):
        await self.users.update_one({"user_id": user_id}, {"$set": value})

    # ---------------- ♻️ Reset User Settings ----------------
    async def reset_user(self, user_id: int):
        """Reset a user to default settings"""
        user = await self.get_user(user_id)
        default_user = self.new_user(user_id, user.get("name", "Unknown"))
        await self.users.update_one({"user_id": user_id}, {"$set": default_user})
        return default_user

        
    # ---- Shortener Link Generator ----  
    async def get_short_link(self, user: dict, link: str):
        api_key = user.get("shortener_api")
        base_site = user.get("base_site")

        if not api_key or not base_site:
            return link

        base_site = base_site.replace("https://", "").replace("http://", "").strip("/")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://{base_site}/api",
                    params={"api": api_key, "url": link},
                    timeout=10
                )

            if response.status_code != 200:
                print(f"❌ Shortener HTTP Error: {response.status_code}")
                return link

            data = response.json()
            print("🔍 Shortener API Response:", data)

            if data.get("status") == "success":
                for key in ["shortenedUrl", "short", "url", "result", "shortenedUrl2"]:
                    if key in data and isinstance(data[key], str):
                        return data[key]

            return link
        except Exception as e:
            print(f"❌ Shortener error: {e}")
            return link

    # ---- Verify Link Generator ----  
    async def get_verify_link(self, user: dict, link: str):
        api_key = user.get("verify_api")
        base_site = user.get("verify_site")

        if not api_key or not base_site:
            return link

        base_site = base_site.replace("https://", "").replace("http://", "").strip("/")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://{base_site}/api",
                    params={"api": api_key, "url": link},
                    timeout=10
                )

            if response.status_code != 200:
                print(f"❌ Verify HTTP Error: {response.status_code}")
                return link

            data = response.json()
            print("🔍 Verify API Response:", data)

            if data.get("status") == "success":
                for key in ["shortenedUrl", "short", "url", "result", "shortenedUrl2"]:
                    if key in data and isinstance(data[key], str):
                        return data[key]

            return link
        except Exception as e:
            print(f"❌ Verify error: {e}")
            return link

    # 🟢 MediaList add/update
    async def add_media(self, user_id, file_id):
        await self.users.update_one(
            {"user_id": user_id},
            {"$push": {"media_list": file_id}},
            upsert=True
        )

    async def get_media(self, user_id):
        user = await self.users.find_one({"user_id": user_id})
        return user.get("media_list", []) if user else []

    async def clear_media(self, user_id):
        await self.users.update_one(
            {"user_id": user_id},
            {"$set": {"media_list": []}}
        )

    # 🟢 Confirmation Msgs
    async def add_confirm_msg(self, user_id, msg_id):
        await self.users.update_one(
            {"user_id": user_id},
            {"$push": {"confirm_msgs": msg_id}},
            upsert=True
        )

    async def get_confirm_msgs(self, user_id):
        user = await self.users.find_one({"user_id": user_id})
        return user.get("confirm_msgs", []) if user else []

    async def clear_confirm_msgs(self, user_id):
        await self.users.update_one(
            {"user_id": user_id},
            {"$set": {"confirm_msgs": []}}
        )

    # 🟢 UserFiles
    async def add_user_file(self, user_id, msg_id):
        await self.users.update_one(
            {"user_id": user_id},
            {"$push": {"user_files": msg_id}},
            upsert=True
        )

    async def get_user_files(self, user_id):
        user = await self.users.find_one({"user_id": user_id})
        return user.get("user_files", []) if user else []

    async def clear_user_files(self, user_id):
        await self.users.update_one(
            {"user_id": user_id},
            {"$set": {"user_files": []}}
        )
        
# Instance of Database (মূল বট)
db = Database()


# =============== ✨ CLONE DATABASE ISOLATION HELPERS ✨ ===============
# প্রতিটা ক্লোনের জন্য আলাদা Motor connection + Database instance ক্যাশ করে রাখা হয়,
# যাতে একই ক্লোন বারবার রিস্টার্ট/অ্যাক্সেস হলে নতুন কানেকশন না বানায়।
_clone_mongo_clients: dict = {}   # bot_id -> AsyncIOMotorClient
_clone_db_cache: dict = {}        # bot_id -> Database instance


def get_clone_database(bot_id: int, db_name: str, db_url: str = None) -> "Database":
    """
    ক্লোনের bot_id অনুযায়ী তার নিজস্ব, মূল বট থেকে সম্পূর্ণ আলাদা
    Database instance রিটার্ন করে (একই mongo cluster, কিন্তু আলাদা db নাম)।
    """
    if bot_id in _clone_db_cache:
        return _clone_db_cache[bot_id]

    mongo_client = AsyncIOMotorClient(db_url or CLONE_DB_URL)
    clone_mongo_db = mongo_client[db_name]

    _clone_mongo_clients[bot_id] = mongo_client
    _clone_db_cache[bot_id] = Database(custom_db=clone_mongo_db)
    return _clone_db_cache[bot_id]


async def drop_clone_database(bot_id: int, db_name: str):
    """ক্লোন ডিলিট করার সময় তার পুরো ডাটাবেস মুছে ফেলার জন্য।"""
    mongo_client = _clone_mongo_clients.get(bot_id)
    if mongo_client is None:
        mongo_client = AsyncIOMotorClient(CLONE_DB_URL)
    try:
        await mongo_client.drop_database(db_name)
    finally:
        _clone_mongo_clients.pop(bot_id, None)
        _clone_db_cache.pop(bot_id, None)


def get_db(client) -> "Database":
    """
    যেকোনো pyrogram Client (মূল বট বা কোনো ক্লোন) থেকে কল করলে সেই
    নির্দিষ্ট বটের নিজের Database instance রিটার্ন করে। প্রতিটা
    plugin হ্যান্ডলারের ভেতরে গ্লোবাল `db`-র বদলে এটা ব্যবহার করতে হবে,
    তাহলেই মূল বট ও প্রতিটা ক্লোনের ডাটা সম্পূর্ণ আলাদা থাকবে।
    """
    return getattr(client, "clone_db", db)
