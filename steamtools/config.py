import os

from dotenv import load_dotenv

load_dotenv()

STEAM_API_KEY = os.environ.get("STEAM_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
MAX_SCORES = int(os.environ.get("MAX_SCORES", "5"))
