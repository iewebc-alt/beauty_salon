FROM python:3.10-slim

WORKDIR /app

# Обновляем системные пакеты
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

# Устанавливаем библиотеки (добавили Babel в конец списка)
RUN pip install --no-cache-dir \
    aiogram==3.10.0 \
    fastapi==0.111.0 \
    uvicorn==0.30.1 \
    sqlalchemy==2.0.30 \
    psycopg2-binary==2.9.9 \
    httpx==0.27.0 \
    python-dotenv==1.0.1 \
    redis==5.0.1 \
    Babel

COPY . .

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]