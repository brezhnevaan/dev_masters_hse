import os
from dotenv import load_dotenv

import logging
logging.basicConfig(level=logging.DEBUG)

aiohttp_logger = logging.getLogger("aiohttp")
aiohttp_logger.setLevel(logging.DEBUG)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_WEATHER_TOKEN = os.getenv("API_WEATHER_TOKEN")
API_NUTRITIONIX_APP = os.getenv("API_NUTRITIONIX_APP")
API_NUTRITIONIX_TOKEN = os.getenv("API_NUTRITIONIX_TOKEN")
