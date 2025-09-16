# 1. Используем официальный легковесный образ Python 3.9
#FROM python:3.9-slim
FROM python:3.11-slim

# 2. Устанавливаем рабочую директорию внутри будущего контейнера
WORKDIR /app

# 3. Копируем ТОЛЬКО файл с зависимостями
COPY requirements.txt .

# 4. Устанавливаем системные зависимости, необходимые для некоторых Python-библиотек
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 5. Устанавливаем Python-зависимости, используя requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 6. Копируем весь остальной код нашего проекта
COPY . .

# 7. Указываем Docker, что наше приложение будет слушать порт 8000
EXPOSE 8000

# 8. Команда по умолчанию, которая будет запускаться при старте контейнера
# Запускаем uvicorn, чтобы он был доступен извне контейнера (0.0.0.0)
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
