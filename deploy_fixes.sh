```bash
#!/bin/bash

# deploy_fixes.sh - Автоматизированное развертывание исправлений для Beauty Salon проекта
# Запуск: chmod +x deploy_fixes.sh && ./deploy_fixes.sh
# Требования: Git, Docker, Docker Compose, python3-venv, dos2unix

set -e  # Остановка на ошибке
LOG_FILE="deploy_fixes.log"
echo "Starting deployment at $(date)" > "$LOG_FILE"

PROJECT_DIR="$(pwd)"
echo "Starting deployment in directory: $PROJECT_DIR" | tee -a "$LOG_FILE"

# Проверка директории проекта
if [[ ! -f "docker-compose.yml" ]]; then
    echo "Error: This script must be run in the project root (where docker-compose.yml exists)." | tee -a "$LOG_FILE"
    exit 1
fi

# Проверка прав доступа
if [[ ! -w "$PROJECT_DIR" ]]; then
    echo "Error: No write permissions in $PROJECT_DIR." | tee -a "$LOG_FILE"
    exit 1
fi

# Проверка и установка dos2unix
if ! command -v dos2unix &>/dev/null; then
    echo "Installing dos2unix..." | tee -a "$LOG_FILE"
    apt update && apt install -y dos2unix || {
        echo "Error: Failed to install dos2unix. Please install it manually." | tee -a "$LOG_FILE"
        exit 1
    }
fi

# Создание виртуального окружения, если отсутствует
if [[ ! -d "venv" ]]; then
    echo "Creating virtual environment..." | tee -a "$LOG_FILE"
    python3 -m venv venv || {
        echo "Error: Failed to create virtual environment." | tee -a "$LOG_FILE"
        exit 1
    }
fi
source venv/bin/activate

# Создание бэкапа
BACKUP_DIR="$PROJECT_DIR/backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
echo "Creating backup in: $BACKUP_DIR" | tee -a "$LOG_FILE"

FILES_TO_BACKUP=(
    "config.py"
    "bot.py"
    "docker-compose.yml"
    "requirements.txt"
    "api/main.py"
    "api/routers/bot.py"
    "handlers/common.py"
    "handlers/appointments.py"
    "handlers/booking.py"
    "tests/test_api.py"
    "services/gemini.py"
)

for file in "${FILES_TO_BACKUP[@]}"; do
    if [[ -f "$file" ]]; then
        mkdir -p "$(dirname "$BACKUP_DIR/$file")"
        cp "$file" "$BACKUP_DIR/$file" 2>/dev/null && echo "Backup: $file" | tee -a "$LOG_FILE" || echo "Warning: Failed to backup $file" | tee -a "$LOG_FILE"
    else
        echo "Warning: File $file not found, skipping backup." | tee -a "$LOG_FILE"
    fi
done

echo "Backup completed. Restore with: cp -r $BACKUP_DIR/* ." | tee -a "$LOG_FILE"

# Проверка и создание .env
if [[ ! -f ".env" ]]; then
    echo "Warning: .env not found, creating example..." | tee -a "$LOG_FILE"
    cat << 'ENV_EOF' > .env
# --- Telegram Бот ---
BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
API_URL="http://api:8000"

# --- Gemini API ---
GEMINI_API_KEY="YOUR_GEMINI_API_KEY"

# --- База Данных (для Docker) ---
DB_USER="your_db_user"
DB_PASSWORD="your_secure_db_password_16chars+"
DB_NAME="your_db_name"
DB_HOST="db"

# --- Админка ---
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="your_secure_admin_password_16chars+"

# --- Redis ---
REDIS_HOST="redis"
REDIS_PORT=6379
REDIS_PASSWORD="your_secure_redis_password"

# --- Окружение ---
RUNNING_IN_DOCKER=1
ENVIRONMENT="prod"
DEBUG=False
ENV_EOF
    echo "Created .env. Replace placeholders (YOUR_*) with real values." | tee -a "$LOG_FILE"
else
    echo ".env found, using existing." | tee -a "$LOG_FILE"
fi

# Замена файлов
echo "Replacing files with fixes..." | tee -a "$LOG_FILE"

# config.py
cat << 'EOF' > config.py
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
API_URL = os.getenv("API_URL", "http://api:8000")

# --- Gemini API ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Админка ---
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# --- Redis ---
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# --- Окружение ---
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
EOF
dos2unix config.py >> "$LOG_FILE" 2>&1
echo "Created config.py" | tee -a "$LOG_FILE"

# bot.py
cat << 'EOF' > bot.py
import asyncio
import logging
import locale

from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio.client import Redis

from config import BOT_TOKEN, REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, DEBUG
from handlers import common, appointments, booking

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)

async def main():
    bot = Bot(token=BOT_TOKEN)
    
    redis_client = Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD if REDIS_PASSWORD else None
    )
    storage = RedisStorage(redis=redis_client)
    
    dp = Dispatcher(storage=storage)
    dp.include_router(booking.router)
    dp.include_router(appointments.router)
    dp.include_router(common.router)

    await bot.set_my_commands([
        types.BotCommand(command="start", description="Начало работы"),
        types.BotCommand(command="book", description="Записаться на услугу"),
        types.BotCommand(command="my_appointments", description="Мои записи"),
        types.BotCommand(command="cancel", description="Отменить действие"),
    ])

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
    except locale.Error:
        logging.warning("Локаль ru_RU.UTF-8 не найдена, месяцы могут отображаться на английском.")
    
    asyncio.run(main())
EOF
dos2unix bot.py >> "$LOG_FILE" 2>&1
echo "Created bot.py" | tee -a "$LOG_FILE"

# docker-compose.yml
cat << 'EOF' > docker-compose.yml
services:
  db:
    image: postgres:14-alpine
    container_name: salon_postgres_db
    volumes:
      - postgres_data:/var/lib/postgresql/data/
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ${DB_NAME}
    ports:
      - "5432:5432"
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - salon_network

  redis:
    image: redis:7-alpine
    container_name: salon_redis
    volumes:
      - redis_data:/data
    environment:
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    command: redis-server --requirepass ${REDIS_PASSWORD}
    restart: unless-stopped
    networks:
      - salon_network

  api:
    build: .
    container_name: salon_api_service
    command: >
      sh -c "if [ \"$ENVIRONMENT\" = \"prod\" ]; then
               uvicorn api.main:app --host 0.0.0.0 --port 8000;
             else
               uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload;
             fi"
    volumes:
      - .:/app
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
    environment:
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - DB_NAME=${DB_NAME}
      - ADMIN_USERNAME=${ADMIN_USERNAME}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD}
      - RUNNING_IN_DOCKER=1
      - ENVIRONMENT=${ENVIRONMENT}
      - DEBUG=${DEBUG}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - salon_network

  bot:
    build: .
    container_name: salon_telegram_bot
    command: python3 bot.py
    volumes:
      - .:/app
    depends_on:
      - api
      - redis
    environment:
      - BOT_TOKEN=${BOT_TOKEN}
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - API_URL=http://api:8000
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=${REDIS_PASSWORD}
      - ENVIRONMENT=${ENVIRONMENT}
      - DEBUG=${DEBUG}
    restart: unless-stopped
    networks:
      - salon_network

volumes:
  postgres_data:
  redis_data:

networks:
  salon_network:
    driver: bridge
EOF
dos2unix docker-compose.yml >> "$LOG_FILE" 2>&1
echo "Created docker-compose.yml" | tee -a "$LOG_FILE"

# requirements.txt
cat << 'EOF' > requirements.txt
aiofiles==24.1.0
aiogram==3.22.0
google-generativeai==0.5.2
aiohappyeyeballs==2.6.1
aiohttp==3.12.15
aiosignal==1.4.0
annotated-types==0.7.0
anyio==4.10.0
attrs==25.3.0
bcrypt==4.3.0
certifi==2025.8.3
click==8.2.1
fastapi==0.116.1
frozenlist==1.7.0
greenlet==3.2.4
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
idna==3.10
Jinja2==3.1.6
magic-filter==1.0.12
MarkupSafe==3.0.2
multidict==6.6.4
passlib==1.7.4
propcache==0.3.2
psycopg2-binary==2.9.10
pydantic==2.8.2
pydantic_core==2.20.1
python-dotenv==1.1.1
python-multipart==0.0.20
sniffio==1.3.1
SQLAlchemy==2.0.43
starlette==0.47.3
typing-inspection==0.4.1
typing_extensions==4.15.0
uvicorn==0.35.0
yarl==1.20.1
redis==5.0.1
pytest==8.3.3
pytest-asyncio==0.24.0
babel==2.15.0
EOF
dos2unix requirements.txt >> "$LOG_FILE" 2>&1
echo "Created requirements.txt" | tee -a "$LOG_FILE"

# api/main.py
mkdir -p api
cat << 'EOF' > api/main.py
import logging
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from datetime import date, datetime, time, timedelta
from contextlib import asynccontextmanager

import models
from database import SessionLocal, Base, get_engine
from api.routers import bot
from api.dependencies import authenticate_user, get_db
from config import ADMIN_USERNAME, ADMIN_PASSWORD, ENVIRONMENT, DEBUG

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Application startup...")
    engine = get_engine()
    SessionLocal.configure(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    with SessionLocal() as db:
        create_initial_data(db)
    yield
    logging.info("Application shutdown...")

app = FastAPI(title="Beauty Salon API", lifespan=lifespan)

def create_initial_data(db: Session):
    """Заполняет базу данных начальными данными, если она пуста."""
    if db.query(models.Service).count() == 0:
        logging.info("Creating initial services data...")
        db.add_all([
            models.Service(name="Маникюр с покрытием", price=2000, duration_minutes=90),
            models.Service(name="Женская стрижка", price=2500, duration_minutes=60),
            models.Service(name="Чистка лица", price=3500, duration_minutes=75),
            models.Service(name="Наращивание ресниц", price=3000, duration_minutes=120),
            models.Service(name="Оформление бровей", price=1500, duration_minutes=45),
            models.Service(name="Депиляция", price=3000, duration_minutes=60)
        ])
        db.commit()
    
    if db.query(models.Master).count() == 0:
        logging.info("Creating initial masters data...")
        s_manicure=db.query(models.Service).filter_by(name="Маникюр с покрытием").one()
        s_haircut=db.query(models.Service).filter_by(name="Женская стрижка").one()
        s_facial=db.query(models.Service).filter_by(name="Чистка лица").one()
        s_eyelash=db.query(models.Service).filter_by(name="Наращивание ресниц").one()
        s_eyebrow=db.query(models.Service).filter_by(name="Оформление бровей").one()
        s_depilation=db.query(models.Service).filter_by(name="Депиляция").one()

        m1=models.Master(name="Анна Смирнова", specialization="Мастер маникюра", description="Опыт 5 лет.")
        m2=models.Master(name="Елена Волкова", specialization="Парикмахер-стилист", description="Сложные окрашивания.")
        m3=models.Master(name="Ольга Морозова", specialization="Косметолог-эстетист", description="Медицинское образование.")
        m4=models.Master(name="Ирина Павлова", specialization="Лешмейкер и бровист", description="Чемпионка конкурсов.")
        
        db.add_all([m1, m2, m3, m4]); db.commit()
        
        m1.services.extend([s_manicure, s_eyebrow])
        m2.services.append(s_haircut)
        m3.services.extend([s_facial, s_depilation, s_eyebrow])
        m4.services.extend([s_eyelash, s_eyebrow])
        db.commit()
        
        schedules = [
            models.Schedule(master_id=m1.id,day_of_week=d,start_time=time(10,0),end_time=time(19,0)) for d in [1,3,5]
        ]
        schedules.extend([
            models.Schedule(master_id=m2.id,day_of_week=d,start_time=time(9,0),end_time=time(18,0)) for d in [2,4,6]
        ])
        schedules.extend([
            models.Schedule(master_id=m3.id,day_of_week=d,start_time=time(10,0),end_time=time(20,0)) for d in [3,5]
        ])
        schedules.extend([
            models.Schedule(master_id=m4.id,day_of_week=d,start_time=time(11,0),end_time=time(20,0)) for d in [1,3,5,7]
        ])
        
        db.add_all(schedules); db.commit()
        logging.info("Initial data created for testing.")

app.include_router(bot.router)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/")
def read_root():
    return {"message": "Beauty Salon API is running"}

@app.get("/admin/schedule", include_in_schema=False)
def admin_schedule_page(
    request: Request, 
    selected_date_str: Optional[str] = None, 
    db: Session = Depends(get_db), 
    username: str = Depends(authenticate_user)
):
    try:
        selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date() if selected_date_str else date.today()
    except ValueError:
        selected_date = date.today()
    
    prev_date = selected_date - timedelta(days=1)
    next_date = selected_date + timedelta(days=1)
    
    masters = db.query(models.Master).order_by(models.Master.name).all()
    
    start_of_day = datetime.combine(selected_date, time.min)
    end_of_day = datetime.combine(selected_date, time.max)
    
    appointments = db.query(models.Appointment).options(
        joinedload(models.Appointment.client), 
        joinedload(models.Appointment.service)
    ).filter(
        models.Appointment.start_time.between(start_of_day, end_of_day)
    ).order_by(models.Appointment.start_time).all()
    
    all_services = db.query(models.Service).order_by(models.Service.name).all()
    
    context = {
        "request": request,
        "selected_date": selected_date,
        "prev_date": prev_date,
        "next_date": next_date,
        "masters": masters,
        "appointments": appointments,
        "all_services": all_services,
        "all_masters": masters
    }
    return templates.TemplateResponse("schedule.html", context)
EOF
dos2unix api/main.py >> "$LOG_FILE" 2>&1
echo "Created api/main.py" | tee -a "$LOG_FILE"

# api/routers/bot.py
mkdir -p api/routers
cat << 'EOF' > api/routers/bot.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import date, datetime, time, timedelta
import calendar
import logging
from config import UTC

import models
from api import schemas
from api.dependencies import get_db

router = APIRouter(
    prefix="/api/v1",
    tags=["Bot API"],
)

@router.get("/services", response_model=List[schemas.ServiceSchema])
def get_services(db: Session = Depends(get_db)):
    return db.query(models.Service).join(models.Service.masters).distinct().all()

@router.get("/services/{service_id}", response_model=schemas.ServiceSchema)
def get_service(service_id: int, db: Session = Depends(get_db)):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service: raise HTTPException(404, "Service not found")
    return service

@router.get("/masters", response_model=List[schemas.MasterSchema])
def get_masters(db: Session = Depends(get_db)):
    return db.query(models.Master).all()

@router.get("/services/{service_id}/masters", response_model=List[schemas.MasterSchema])
def get_masters_for_service(service_id: int, db: Session = Depends(get_db)):
    service = db.query(models.Service).options(joinedload(models.Service.masters)).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service.masters

@router.get("/available-slots", response_model=List[schemas.AvailableSlotSchema])
def get_available_slots(service_id: int, selected_date: date, telegram_user_id: int, master_id: Optional[int]=None, db: Session=Depends(get_db)):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service: raise HTTPException(status_code=404, detail="Service not found")
    
    duration = timedelta(minutes=service.duration_minutes)
    
    client = db.query(models.Client).filter(models.Client.telegram_user_id == telegram_user_id).first()
    client_appointments = []
    if client:
        start_of_day = datetime.combine(selected_date, time.min, tzinfo=UTC)
        end_of_day = datetime.combine(selected_date, time.max, tzinfo=UTC)
        client_appointments = db.query(models.Appointment).filter(
            models.Appointment.client_id == client.id,
            models.Appointment.start_time.between(start_of_day, end_of_day)
        ).all()

    masters_query = db.query(models.Master).join(models.Service, models.Master.services).filter(models.Service.id == service_id)
    if master_id: masters_query = masters_query.filter(models.Master.id == master_id)
    potential_masters = masters_query.all()
    if not potential_masters:
        return []
    
    all_slots = []
    day_of_week = selected_date.isoweekday()
    now_utc = datetime.now(UTC)

    for master in potential_masters:
        schedule = db.query(models.Schedule).filter(models.Schedule.master_id == master.id, models.Schedule.day_of_week == day_of_week).first()
        if not schedule: continue
        
        master_appointments = db.query(models.Appointment).filter(
            models.Appointment.master_id == master.id,
            models.Appointment.start_time.between(datetime.combine(selected_date, time.min, tzinfo=UTC), datetime.combine(selected_date, time.max, tzinfo=UTC))
        ).all()
        
        slot_start = datetime.combine(selected_date, schedule.start_time, tzinfo=UTC)
        
        if selected_date == date.today():
            slot_start = max(slot_start, now_utc)
            if slot_start.minute % 15 != 0:
                minutes_to_add = 15 - (slot_start.minute % 15)
                slot_start += timedelta(minutes=minutes_to_add)
                slot_start = slot_start.replace(second=0, microsecond=0)

        workday_end = datetime.combine(selected_date, schedule.end_time, tzinfo=UTC)
        slot_step = timedelta(minutes=15)
        
        while slot_start + duration <= workday_end:
            slot_end = slot_start + duration
            is_master_free = True
            for appt in master_appointments:
                if max(slot_start, appt.start_time) < min(slot_end, appt.end_time):
                    is_master_free = False
                    break
            if is_master_free:
                all_slots.append({"time": slot_start.strftime("%H:%M"), "master_id": master.id})
            slot_start += slot_step
    
    final_slots = []
    for slot in all_slots:
        slot_start_dt = datetime.strptime(f"{selected_date} {slot['time']}", "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
        slot_end_dt = slot_start_dt + duration
        is_client_busy = False
        for client_appt in client_appointments:
            if max(slot_start_dt, client_appt.start_time) < min(slot_end_dt, client_appt.end_time):
                is_client_busy = True
                break
        if not is_client_busy:
            final_slots.append(slot)
            
    return sorted(final_slots, key=lambda x: x['time'])

@router.get("/active-days-in-month", response_model=List[int])
def get_active_days(service_id: int, year: int, month: int, telegram_user_id: int, master_id: Optional[int]=None, db: Session=Depends(get_db)):
    try:
        num_days = calendar.monthrange(year, month)[1]
    except calendar.IllegalMonthError:
        return []
    active_days = []
    for day in range(1, num_days + 1):
        current_date = date(year, month, day)
        if current_date < date.today():
            continue
        if get_available_slots(service_id=service_id, selected_date=current_date, telegram_user_id=telegram_user_id, master_id=master_id, db=db):
            active_days.append(day)
    return active_days

@router.get("/appointments/{appointment_id}", response_model=schemas.AppointmentInfoSchema)
def get_appointment(appointment_id: int, db: Session = Depends(get_db)):
    appt = db.query(models.Appointment).options(joinedload(models.Appointment.service), joinedload(models.Appointment.master)).filter(models.Appointment.id == appointment_id).first()
    if not appt: raise HTTPException(404, "Appointment not found")
    return appt

@router.get("/salon-info", response_model=schemas.SalonInfoSchema)
def get_salon_information(db: Session = Depends(get_db)):
    services = db.query(models.Service).all()
    masters_raw = db.query(models.Master).options(joinedload(models.Master.services)).all()
    
    masters_processed = [
        {
            "name": master.name,
            "specialization": master.specialization,
            "services": [s.name for s in master.services]
        } for master in masters_raw
    ]
    
    return {"services": services, "masters": masters_processed}

@router.post("/appointments/natural", response_model=schemas.AppointmentInfoSchema)
def create_appointment_from_natural_language(request: schemas.AppointmentNaturalLanguageSchema, db: Session = Depends(get_db)):
    logging.info(f"Received natural language appointment request: {request.model_dump()}")
    client = db.query(models.Client).filter(models.Client.telegram_user_id == request.telegram_user_id).first()
    if not client:
        client = models.Client(telegram_user_id=request.telegram_user_id, name=request.user_name)
        db.add(client); db.commit(); db.refresh(client)
    service = db.query(models.Service).filter(models.Service.name.ilike(f"%{request.service_name}%")).first()
    if not service: raise HTTPException(status_code=404, detail=f"Услуга '{request.service_name}' не найдена.")
    master = None
    if request.master_name:
        master = db.query(models.Master).filter(models.Master.name.ilike(f"%{request.master_name}%")).first()
        if not master: raise HTTPException(status_code=404, detail=f"Мастер '{request.master_name}' не найден.")
    else:
        master = db.query(models.Master).join(models.Master.services).filter(models.Service.id == service.id).first()
        if not master: raise HTTPException(status_code=404, detail=f"Для услуги '{service.name}' не найдено ни одного мастера.")
    try:
        start_time = datetime.strptime(f"{request.appointment_date} {request.appointment_time}", "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты или времени. Используйте YYYY-MM-DD и HH:MM.")
    end_time = start_time + timedelta(minutes=service.duration_minutes)
    master_conflicting = db.query(models.Appointment).filter(models.Appointment.master_id == master.id, models.Appointment.start_time < end_time, models.Appointment.end_time > start_time).count()
    if master_conflicting > 0: raise HTTPException(status_code=409, detail="Это время у выбранного мастера уже занято.")
    client_conflicting = db.query(models.Appointment).filter(models.Appointment.client_id == client.id, models.Appointment.start_time < end_time, models.Appointment.end_time > start_time).count()
    if client_conflicting > 0: raise HTTPException(status_code=409, detail="У Вас уже есть другая запись на это время.")
    new_appointment = models.Appointment(client_id=client.id, master_id=master.id, service_id=service.id, start_time=start_time, end_time=end_time)
    db.add(new_appointment); db.commit(); db.refresh(new_appointment)
    db.refresh(new_appointment, attribute_names=['service', 'master'])
    return {
        "id": new_appointment.id,
        "start_time": new_appointment.start_time.isoformat(),
        "service_name": new_appointment.service.name,
        "master_name": new_appointment.master.name
    }

@router.post("/appointments", response_model=schemas.AppointmentInfoSchema)
def create_appointment(appointment: schemas.AppointmentCreateSchema, db: Session = Depends(get_db)):
    logging.info(f"Received appointment request: {appointment.model_dump()}")
    client = db.query(models.Client).filter(models.Client.telegram_user_id == appointment.telegram_user_id).first()
    if not client:
        client = models.Client(telegram_user_id=appointment.telegram_user_id, name=appointment.user_name)
        db.add(client); db.commit(); db.refresh(client)
    service = db.query(models.Service).filter(models.Service.id == appointment.service_id).first()
    master = db.query(models.Master).filter(models.Master.id == appointment.master_id).first()
    if not service or not master: raise HTTPException(status_code=404, detail="Service or Master not found")
    start_time = appointment.start_time.replace(tzinfo=UTC)
    end_time = start_time + timedelta(minutes=service.duration_minutes)
    master_conflicting = db.query(models.Appointment).filter(models.Appointment.master_id == appointment.master_id, models.Appointment.start_time < end_time, models.Appointment.end_time > start_time).count()
    if master_conflicting > 0: raise HTTPException(status_code=409, detail="This time slot has just been booked. Please choose another time.")
    client_conflicting = db.query(models.Appointment).filter(models.Appointment.client_id == client.id, models.Appointment.start_time < end_time, models.Appointment.end_time > start_time).count()
    if client_conflicting > 0: raise HTTPException(status_code=409, detail="У Вас уже есть другая запись на это время.")
    new_appointment = models.Appointment(client_id=client.id, master_id=appointment.master_id, service_id=appointment.service_id, start_time=start_time, end_time=end_time)
    db.add(new_appointment); db.commit(); db.refresh(new_appointment)
    db.refresh(new_appointment, attribute_names=['service', 'master'])
    return {
        "id": new_appointment.id,
        "start_time": new_appointment.start_time.isoformat(),
        "service_name": new_appointment.service.name,
        "master_name": new_appointment.master.name
    }

@router.get("/clients/{telegram_user_id}/appointments", response_model=List[schemas.AppointmentInfoSchema])
def get_client_appointments(telegram_user_id: int, db: Session = Depends(get_db)):
    client = db.query(models.Client).filter(models.Client.telegram_user_id == telegram_user_id).first()
    if not client: return []
    now_utc = datetime.now(UTC)
    appointments = db.query(models.Appointment).options(
        joinedload(models.Appointment.service),
        joinedload(models.Appointment.master)
    ).filter(
        models.Appointment.client_id == client.id,
        models.Appointment.start_time >= now_utc
    ).order_by(models.Appointment.start_time).all()
    return [{
        "id": appt.id,
        "start_time": appt.start_time.isoformat(),
        "service_name": appt.service.name,
        "master_name": appt.master.name
    } for appt in appointments]

@router.delete("/appointments/{appointment_id}")
def delete_appointment(appointment_id: int, db: Session = Depends(get_db)):
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appointment: raise HTTPException(status_code=404, detail="Appointment not found")
    db.delete(appointment); db.commit()
    return {"message": "Appointment cancelled successfully"}

@router.patch("/clients/{telegram_user_id}")
def update_client_phone(telegram_user_id: int, client_data: schemas.ClientUpdateSchema, db: Session = Depends(get_db)):
    client = db.query(models.Client).filter(models.Client.telegram_user_id == telegram_user_id).first()
    if not client: raise HTTPException(status_code=404, detail="Client not found")
    client.phone_number = client_data.phone_number; db.commit()
    return {"message": "Phone number updated successfully"}
EOF
dos2unix api/routers/bot.py >> "$LOG_FILE" 2>&1
echo "Created api/routers/bot.py" | tee -a "$LOG_FILE"

# handlers/common.py
mkdir -p handlers
cat << 'EOF' > handlers/common.py
from aiogram import Router, types, F, Bot
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
import httpx
import logging
import json
from datetime import datetime
from babel.dates import format_datetime

from fsm import AppointmentStates
from services.api_client import api_client
from services.gemini import gemini_client

router = Router()

@router.callback_query(F.data.in_({"ignore", "ignore_inactive_day"}))
async def ignore_callback_handler(callback: types.CallbackQuery):
    await callback.answer("Ой, на этот день уже всё занято, выберите, пожалуйста, другой 😔", show_alert=True)

@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"Здравствуйте, {message.from_user.full_name}! ✨\n"
        "Я — ваш виртуальный администратор салона «Элеганс». Рада помочь вам!\n\n"
        "Чем могу быть полезна?\n"
        "/book - Записаться на процедуру 💅\n"
        "/my_appointments - Посмотреть ваши записи 🗓️\n"
        "/cancel - Отменить действие",
        reply_markup=types.ReplyKeyboardRemove()
    )

@router.message(Command("cancel"))
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    
    if current_state is None:
        await message.answer("Сейчас нет активного процесса, который можно было бы отменить. 😊")
        return

    if current_state == AppointmentStates.awaiting_contact:
        await state.clear()
        await message.answer(
            "Хорошо, понял(а) Вас. Ваша запись уже подтверждена. Если захотите ее отменить, воспользуйтесь командой /my_appointments. ✨",
            reply_markup=types.ReplyKeyboardRemove()
        )
    else:
        await state.clear()
        await message.answer(
            "Хорошо, я всё отменила. Давайте начнем заново, если хотите! /book",
            reply_markup=types.ReplyKeyboardRemove()
        )

@router.message(F.contact, StateFilter(AppointmentStates.awaiting_contact, None))
async def handle_contact(message: types.Message, state: FSMContext):
    try:
        await api_client.update_client_phone(message.from_user.id, message.contact.phone_number)
        await message.answer("Спасибо! Сохранила ваш номер телефона. Теперь мы сможем с вами связаться, если что-то изменится. 😊", reply_markup=types.ReplyKeyboardRemove())
    except (httpx.RequestError, httpx.HTTPStatusError):
        await message.answer("Простите, не удалось сохранить ваш номер телефона из-за технической ошибки. Попробуйте, пожалуйста, еще раз. 🙏")
    finally:
        await state.clear()

@router.message(F.text, StateFilter(AppointmentStates.awaiting_contact))
async def handle_contact_rejection(message: types.Message, state: FSMContext):
    text = message.text.lower()
    negative_responses = ['нет', 'не', 'не хочу', 'отказ', 'позже']
    question_responses = ['зачем', 'почему', 'для чего']

    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    if any(word in text for word in negative_responses):
        await message.answer(
            "Хорошо, без проблем! Ваша запись уже подтверждена. Если что-то изменится, Вы всегда можете написать нам здесь. До встречи в «Элеганс»! ✨",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await state.clear()
    
    elif any(word in text for word in question_responses):
        await message.answer(
            "Мы просим номер телефона, чтобы администратор мог оперативно связаться с Вами в случае непредвиденных изменений в расписании мастера (например, если мастер заболел). Это помогает избежать недоразумений и вовремя предложить Вам альтернативу. 😊",
            reply_markup=keyboard
        )

    else:
        await message.answer(
            "Я не совсем понял(а). Пожалуйста, либо поделитесь контактом с помощью кнопки ниже, либо просто напишите 'нет', если не хотите этого делать.",
            reply_markup=keyboard
        )

@router.message(F.text, StateFilter(AppointmentStates))
async def handle_text_while_in_state(message: types.Message, bot: Bot):
    await message.answer("Пожалуйста, используйте кнопки для выбора или введите /cancel для отмены.")

@router.message(StateFilter(None))
async def handle_unhandled_content(message: types.Message, state: FSMContext, bot: Bot):
    msg = None
    try:
        msg = await message.answer("Думаю...")
        gemini_response = await gemini_client.handle_natural_language(
            state=state,
            user_message=message.text,
            user_name=message.from_user.full_name,
            telegram_user_id=message.from_user.id
        )
        
        if gemini_response['type'] == 'text':
            await bot.edit_message_text(text=gemini_response['content'], chat_id=message.chat.id, message_id=msg.message_id)
        
        elif gemini_response['type'] == 'error':
            await bot.edit_message_text(text=gemini_response['content'], chat_id=message.chat.id, message_id=msg.message_id)
        
        elif gemini_response['type'] == 'tool_call' or gemini_response['type'] == 'multi_tool_call':
            await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
            
            tool_calls = gemini_response.get('calls', [gemini_response])
            success_messages = []

            for call in tool_calls:
                tool_name = call['name']
                tool_args = call['args']
                
                if tool_name == 'create_appointment':
                    payload = {"telegram_user_id": message.from_user.id, "user_name": message.from_user.full_name, **tool_args}
                    try:
                        api_response = await api_client.create_natural_appointment(payload)
                        dt_object = datetime.fromisoformat(api_response['start_time'])
                        formatted_datetime = format_datetime(dt_object, 'd MMMM в HH:mm', locale='ru_RU')
                        success_messages.append(
                            f"🎉 Отлично! Я успешно записал(а) Вас.\n\n"
                            f"**Услуга:** {api_response['service_name']}\n"
                            f"**Мастер:** {api_response['master_name']}\n"
                            f"**Когда:** {formatted_datetime}\n\n"
                            f"Будем ждать Вас в «Элеганс»!"
                        )
                        await state.clear()
                    except httpx.HTTPStatusError as e:
                        error_detail = "Неизвестная ошибка API."
                        try: error_detail = e.response.json().get("detail", error_detail)
                        except json.JSONDecodeError: error_detail = e.response.text
                        success_messages.append(f"😔 Не удалось создать запись. Причина: {error_detail}")
                    except Exception as e:
                        logging.error(f"Непредвиденная ошибка при вызове API: {e}")
                        success_messages.append("😔 Простите, произошла непредвиденная ошибка при создании записи.")
                
                elif tool_name == 'cancel_appointment':
                    try:
                        appointment_index = tool_args.get('appointment_index')
                        if not appointment_index or appointment_index < 1:
                            success_messages.append(f"⚠️ Не удалось определить номер записи для отмены.")
                            continue
                        data = await state.get_data()
                        cancellation_cache = data.get("cancellation_cache", [])
                        if len(cancellation_cache) < appointment_index:
                            success_messages.append(f"⚠️ Неверный номер записи: {appointment_index}.")
                            continue
                        appt = cancellation_cache[appointment_index - 1]
                        appointment_id = appt['id']
                        await api_client.delete_appointment(appointment_id)
                        dt_object = datetime.fromisoformat(appt['start_time'])
                        formatted_datetime = format_datetime(dt_object, 'd MMMM в HH:mm', locale='ru_RU')
                        success_messages.append(
                            f"Готово! Ваша запись на услугу:\n"
                            f"✨ **{appt['service_name']}** к мастеру **{appt['master_name']}**\n"
                            f"🗓️ на **{formatted_datetime}**\n"
                            f"успешно отменена."
                        )
                    except (httpx.RequestError, httpx.HTTPStatusError):
                        success_messages.append(f"❌ Не удалось отменить запись №{appointment_index} из-за технической ошибки.")
                    except IndexError:
                        success_messages.append(f"⚠️ Запись с номером {appointment_index} не найдена.")
            
            if success_messages:
                await message.answer("\n\n".join(success_messages), parse_mode="Markdown")
                await state.clear()

    except Exception as e:
        logging.error(f"Критическая ошибка в хендлере: {e}")
        if msg:
            await bot.edit_message_text(
                text="😔 Простите, в боте произошла критическая ошибка. Мы уже работаем над этим.",
                chat_id=message.chat.id,
                message_id=msg.message_id
            )
EOF
dos2unix handlers/common.py >> "$LOG_FILE" 2>&1
echo "Created handlers/common.py" | tee -a "$LOG_FILE"

# handlers/appointments.py
cat << 'EOF' > handlers/appointments.py
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime
import httpx
import uuid
import logging
from babel.dates import format_datetime

from services.api_client import api_client

router = Router()

@router.message(Command("my_appointments"))
async def show_my_appointments(message: types.Message, state: FSMContext):
    try:
        appointments = await api_client.get_client_appointments(message.from_user.id)
        if not appointments:
            await message.answer("У Вас пока нет предстоящих записей в нашем салоне «Элеганс». Может, запишемся? /book 😊")
            return
        
        await message.answer("Нашла Ваши предстоящие визиты в «Элеганс»:")
        cancellation_data = {}
        for idx, appt in enumerate(appointments, 1):
            dt_object = datetime.fromisoformat(appt['start_time'])
            formatted_datetime = format_datetime(dt_object, 'd MMMM yyyy в HH:mm', locale='ru_RU')
            response_text = (f"🗓️ *{idx}. {formatted_datetime}*\n" f"Услуга: {appt['service_name']}\n" f"Мастер: {appt['master_name']}")
            short_id = str(uuid.uuid4())[:8]
            cancellation_data[short_id] = {"appointment_id": appt['id'], "service_name": appt['service_name'], "master_name": appt['master_name'], "datetime": formatted_datetime}
            builder = InlineKeyboardBuilder().button(text="❌ Отменить запись", callback_data=f"cancel_appt:{short_id}")
            await message.answer(response_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        await state.update_data(cancellation_data=cancellation_data, cancellation_cache=appointments)
    except (httpx.RequestError, httpx.HTTPStatusError):
        await message.answer("Ой, произошла небольшая техническая заминка, и я не могу сейчас посмотреть Ваши записи. Попробуйте, пожалуйста, чуть позже! 🙏")

@router.callback_query(F.data.startswith("cancel_appt:"))
async def cancel_appointment_handler(callback: types.CallbackQuery, state: FSMContext):
    try:
        short_id = callback.data.split(":", 1)[1]
        data = await state.get_data()
        cancellation_data = data.get("cancellation_data", {})
        appt_info = cancellation_data.get(short_id)
        if not appt_info:
            await callback.message.edit_text("Готово! Ваша запись отменена. Будем ждать Вас в «Элеганс» в другой раз! 💖")
            await callback.answer(); return
        appointment_id = appt_info['appointment_id']
        await api_client.delete_appointment(appointment_id)
        confirmation_text = (f"Готово! Ваша запись на услугу:\n\n" f"✨ **{appt_info['service_name']}**\n" f"👩‍⚕️ к мастеру **{appt_info['master_name']}**\n" f"🗓️ на **{appt_info['datetime']}**\n\n" f"успешно отменена. Будем ждать Вас в «Элеганс» в другой раз! 💖")
        await callback.message.edit_text(confirmation_text, parse_mode="Markdown")
    except (httpx.RequestError, httpx.HTTPStatusError):
        await callback.message.edit_text("Что-то пошло не так, и не получилось отменить запись. Пожалуйста, попробуйте еще раз или свяжитесь с нами напрямую. 😥")
    except Exception as e:
        logging.error(f"Ошибка при обработке отмены: {e}")
        await callback.message.edit_text("Произошла ошибка при обработке отмены. Пожалуйста, попробуйте снова.")
    await callback.answer()
EOF
dos2unix handlers/appointments.py >> "$LOG_FILE" 2>&1
echo "Created handlers/appointments.py" | tee -a "$LOG_FILE"

# handlers/booking.py
cat << 'EOF' > handlers/booking.py
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import date, datetime, timezone
import httpx
import logging
import json
from config import UTC
from babel.dates import format_datetime

from fsm import AppointmentStates
from keyboards import create_calendar_keyboard
from services.api_client import api_client

router = Router()

@router.message(Command("book"))
async def start_booking(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(AppointmentStates.choosing_service)
    try:
        services = await api_client.get_services()
        builder = InlineKeyboardBuilder()
        for service in services:
            builder.button(text=f"{service['name']} ({service['price']} руб.)", callback_data=f"service_select:{service['id']}:{service['name']}:{service['price']}")
        builder.adjust(1)
        await message.answer(
            "Какую процедуру для вашей красоты выберем сегодня? ✨",
            reply_markup=builder.as_markup()
        )
    except (httpx.RequestError, httpx.HTTPStatusError):
        await message.answer("Ой, не могу сейчас загрузить список наших прекрасных услуг. Попробуйте, пожалуйста, через минутку! 😔")
        await state.clear()

@router.callback_query(AppointmentStates.choosing_service, F.data.startswith("service_select:"))
async def service_selected(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":", 3)
    service_id, service_name, service_price = int(parts[1]), parts[2], parts[3]
    await state.update_data(service_id=service_id, service_name=service_name, service_price=service_price)
    try:
        masters = await api_client.get_masters_for_service(service_id)
        if not masters:
            await callback.message.edit_text("К сожалению, на эту услугу сейчас нет свободных мастеров. Может, выберете другую? 💖")
            await state.clear()
            return
        builder = InlineKeyboardBuilder()
        if len(masters) > 1:
            builder.button(text="Любой свободный мастер", callback_data="master_select:any:Любой мастер")
        for master in masters:
            builder.button(text=master['name'], callback_data=f"master_select:{master['id']}:{master['name']}")
        builder.button(text="◀️ Назад к услугам", callback_data="back_to_service")
        builder.adjust(1)
        await callback.message.edit_text("Отличный выбор! ✨ Теперь давайте подберем для вас мастера:", reply_markup=builder.as_markup())
        await state.set_state(AppointmentStates.choosing_master)
    except (httpx.RequestError, httpx.HTTPStatusError):
        await callback.message.edit_text("Простите, не могу загрузить список наших замечательных мастеров. Пожалуйста, попробуйте еще раз. 🙏")
        await state.clear()
    finally:
        await callback.answer()

@router.callback_query(AppointmentStates.choosing_master, F.data.startswith("master_select:"))
async def master_selected_show_calendar(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":", 2)
    master_id_str, master_name = parts[1], parts[2]
    master_id = None if master_id_str == 'any' else int(master_id_str)
    await state.update_data(master_id=master_id, master_name=master_name)
    today = date.today()
    user_data = await state.get_data()
    try:
        active_days = await api_client.get_active_days(
            service_id=user_data['service_id'],
            year=today.year,
            month=today.month,
            telegram_user_id=callback.from_user.id,
            master_id=master_id
        )
        calendar_kb = create_calendar_keyboard(today.year, today.month, set(active_days))
        back_button = types.InlineKeyboardButton(text="◀️ Назад к мастерам", callback_data="back_to_master")
        calendar_kb.inline_keyboard.append([back_button])
        await callback.message.edit_text("Прекрасно! Теперь выберите удобную для вас дату в календаре: 🗓️", reply_markup=calendar_kb)
        await state.set_state(AppointmentStates.choosing_date)
    except (httpx.RequestError, httpx.HTTPStatusError):
        await callback.message.edit_text("Произошла ошибка при загрузке календаря. Попробуйте снова.")
    finally:
        await callback.answer()

@router.callback_query(AppointmentStates.choosing_date, F.data.startswith("cal_day:"))
async def process_date_selected(callback: types.CallbackQuery, state: FSMContext):
    _, year, month, day = callback.data.split(":")
    selected_date = date(int(year), int(month), int(day))
    await state.update_data(selected_date=selected_date.isoformat())
    user_data = await state.get_data()
    try:
        slots = await api_client.get_available_slots(
            service_id=user_data['service_id'],
            selected_date=selected_date.isoformat(),
            telegram_user_id=callback.from_user.id,
            master_id=user_data.get('master_id')
        )
        if not slots:
            await callback.answer("На эту дату, к сожалению, уже всё расписано. Посмотрите, пожалуйста, другой денёк. 😔", show_alert=True)
            return
        builder = InlineKeyboardBuilder()
        time_buttons = [types.InlineKeyboardButton(text=slot['time'], callback_data=f"time_select:{slot['time']}:{slot['master_id']}") for slot in slots]
        builder.add(*time_buttons)
        builder.row(types.InlineKeyboardButton(text="◀️ Назад к датам", callback_data="back_to_date"))
        builder.adjust(4)
        await callback.message.edit_text("Нашла свободные окошки на этот день! Выбирайте удобное время: 🕒", reply_markup=builder.as_markup())
        await state.set_state(AppointmentStates.choosing_time)
    except (httpx.RequestError, httpx.HTTPStatusError):
        await callback.message.edit_text("Ой, что-то пошло не так при поиске свободного времени. Давайте попробуем еще разок! 😥")
        await state.clear()
    finally:
        await callback.answer()

@router.callback_query(AppointmentStates.choosing_time, F.data.startswith("time_select:"))
async def time_selected(callback: types.CallbackQuery, state: FSMContext):
    try:
        parts = callback.data.split(':')
        selected_time, selected_master_id = f"{parts[1]}:{parts[2]}", int(parts[3])
        await state.update_data(selected_time=selected_time, final_master_id=selected_master_id)
        user_data = await state.get_data()
        master_name = user_data['master_name']
        if user_data.get('master_id') is None:
            all_masters_list = await api_client.get_all_masters()
            all_masters = {master['id']: master['name'] for master in all_masters_list}
            master_name = all_masters.get(selected_master_id, f"Мастер ID {selected_master_id}")

        selected_date_obj = date.fromisoformat(user_data['selected_date'])
        formatted_date = format_datetime(selected_date_obj, 'd MMMM yyyy', locale='ru_RU')

        confirmation_text = (
            f"Почти готово! Давайте всё проверим: 🥰\n\n"
            f"✨ **Услуга:** {user_data['service_name']} ({user_data['service_price']} руб.)\n"
            f"👩‍⚕️ **Мастер:** {master_name}\n"
            f"🗓️ **Дата:** {formatted_date}\n"
            f"🕒 **Время:** {selected_time}\n\n"
            "Всё верно?"
        )
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Да, подтвердить", callback_data="confirm_booking")
        builder.button(text="◀️ Назад к выбору времени", callback_data="back_to_time")
        builder.adjust(1)
        await callback.message.edit_text(confirmation_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        await state.set_state(AppointmentStates.confirmation)
    except Exception as e:
        logging.error(f"CRITICAL ERROR in [time_selected]: {e}", exc_info=True)
        await callback.answer("Ой, произошла какая-то внутренняя ошибка. Пожалуйста, начните сначала. /book 🙏", show_alert=True)
        await state.clear()
    finally:
        await callback.answer()

@router.callback_query(AppointmentStates.choosing_date, F.data.startswith("cal_nav:"))
async def process_calendar_nav Successful deployment completed at $(date)" | tee -a "$LOG_FILE"
echo "Check logs in $LOG_FILE for details." | tee -a "$LOG_FILE"
echo "Deployment successful! Check .env, then test with: docker-compose logs, curl http://localhost:8000, or Telegram bot (/book, /my_appointments)." | tee -a "$LOG_FILE"
```

