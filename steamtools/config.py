import os

from dotenv import load_dotenv

load_dotenv()

STEAM_API_KEY = os.environ.get("STEAM_API_KEY")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB", "steamtools")
