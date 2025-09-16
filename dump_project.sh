#!/bin/bash

# Функция для вывода файла с заголовком
print_file() {
    if [ -f "$1" ]; then
        echo "--- START OF FILE $1 ---"
        cat "$1"
        echo -e "\n"
    else
        echo "--- FILE NOT FOUND: $1 ---"
        echo -e "\n"
    fi
}

echo "=================================================="
echo "           DUMPING PROJECT FILE CONTENTS"
echo "=================================================="
echo -e "\n"

# --- Корневые файлы ---
print_file "docker-compose.yml"
print_file "requirements.txt"
print_file "config.py"
print_file "database.py"
print_file "models.py"
print_file "fsm.py"
print_file "keyboards.py"
print_file "bot.py"
print_file "setup.py"
print_file "pytest.ini"

# --- Папка api ---
print_file "api/main.py"
print_file "api/dependencies.py"
print_file "api/schemas.py"

# --- Папка api/routers ---
print_file "api/routers/bot.py"

# --- Папка handlers ---
print_file "handlers/common.py"
print_file "handlers/booking.py"
print_file "handlers/appointments.py"

# --- Папка services ---
print_file "services/api_client.py"
print_file "services/gemini.py"

# --- Папка tests ---
print_file "tests/test_api.py"

# --- Шаблоны ---
print_file "templates/schedule.html"

# --- .env (Пример, чтобы не светить секреты) ---
echo "--- START OF FILE .env (EXAMPLE) ---"
echo "# --- Telegram Бот ---"
echo "BOT_TOKEN=\"YOUR_TELEGRAM_BOT_TOKEN\""
echo "API_URL=\"http://api:8000\""
echo ""
echo "# --- Gemini API ---"
echo "GEMINI_API_KEY=\"YOUR_GEMINI_API_KEY\""
echo ""
echo "# --- База Данных (для Docker) ---"
echo "DB_USER=\"your_db_user\""
echo "DB_PASSWORD=\"your_db_password\""
echo "DB_NAME=\"your_db_name\""
echo "DB_HOST=\"db\""
echo ""
echo "# --- Админка ---"
echo "ADMIN_USERNAME=\"admin\""
echo "ADMIN_PASSWORD=\"your_secure_admin_password\""
echo ""
echo "# --- Переменная для определения окружения ---"
echo "RUNNING_IN_DOCKER=1"
echo -e "\n"


echo "=================================================="
echo "                  DUMP COMPLETE"
echo "=================================================="
