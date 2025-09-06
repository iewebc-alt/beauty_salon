import os
from dotenv import load_dotenv

load_dotenv()

# --- База Данных ---
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ ---
# Если переменная окружения RUNNING_IN_DOCKER установлена, используем 'db'.
# Иначе (при ручном запуске) используем 'localhost'.
if os.getenv("RUNNING_IN_DOCKER"):
    DB_HOST = os.getenv("DB_HOST", "db")
else:
    DB_HOST = "localhost"
# --- КОНЕЦ ИЗМЕНЕНИЯ ---

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"

# --- Telegram Бот ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = os.getenv("API_URL", "http://api:8000")

# --- Админка ---
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
