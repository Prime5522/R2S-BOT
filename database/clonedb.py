from database import mydb


class CloneDB:
    def __init__(self):
        self.clones = mydb.clones

    async def save_clone(
        self,
        owner_id: int,
        bot_id: int,
        bot_username: str,
        bot_token: str,
        db_name: str,
        status: str = "active",
        owner_mention: str = None,
    ):
        set_fields = {
            "owner_id": int(owner_id),
            "bot_id": int(bot_id),
            "bot_username": bot_username,
            "bot_token": bot_token,
            "db_name": db_name,
            "status": status,
        }
        if owner_mention:
            set_fields["owner_mention"] = owner_mention

        await self.clones.update_one(
            {"bot_id": int(bot_id)},
            {
                "$set": set_fields,
                "$setOnInsert": {
                    "start_pic": None,
                    "start_pic_bytes": None,
                    "start_msg": None,
                    "start_buttons": [],
                    "about_text": None,
                    "help_text": None,
                    "file_buttons": [],
                },
            },
            upsert=True,
        )
        return await self.get_clone(bot_id)

    async def get_clone(self, bot_id: int):
        return await self.clones.find_one({"bot_id": int(bot_id)})

    async def get_user_clone(self, owner_id: int):
        return await self.clones.find_one({"owner_id": int(owner_id)})

    async def get_user_clones_count(self, owner_id: int) -> int:
        return await self.clones.count_documents({"owner_id": int(owner_id)})

    async def get_all_active_clones(self) -> list:
        return await self.clones.find({"status": "active"}).to_list(length=None)

    async def total_clones_count(self) -> int:
        return await self.clones.count_documents({})

    async def set_status(self, bot_id: int, status: str):
        await self.clones.update_one({"bot_id": int(bot_id)}, {"$set": {"status": status}})

    async def update_clone_settings(self, bot_id: int, values: dict):
        await self.clones.update_one({"bot_id": int(bot_id)}, {"$set": values})

    async def delete_clone(self, bot_id: int):
        await self.clones.delete_one({"bot_id": int(bot_id)})


clone_db = CloneDB()
