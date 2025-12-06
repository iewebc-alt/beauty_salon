import os
from dotenv import load_dotenv

load_dotenv()

# --- База Данных ---
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_HOST = os.getenv("DB_HOST", "localhost")
# Порт с учетом Яндекса
DB_PORT = os.getenv("DB_PORT", "6432" if "yandexcloud" in str(DB_HOST) else "5432")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# --- Telegram & API ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = os.getenv("API_URL", "http://api:8000")

# --- YandexGPT ---
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

# --- Redis ---
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# --- АДМИНИСТРАТОРЫ ---

# 1. Старый админ (для совместимости)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

# 2. Супер-Админ (Владелец платформы SaaS)
SUPER_ADMIN_USERNAME = "root"
SUPER_ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD", "root")
