from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN, LOG_CHANNEL, PORT, ADMINS
from aiohttp import web
from route import web_server
from clone_manager import load_all_clones
import pytz
from datetime import date, datetime

class Bot(Client):
    def __init__(self):
        super().__init__(
            name="avbotz",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=200,
            plugins={"root": "plugins"},
            sleep_threshold=15,
            max_concurrent_transmissions=5,
        )

    async def start(self):
        await super().start()
        me = await self.get_me()
        self.mention = me.mention
        self.username = me.username
        # ✨ এটা মূল বট — ক্লোন না, তাই is_clone সবসময় False থাকবে।
        self.is_clone = False
        self.custom_start_pic = None
        self.custom_start_txt = None

        tz = pytz.timezone('Asia/Kolkata')
        today = date.today()
        now = datetime.now(tz)
        time = now.strftime("%H:%M:%S %p")

        # 🌍 Web Server Initialization ✅
        app_instance = await web_server()
        app_runner = web.AppRunner(app_instance)
        await app_runner.setup()
        site = web.TCPSite(app_runner, "0.0.0.0", int(PORT))
        await site.start()

        print(f"{me.first_name} 𝚂𝚃𝙰𝚁𝚃𝙴𝙳 ⚡️⚡️⚡️")

        # ✨ আগে থেকে সেভ করা সব অ্যাক্টিভ ক্লোন আবার চালু করা (hosting restart হলেও)
        try:
            await load_all_clones()
            print("✨ Aʟʟ Sᴀᴠᴇᴅ Cʟᴏɴᴇꜱ Rᴇꜱᴛᴏʀᴇᴅ ✨")
        except Exception as e:
            print(f"❌ Failed to restore clones: {e}")

        # ✅ ADMINS को मैसेज भेजना
        if isinstance(ADMINS, list):
            for admin in ADMINS:
                await self.send_message(admin, f"**__{me.first_name} Iꜱ Sᴛᴀʀᴛᴇᴅ.....✨️😅😅😅__**")
        else:
            await self.send_message(ADMINS, f"**__{me.first_name} Iꜱ Sᴛᴀʀᴛᴇᴅ.....✨️😅😅😅__**")

        # ✅ LOG_CHANNEL में Restart Log भेजना
        await self.send_message(
            LOG_CHANNEL,
            text=(
                f"<b>ʀᴇsᴛᴀʀᴛᴇᴅ 🤖\n\n"
                f"📆 ᴅᴀᴛᴇ - <code>{today}</code>\n"
                f"🕙 ᴛɪᴍᴇ - <code>{time}</code>\n"
                f"🌍 ᴛɪᴍᴇ ᴢᴏɴᴇ - <code>Asia/Kolkata</code></b>"
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

# ✅ Run the Bot
Bot().run()