### Инструкции по использованию

1. **Сохранение скрипта**:
   - Сохраните скрипт в `/var/www/beauty_salon/deploy_fixes.sh`:
     ```bash
     nano deploy_fixes.sh
     ```
     Вставьте содержимое из артефакта выше, сохраните (`Ctrl+O`, `Enter`, `Ctrl+X`).

2. **Исправление окончаний строк**:
   ```bash
   apt update && apt install -y dos2unix
   dos2unix deploy_fixes.sh
   ```

3. **Дать права на выполнение**:
   ```bash
   chmod +x deploy_fixes.sh
   ```

4. **Запуск скрипта**:
   ```bash
   ./deploy_fixes.sh
   ```

5. **Проверка `.env`**:
   - После выполнения скрипта, если `.env` создан, отредактируйте его:
     ```bash
     nano .env
     ```
     Замените заглушки (`YOUR_TELEGRAM_BOT_TOKEN`, `YOUR_GEMINI_API_KEY`, и т.д.) реальными значениями.
   - Если используете Redis без пароля:
     ```bash
     nano docker-compose.yml
     ```
     Удалите строку `command: redis-server --requirepass ${REDIS_PASSWORD}` в секции `redis`.

6. **Проверка результата**:
   - Проверьте созданные файлы:
     ```bash
     ls -la config.py bot.py docker-compose.yml requirements.txt api/ handlers/ tests/ services/
     ```
   - Проверьте бэкап:
     ```bash
     ls -la backup_*
     ```
   - Проверьте логи:
     ```bash
     cat deploy_fixes.log
     ```
   - Проверьте статус контейнеров:
     ```bash
     docker-compose ps
     ```
   - Проверьте API:
     ```bash
     curl http://localhost:8000
     ```
     Ожидаемый результат: `{"message": "Beauty Salon API is running"}`.

