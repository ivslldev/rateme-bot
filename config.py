"""Configuration loaded from .env file."""
import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))

# DEBUG_MODE enables the /test_profiles admin toolbox (fake profiles,
# identity switching, rating simulation). Keep False in production.
DEBUG_MODE: bool = os.getenv("DEBUG_MODE", "False").strip().lower() in ("true", "1", "yes")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "rateme.db")

ASSETS_DIR = os.path.join(BASE_DIR, "assets")
SCALE_MALE_IMG = os.path.join(ASSETS_DIR, "image_0.png")    # "True Adam" scale
SCALE_FEMALE_IMG = os.path.join(ASSETS_DIR, "image_1.png")  # "True Eve" scale
PLACEHOLDER_IMG = os.path.join(ASSETS_DIR, "placeholder.png")