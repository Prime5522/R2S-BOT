from pyrogram import Client
from pyrogram.errors import InternalServerError
from config import API_ID, API_HASH, BOT_TOKEN, LOG_CHANNEL, PORT, ADMINS, DB_URL, DB_NAME
from database import mydb
from session_store import (
    load_main_session_sync, save_main_session, clear_main_session,
    reset_to_token_login, SESSION_DEAD_ERRORS,
)
from aiohttp import web
from route import web_server
from clone_manager import load_all_clones, moderator_cleanup_loop
from bot_commands import set_public_commands, set_staff_commands
import asyncio
import pytz
from datetime import date, datetime


class Bot(Client):
    def __init__(self):
        # ✨ ডাটাবেসে সেভ করা সেশন থাকলে সেটা দিয়ে চালু — Telegram-এ নতুন লগইন কল লাগে না
        saved_session = load_main_session_sync(DB_URL, DB_NAME, BOT_TOKEN, API_ID)
        self._used_saved_session = bool(saved_session)
        super().__init__(
            name="PrimeXBots",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            session_string=saved_session,
            workers=200,
            plugins={"root": "plugins"},
            sleep_threshold=15,
            max_concurrent_transmissions=5,
        )

    async def start(self):
        # ✨ ওয়েব সার্ভার সবার আগে চালু — Koyeb/Heroku-র হেলথ-চেক (পোর্ট ৮০৮০) যাতে
        # টেলিগ্রামে লগইন হওয়ার আগেই পাস করে, নইলে প্ল্যাটফর্ম বারবার রিস্টার্ট দেয়।
        app_instance = await web_server()
        app_runner = web.AppRunner(app_instance)
        await app_runner.setup()
        site = web.TCPSite(app_runner, "0.0.0.0", int(PORT))
        await site.start()

        # ✨ টেলিগ্রামের সার্ভারে সাময়িক সমস্যা (500 RPC_CALL_FAIL) হলে বট ক্র্যাশ না করে
        # নিজে থেকে আবার চেষ্টা করবে (সর্বোচ্চ ৩০ বার, প্রতিবার ২০ সেকেন্ড অপেক্ষা)
        for attempt in range(1, 31):
            try:
                await super().start()
                break
            except SESSION_DEAD_ERRORS as e:
                # সেভ করা সেশন অচল (যেমন একই সময়ে দুই জায়গায় চালু) → মুছে টোকেন দিয়ে নতুন লগইন
                if not self._used_saved_session:
                    raise
                print(f"⚠️ Saved session is dead ({e.__class__.__name__}) — logging in with bot token...")
                await clear_main_session(mydb)
                reset_to_token_login(self)
                self._used_saved_session = False
            except InternalServerError as e:
                if attempt == 30:
                    raise
                print(f"⚠️ Telegram internal error ({e.__class__.__name__}), retry {attempt}/30 in 20s...")
                await asyncio.sleep(20)
        # ✨ নতুন লগইন হলে সেশন সেভ করে রাখা হয়
        if not self._used_saved_session:
            try:
                await save_main_session(mydb, await self.export_session_string(), BOT_TOKEN, API_ID)
                print("💾 Session saved to database")
            except Exception as e:
                print(f"⚠️ Could not save session: {e}")

        me = await self.get_me()
        self.bot_id = me.id
        self.first_name = me.first_name
        self.mention = me.mention
        self.username = me.username
        self.is_clone = False
        self.custom_start_pic = None
        self.custom_start_pic_bytes = None
        self.custom_start_txt = None
        self.custom_start_buttons = []

        tz = pytz.timezone('Asia/Kolkata')
        today = date.today()
        now = datetime.now(tz)
        time = now.strftime("%H:%M:%S %p")

        print(f"{me.first_name} STARTED ⚡️⚡️⚡️")

        try:
            await load_all_clones()
            print("✨ All Saved Clones Restored ✨")
        except Exception as e:
            print(f"❌ Failed to restore clones: {e}")

        # ✨ মূল বটের কমান্ড মেনু + মডারেটর মেয়াদ-ক্লিনআপ
        try:
            await set_public_commands(self)
            for admin in (ADMINS if isinstance(ADMINS, list) else [ADMINS]):
                await set_staff_commands(self, admin)
        except Exception as e:
            print(f"❌ Command setup failed: {e}")
        asyncio.create_task(moderator_cleanup_loop())

        if isinstance(ADMINS, list):
            for admin in ADMINS:
                await self.send_message(admin, f"**__{me.first_name} Is Started.....✨️__**")
        else:
            await self.send_message(ADMINS, f"**__{me.first_name} Is Started.....✨️__**")

        await self.send_message(
            LOG_CHANNEL,
            text=(
                f"<b>Restarted 🤖\n\n"
                f"📆 Date - <code>{today}</code>\n"
                f"🕙 Time - <code>{time}</code>\n"
                f"🌍 Time Zone - <code>Asia/Kolkata</code></b>"
            )
        )

    async def stop(self, *args):
        from clone_manager import RUNNING_CLONES
        for bot_id, clone_client in list(RUNNING_CLONES.items()):
            try:
                await clone_client.stop()
            except Exception:
                pass
        await super().stop()
        print("Bot Stopped")


Bot().run()