7. **Тестирование бота**:
   - В Telegram проверьте команды:
     - `/my_appointments`: список записей или сообщение об их отсутствии.
     - `/book`: процесс записи (услуга, мастер, дата, время).
     - После `/my_appointments` введите "отмени вторую запись" для проверки Gemini.
   - Если бот не работает, проверьте логи:
     ```bash
     docker-compose logs salon_telegram_bot
     ```

8. **Восстановление (если нужно)**:
   - Если что-то пошло не так, восстановите из бэкапа:
     ```bash
     cp -r backup_YYYYMMDD_HHMMSS/* .
     ```

### Дополнительные файлы

Скрипт предполагает наличие `database.py`, `models.py`, `fsm.py`, `keyboards.py`, `api/dependencies.py`, `api/schemas.py`, `services/api_client.py`, `templates/schedule.html`, и `pytest.ini` из вашего исходного дампа. Если их нет, создайте их вручную из дампа (я могу предоставить их содержимое, если нужно).

### Если проблемы сохраняются

Пожалуйста, предоставьте:
- Вывод `ls -la /var/www/beauty_salon`.
- Содержимое `deploy_fixes.log` (`cat deploy_fixes.log`).
- Логи Docker: `docker-compose logs | tail -n 50`.
- Статус контейнеров: `docker-compose ps`.

Это поможет точно диагностировать, почему `backup_*` не создался и какие ошибки возникли при выполнении скрипта.