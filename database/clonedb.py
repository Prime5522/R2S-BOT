"""
clonedb.py
----------
এই ফাইলটা শুধু ক্লোনের "মেটাডেটা" (কোন ইউজারের কোন বট, কোন টোকেন, কোন
db_name, অ্যাক্টিভ/ইনঅ্যাক্টিভ স্ট্যাটাস, স্টার্ট পিকচার/মেসেজ) মূল বটের
ডাটাবেসে `clones` নামের একটা কালেকশনে রাখে। প্রতিটা ক্লোনের নিজের
file/user ডাটা থাকে সম্পূর্ণ আলাদা ডাটাবেসে (দেখুন database/__init__.py
এর get_clone_database), এখানে শুধু "কোন ক্লোন কোথায়" তার হিসাব থাকে।
"""

from database import mydb


class CloneDB:
    def __init__(self):
        self.clones = mydb.clones

    # ---- Create / Update ----
    async def save_clone(
        self,
        owner_id: int,
        bot_id: int,
        bot_username: str,
        bot_token: str,
        db_name: str,
        status: str = "active",
    ):
        await self.clones.update_one(
            {"bot_id": bot_id},
            {
                "$set": {
                    "owner_id": owner_id,
                    "bot_id": bot_id,
                    "bot_username": bot_username,
                    "bot_token": bot_token,
                    "db_name": db_name,
                    "status": status,
                },
                "$setOnInsert": {
                    "start_pic": None,
                    "start_msg": None,
                },
            },
            upsert=True,
        )
        return await self.get_clone(bot_id)

    # ---- Read ----
    async def get_clone(self, bot_id: int):
        return await self.clones.find_one({"bot_id": int(bot_id)})

    async def get_user_clone(self, owner_id: int):
        """প্রতি ইউজারের ১টা করে ক্লোন — তাই এটা একটাই ডকুমেন্ট রিটার্ন করে।"""
        return await self.clones.find_one({"owner_id": int(owner_id)})

    async def get_user_clones_count(self, owner_id: int) -> int:
        return await self.clones.count_documents({"owner_id": int(owner_id)})

    async def get_all_active_clones(self) -> list:
        return await self.clones.find({"status": "active"}).to_list(length=None)

    async def total_clones_count(self) -> int:
        return await self.clones.count_documents({})

    # ---- Update ----
    async def set_status(self, bot_id: int, status: str):
        await self.clones.update_one({"bot_id": int(bot_id)}, {"$set": {"status": status}})

    async def update_clone_settings(self, bot_id: int, values: dict):
        await self.clones.update_one({"bot_id": int(bot_id)}, {"$set": values})

    # ---- Delete ----
    async def delete_clone(self, bot_id: int):
        await self.clones.delete_one({"bot_id": int(bot_id)})


# Instance
clone_db = CloneDB()
