import os

from dotenv import load_dotenv

load_dotenv()

STEAM_API_KEY = os.environ.get("STEAM_API_KEY")
