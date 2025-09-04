from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL, DB_NAME, AUTH_CHANNELS, VERIFY_EXPIRE, HOW_TO_VERIFY, VERIFY, VERIFIED_LOG
import httpx

# MongoDB Connection
client = AsyncIOMotorClient(DB_URL)
mydb = client[DB_NAME]

class Database:
    def __init__(self):
        self.users = mydb.users

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
            "verify_expire": VERIFY_EXPIRE,
            "custom_caption": None,
            "fsub_channels": AUTH_CHANNELS,
            "log_channel": VERIFIED_LOG,
            "protect_content": False,
            "how_to_download": HOW_TO_VERIFY,
            "verify": VERIFY,
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
        
# Instance of Database
db = Database()
