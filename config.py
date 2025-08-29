from os import environ
import re
import os
from typing import List

API_ID = int(environ.get('API_ID', ''))
API_HASH = environ.get('API_HASH', '')
PORT = environ.get('PORT', '8080')
BOT_TOKEN = environ.get('BOT_TOKEN', "")
ADMINS = int(environ.get("ADMINS", ""))
LOG_CHANNEL = int(environ.get("LOG_CHANNEL", ""))
BOT_USERNAME = environ.get("BOT_USERNAME", "")
DB_CHANNEL = int(environ.get("DB_CHANNEL", ""))
URL = environ.get("URL", "https://bumpy-liana-prime-movie-search-bot-cec26958.koyeb.app")
BIN_CHANNEL = int(environ.get("BIN_CHANNEL", ""))
IS_FSUB = environ.get("IS_FSUB", True)  # Set "True" For Enable Force Subscribe
AUTH_CHANNELS = list(map(int, environ.get("AUTH_CHANNEL", "").split()))
# 💾 MongoDB Connection Information
DB_URL = environ.get('DATABASE_URI', "") # MongoDB connection URI
DB_NAME = environ.get('DATABASE_NAME', "Cluster0")  # MongoDB database name
FORWARD_AS_COPY = bool(os.environ.get("FORWARD_AS_COPY", True))
PICS = environ.get('PICS', '')
VERIFY_EXPIRE = int(environ.get('VERIFY_EXPIRE', 600))  # Time (in hours) after which verification expires
VERIFIED_LOG = int(environ.get('VERIFIED_LOG', ''))
HOW_TO_VERIFY = environ.get('HOW_TO_VERIFY', '')
VERIFY = environ.get("VERIFY", False)
VERIFY_IMG = environ.get("VERIFY_IMG", "")  

WEBSITE_URL_MODE = bool(environ.get('WEBSITE_URL_MODE', False)) # Set True or False

# If Website Url Mode Is True Then Fill All Required Variable, If False Then Don't Fill.
WEBSITE_URL = environ.get("WEBSITE_URL", "") 
#exmp: https://filestoreprimebot.vercel.app
