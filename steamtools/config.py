import os

from dotenv import load_dotenv

load_dotenv()

STEAM_API_KEY = os.environ.get("STEAM_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
