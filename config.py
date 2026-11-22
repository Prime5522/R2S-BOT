from os import environ
import re
import os
from typing import List

API_ID = int(environ.get('API_ID', ''))
API_HASH = environ.get('API_HASH', '')
PORT = environ.get('PORT', '8080')
BOT_TOKEN = environ.get('BOT_TOKEN', "")
ADMINS = int(environ.get("ADMINS", "5926160191"))
LOG_CHANNEL = int(environ.get("LOG_CHANNEL", ""))
BOT_USERNAME = environ.get("BOT_USERNAME", "File_Store_Prime_Bot")
DB_CHANNEL = int(environ.get("DB_CHANNEL", ""))
URL = environ.get("URL", "")
BIN_CHANNEL = int(environ.get("BIN_CHANNEL", ""))
IS_FSUB = environ.get("IS_FSUB", True)  # Set "True" For Enable Force Subscribe
AUTH_CHANNELS = list(map(int, environ.get("AUTH_CHANNEL", "").split()))
# 💾 MongoDB Connection Information
DB_URL = environ.get('DATABASE_URI', "mongodb+srv://aman991932:aman@cluster0.4psab89.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0") # MongoDB connection URI
DB_NAME = environ.get('DATABASE_NAME', "Cluster0")  # MongoDB database name
FORWARD_AS_COPY = bool(os.environ.get("FORWARD_AS_COPY", True))
PICS = environ.get('PICS', '')
VERIFY_EXPIRE = int(environ.get('VERIFY_EXPIRE', 600))  # Time (in hours) after which verification expires
VERIFIED_LOG = int(environ.get('VERIFIED_LOG', '-1002227216574'))
HOW_TO_VERIFY = environ.get('HOW_TO_VERIFY', '')
VERIFY = environ.get("VERIFY", False)
VERIFY_IMG = environ.get("VERIFY_IMG", "https://graph.org/file/1669ab9af68eaa62c3ca4.jpg")  

WEBSITE_URL_MODE = bool(environ.get('WEBSITE_URL_MODE', True)) # Set True or False

# If Website Url Mode Is True Then Fill All Required Variable, If False Then Don't Fill.
WEBSITE_URL = environ.get("WEBSITE_URL", "https://filestoreprimebot.vercel.app") 

# ================= ✨ CLONE MODE SETTINGS ✨ =================
# মূল বটের ইউজারনেম (@ ছাড়া) — ক্লোন বট থেকে "Create My Own Clone" বাটনে
# ক্লিক করলে এই ইউজারনেমের বটে রিডাইরেক্ট করবে।
MAIN_BOT_USERNAME = environ.get("MAIN_BOT_USERNAME", BOT_USERNAME)

# একজন ইউজার সর্বোচ্চ কয়টা ক্লোন বানাতে পারবে (ডিফল্ট ১টা)
MAX_CLONE_PER_USER = int(environ.get("MAX_CLONE_PER_USER", "1"))

# ✨ About পেজে "Developer" হিসেবে যাকে ক্রেডিট দেখানো হবে (আপনার Telegram user ID)।
# খালি রাখলে শুধু স্টাইলড টেক্সট দেখাবে, ক্লিকযোগ্য মেনশন দেখাবে না।
MAIN_OWNER_ID = int(environ.get("MAIN_OWNER_ID", "5926160191")) or None

# ক্লোনদের নিজস্ব ডাটাবেসগুলো কোন MongoDB cluster-এ থাকবে।
# আলাদা করে না দিলে মূল DB_URL-এর cluster-ই ব্যবহার হবে, শুধু প্রতিটা
# ক্লোনের জন্য আলাদা db নাম (clone_<bot_id>) তৈরি হবে, তাই ডাটা আলাদাই থাকে।
CLONE_DB_URL = environ.get("CLONE_DB_URL", DB_URL)

# ✨ মূল বটে কেউ "Create Your Own Clone"-এ বট টোকেন পাঠালে, ক্লোন তৈরির আগে
# তাকে এই চ্যানেলে জয়েন হতেই হবে (/start নিজে ব্লক হবে না, শুধু টোকেন জমা
# দেওয়ার সময় চেক হবে)। খালি/0 রাখলে এই চেক বন্ধ থাকবে।
CLONE_CREATION_FSUB_CHANNEL = int(environ.get("CLONE_CREATION_FSUB_CHANNEL", "-1002245813234")) or None

# উপরের চ্যানেলের জয়েন লিংক — বট নিজে থেকে invite link বানাতে না পারলে (অ্যাডমিন
# না থাকলে) এটা ব্যবহার হবে। সেট না করলে বট নিজে invite link বানানোর চেষ্টা করবে।
CLONE_CREATION_FSUB_INVITE = environ.get("CLONE_CREATION_FSUB_INVITE", "")

# ✨ ক্লোন বট থেকে ফাইল ডেলিভারির আগে ২ সেকেন্ডের লোডিং স্ক্রিনে এই বাটন দেখাবে
CLONE_SOURCE_CODE_URL = environ.get("CLONE_SOURCE_CODE_URL", "https://t.me/PrimeXBots")
