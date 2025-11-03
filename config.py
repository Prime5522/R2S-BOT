from os import environ
import re
import os
from typing import List

API_ID = int(environ.get('API_ID', ''))
API_HASH = environ.get('API_HASH', '')
PORT = environ.get('PORT', '8080')
BOT_TOKEN = environ.get('BOT_TOKEN', "")
ADMINS = int(environ.get("ADMINS", "5977931010"))
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
