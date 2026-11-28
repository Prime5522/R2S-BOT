import time

from database import mydb


# ================= ✨ Access helpers ✨ =================
def is_owner(clone_doc: dict, user_id: int) -> bool:
    return bool(clone_doc) and int(clone_doc.get("owner_id", 0)) == int(user_id)


def active_moderators(clone_doc: dict) -> list:
    now = time.time()
    return [m for m in (clone_doc.get("moderators") or []) if m.get("expires_at", 0) > now]


def is_active_moderator(clone_doc: dict, user_id: int) -> bool:
    return any(int(m["user_id"]) == int(user_id) for m in active_moderators(clone_doc))


def has_clone_access(clone_doc: dict, user_id: int) -> bool:
    """ওনার অথবা মেয়াদ-থাকা মডারেটর"""
    return bool(clone_doc) and (is_owner(clone_doc, user_id) or is_active_moderator(clone_doc, user_id))


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
                    "moderators": [],
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

    # ================= ✨ Clone statistics (admin) ✨ =================
    async def bump_deleted(self):
        """কতগুলো ক্লোন ডিলিট হয়েছে তার স্থায়ী কাউন্টার (ডিপ্লয়ের পর থেকে গোনা শুরু)"""
        await mydb.clone_stats.update_one({"_id": "counts"}, {"$inc": {"deleted": 1}}, upsert=True)

    async def get_clone_counts(self) -> dict:
        total = await self.clones.count_documents({})
        active = await self.clones.count_documents({"status": "active"})
        doc = await mydb.clone_stats.find_one({"_id": "counts"}) or {}
        return {
            "total": total,
            "active": active,
            "inactive": total - active,
            "deleted": int(doc.get("deleted", 0)),
        }

    async def set_status(self, bot_id: int, status: str):
        await self.clones.update_one({"bot_id": int(bot_id)}, {"$set": {"status": status}})

    async def update_clone_settings(self, bot_id: int, values: dict):
        await self.clones.update_one({"bot_id": int(bot_id)}, {"$set": values})

    # ================= ✨ Permanent-link index (code → clone bot) ✨ =================
    async def index_link(self, code: str, bot_id: int):
        await mydb.link_index.update_one({"_id": code}, {"$set": {"bot_id": int(bot_id)}}, upsert=True)

    async def get_link_bot(self, code: str):
        doc = await mydb.link_index.find_one({"_id": code})
        return int(doc["bot_id"]) if doc else None

    async def delete_link_index(self, bot_id: int):
        await mydb.link_index.delete_many({"bot_id": int(bot_id)})

    # ================= ✨ Change Bot (একই ক্লোন, নতুন বট) ✨ =================
    async def replace_clone_bot(self, old_bot_id: int, new_bot_id: int, username: str,
                                token: str, session: str, fp: str):
        await self.clones.update_one(
            {"bot_id": int(old_bot_id)},
            {"$set": {
                "bot_id": int(new_bot_id), "bot_username": username, "bot_token": token,
                "session_string": session, "session_fp": fp, "status": "active",
                "start_pic": None,  # file_id বটভেদে আলাদা — নতুন বট প্রথম /start-এ bytes থেকে নিজেই বানিয়ে নেবে
            }},
        )
        await mydb.link_index.update_many({"bot_id": int(old_bot_id)}, {"$set": {"bot_id": int(new_bot_id)}})

    # ================= ✨ Saved sessions ✨ =================
    async def get_clone_by_token(self, bot_token: str):
        return await self.clones.find_one({"bot_token": bot_token})

    async def save_session(self, bot_id: int, session: str, fp: str):
        await self.clones.update_one(
            {"bot_id": int(bot_id)}, {"$set": {"session_string": session, "session_fp": fp}}
        )

    async def clear_session(self, bot_id: int):
        await self.clones.update_one(
            {"bot_id": int(bot_id)}, {"$unset": {"session_string": "", "session_fp": ""}}
        )

    # ================= ✨ Moderators ✨ =================
    async def get_moderated_clones(self, user_id: int) -> list:
        return await self.clones.find({
            "moderators": {"$elemMatch": {"user_id": int(user_id), "expires_at": {"$gt": time.time()}}}
        }).to_list(length=None)

    async def add_moderator(self, bot_id: int, user_id: int, expires_at: float, added_by: int, name: str = None):
        await self.clones.update_one({"bot_id": int(bot_id)}, {"$pull": {"moderators": {"user_id": int(user_id)}}})
        await self.clones.update_one(
            {"bot_id": int(bot_id)},
            {"$push": {"moderators": {
                "user_id": int(user_id),
                "expires_at": float(expires_at),
                "added_by": int(added_by),
                "name": name or str(user_id),
            }}},
        )

    async def remove_moderator(self, bot_id: int, user_id: int):
        await self.clones.update_one({"bot_id": int(bot_id)}, {"$pull": {"moderators": {"user_id": int(user_id)}}})

    async def clear_moderators(self, bot_id: int):
        await self.clones.update_one({"bot_id": int(bot_id)}, {"$set": {"moderators": []}})

    async def purge_expired_moderators(self, bot_id: int) -> list:
        """মেয়াদ শেষ মডারেটরদের মুছে ফেলে, তাদের ID লিস্ট রিটার্ন করে"""
        doc = await self.get_clone(bot_id)
        if not doc:
            return []
        now = time.time()
        expired = [int(m["user_id"]) for m in (doc.get("moderators") or []) if m.get("expires_at", 0) <= now]
        if expired:
            await self.clones.update_one(
                {"bot_id": int(bot_id)},
                {"$pull": {"moderators": {"expires_at": {"$lte": now}}}},
            )
        return expired

    async def delete_clone(self, bot_id: int):
        await self.clones.delete_one({"bot_id": int(bot_id)})


clone_db = CloneDB()
