from os import environ
import re
import os
from typing import List

API_ID = int(environ.get('API_ID', '21956488'))
API_HASH = environ.get('API_HASH', '812529f879f06436925c7d62eb49f5d1')
PORT = environ.get('PORT', '8080')
BOT_TOKEN = environ.get('BOT_TOKEN', "8314882997:AAGKLc0nVniEmC97xFuP-IS7ujor0YUcfUo")
ADMINS = int(environ.get("ADMINS", "5977931010"))
LOG_CHANNEL = int(environ.get("LOG_CHANNEL", "-1002110971750"))
BOT_USERNAME = environ.get("BOT_USERNAME", "AV_F2S_BOT")
DB_CHANNEL = int(environ.get("DB_CHANNEL", "-1001973960964"))
URL = environ.get("URL", "https://integral-trista-vnnmbs-5d76313f.koyeb.app")
BIN_CHANNEL = int(environ.get("BIN_CHANNEL", "-1001973960964"))
IS_FSUB = environ.get("IS_FSUB", True)  # Set "True" For Enable Force Subscribe
AUTH_CHANNELS = list(map(int, environ.get("AUTH_CHANNEL", "-1002012150170 -1002102037760").split()))
# 💾 MongoDB Connection Information
DB_URL = environ.get('DATABASE_URI', "mongodb+srv://aman991932:aman@cluster0.4psab89.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0") # MongoDB connection URI
DB_NAME = environ.get('DATABASE_NAME', "Cluster0")  # MongoDB database name
FORWARD_AS_COPY = bool(os.environ.get("FORWARD_AS_COPY", True))
PICS = environ.get('PICS', 'https://image.zaw-myo.workers.dev/image/4ff3401c-7bbf-4c0e-9ae2-b1cdc6fd8cdf')
VERIFY_EXPIRE = int(environ.get('VERIFY_EXPIRE', 600))  # Time (in hours) after which verification expires
VERIFIED_LOG = int(environ.get('VERIFIED_LOG', '-1002227216574'))
HOW_TO_VERIFY = environ.get('HOW_TO_VERIFY', 'https://t.me/AV_BOTz_UPDATE')
VERIFY = environ.get("VERIFY", False)
VERIFY_IMG = environ.get("VERIFY_IMG", "https://graph.org/file/1669ab9af68eaa62c3ca4.jpg")  

WEBSITE_URL_MODE = bool(environ.get('WEBSITE_URL_MODE', True)) # Set True or False

# If Website Url Mode Is True Then Fill All Required Variable, If False Then Don't Fill.
WEBSITE_URL = environ.get("WEBSITE_URL", "https://av-f2-s-bot.vercel.app") 
