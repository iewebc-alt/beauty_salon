import os
from datetime import timezone
from dotenv import load_dotenv

load_dotenv()

# --- UTC ---
UTC = timezone.utc

# --- База Данных ---
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# Если переменная окружения RUNNING_IN_DOCKER установлена, используем 'db'.
# Иначе (при ручном запуске) используем 'localhost'.
if os.getenv("RUNNING_IN_DOCKER"):
    DB_HOST = os.getenv("DB_HOST", "db")
else:
    DB_HOST = "localhost"

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"

# --- Telegram Бот ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = os.getenv("API_URL")  # Исправлено: добавлена закрывающая скобка

# --- Redis ---
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

# --- Админка ---
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# --- Gemini ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Окружение ---
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
RUNNING_IN_DOCKER = os.getenv("RUNNING_IN_DOCKER", "0") == "1"
