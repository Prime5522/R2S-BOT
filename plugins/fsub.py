# plugins/fsub.py
from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import UserNotParticipant
from config import AUTH_CHANNELS
from database import db


async def get_fsub(bot: Client, message: Message, owner_uid: int = None) -> bool:
    user_id = message.from_user.id
    me = await bot.get_me()

    # 👇 अगर owner_uid दिया है तो उसकी channels लो, वरना default AUTH_CHANNELS
    if owner_uid:
        owner = await db.get_user(owner_uid)
        channels = owner.get("fsub_channels", AUTH_CHANNELS)
    else:
        channels = AUTH_CHANNELS

    not_joined_channels = []

    for channel_id in channels:
        try:
            await bot.get_chat_member(channel_id, user_id)
        except UserNotParticipant:
            try:
                chat = await bot.get_chat(channel_id)
                invite_link = await bot.export_chat_invite_link(channel_id)
                not_joined_channels.append((chat.title, invite_link))
            except Exception as e:
                print(f"[ERROR] Channel Fetch Failed: {e}")
                continue
        except Exception as e:
            print(f"[ERROR] Chat Member Check Failed: {e}")
            continue

    if not_joined_channels:
        join_buttons = [
            [InlineKeyboardButton(f"[{i+1}] {title}", url=link)]
            for i, (title, link) in enumerate(not_joined_channels)
        ]

        # ✅ args निकालो safe तरीके से
        args = None
        if message.text:
            parts = message.text.split()
            if len(parts) > 1:
                args = parts[1]

        if args:
            join_buttons.append([InlineKeyboardButton(
                "♻️ Try Again ♻️",
                url=f"https://t.me/{me.username}?start={args}"
            )])
        else:
            join_buttons.append([InlineKeyboardButton(
                "♻️ Try Again ♻️",
                url=f"https://t.me/{me.username}?start=true"
            )])

        await message.reply(
            "<i>🚨 Please Join Owner's Channels First To Use This File.\n"
            "Click The Below Buttons To Join All Channels And Then Press Try Again ✅</i>",
            reply_markup=InlineKeyboardMarkup(join_buttons)
        )
        return False
    return True
