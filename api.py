import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import logging
import secrets
import calendar
from fastapi import Depends, FastAPI, HTTPException, status, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import date, datetime, time, timedelta

import models
from database import SessionLocal, engine
from config import ADMIN_USERNAME, ADMIN_PASSWORD

# Создаем таблицы в БД
models.Base.metadata.create_all(bind=engine)

# --- ВОТ ГЛАВНАЯ СТРОКА, КОТОРУЮ ИЩЕТ СЕРВЕР ---
app = FastAPI()
# -----------------------------------------------

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Безопасность ---
security = HTTPBasic()
def authenticate_user(credentials: HTTPBasicCredentials = Depends(security)):
    is_username_correct = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    is_password_correct = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (is_username_correct and is_password_correct):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# --- Pydantic схемы ---
from pydantic import BaseModel
class ServiceSchema(BaseModel):
    id: int; name: str; price: int; duration_minutes: int
    class Config: from_attributes = True
class MasterSchema(BaseModel):
    id: int; name: str; specialization: str; description: Optional[str] = None
    class Config: from_attributes = True
class AppointmentInfoSchema(BaseModel):
    id: int; start_time: datetime; service_name: str; master_name: str
    class Config: from_attributes = True
class AppointmentCreateSchema(BaseModel):
    telegram_user_id: int; user_name: str; service_id: int; master_id: int; start_time: datetime
class ClientUpdateSchema(BaseModel):
    phone_number: str
class AvailableSlotSchema(BaseModel):
    time: str; master_id: int
class AppointmentNaturalLanguageSchema(BaseModel):
    telegram_user_id: int
    user_name: str
    service_name: str
    appointment_date: str
    appointment_time: str
    master_name: Optional[str] = None

# --- Dependency БД ---
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- Создание начальных данных ---
def create_initial_data(db: Session):
    if db.query(models.Service).count() == 0:
        logging.info("Creating initial services data...")
        s1=models.Service(name="Маникюр с покрытием", price=2000, duration_minutes=90)
        s2=models.Service(name="Женская стрижка", price=2500, duration_minutes=60)
        s3=models.Service(name="Чистка лица", price=3500, duration_minutes=75)
        db.add_all([s1, s2, s3]); db.commit()
    if db.query(models.Master).count() == 0:
        logging.info("Creating initial masters data...")
        s_manicure=db.query(models.Service).filter_by(name="Маникюр с покрытием").one()
        s_haircut=db.query(models.Service).filter_by(name="Женская стрижка").one()
        m1=models.Master(name="Анна Смирнова", specialization="Мастер маникюра", description="Опыт 5 лет.")
        m2=models.Master(name="Елена Волкова", specialization="Парикмахер-стилист", description="Сложные окрашивания.")
        db.add_all([m1, m2]); db.commit()
        m1.services.append(s_manicure)
        m2.services.append(s_haircut)
        db.commit()
        schedules=[models.Schedule(master_id=m1.id,day_of_week=d,start_time=time(10,0),end_time=time(19,0)) for d in [1,2,3,4,5]]
        schedules.extend([models.Schedule(master_id=m2.id,day_of_week=d,start_time=time(10,0),end_time=time(19,0)) for d in [1,2,3,4,5]])
        db.add_all(schedules); db.commit()
        logging.info("Initial data created.")
with SessionLocal() as db: create_initial_data(db)

# ========= Эндпоинты =========
@app.get("/")
def read_root(): return {"message": "Beauty Salon API is running"}

@app.get("/api/v1/services", response_model=List[ServiceSchema])
def get_services(db: Session = Depends(get_db)):
    return db.query(models.Service).join(models.Service.masters).distinct().all()

@app.get("/api/v1/masters", response_model=List[MasterSchema])
def get_masters(db: Session = Depends(get_db)):
    return db.query(models.Master).all()

@app.get("/api/v1/services/{service_id}/masters", response_model=List[MasterSchema])
def get_masters_for_service(service_id: int, db: Session = Depends(get_db)):
    service = db.query(models.Service).options(joinedload(models.Service.masters)).filter(models.Service.id == service_id).first()
    if not service: raise HTTPException(status_code=404, detail="Service not found")
    return service.masters

@app.get("/api/v1/available-slots", response_model=List[AvailableSlotSchema])
def get_available_slots(service_id: int, selected_date: date, master_id: Optional[int]=None, db: Session=Depends(get_db)):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service: return []
    duration = timedelta(minutes=service.duration_minutes)
    masters_query = db.query(models.Master).join(models.Service, models.Master.services).filter(models.Service.id == service_id)
    if master_id: masters_query = masters_query.filter(models.Master.id == master_id)
    potential_masters = masters_query.all()
    all_slots = []
    for master in potential_masters:
        schedule = db.query(models.Schedule).filter(models.Schedule.master_id == master.id, models.Schedule.day_of_week == selected_date.isoweekday()).first()
        if not schedule: continue
        start_of_day = datetime.combine(selected_date, time.min)
        end_of_day = datetime.combine(selected_date, time.max)
        appointments = db.query(models.Appointment).filter(models.Appointment.master_id == master.id, models.Appointment.start_time.between(start_of_day, end_of_day)).all()
        slot_start = datetime.combine(selected_date, schedule.start_time)
        workday_end = datetime.combine(selected_date, schedule.end_time)
        while slot_start + duration <= workday_end:
            slot_end = slot_start + duration
            is_free = True
            for appt in appointments:
                if max(slot_start, appt.start_time) < min(slot_end, appt.end_time): is_free = False; break
            if is_free: all_slots.append({"time": slot_start.strftime("%H:%M"), "master_id": master.id})
            slot_start += timedelta(minutes=15)
    return sorted(all_slots, key=lambda x: x['time'])

@app.get("/api/v1/active-days-in-month", response_model=List[int])
def get_active_days(service_id: int, year: int, month: int, master_id: Optional[int]=None, db: Session=Depends(get_db)):
    try: num_days = calendar.monthrange(year, month)[1]
    except: return []
    active_days = []
    for day in range(1, num_days + 1):
        current_date = date(year, month, day)
        if current_date < date.today(): continue
        if get_available_slots(service_id=service_id, selected_date=current_date, master_id=master_id, db=db):
            active_days.append(day)
    return active_days

@app.post("/api/v1/appointments")
def create_appointment(appointment: AppointmentCreateSchema, db: Session = Depends(get_db)):
    client = db.query(models.Client).filter(models.Client.telegram_user_id == appointment.telegram_user_id).first()
    if not client:
        client = models.Client(telegram_user_id=appointment.telegram_user_id, name=appointment.user_name)
        db.add(client); db.commit(); db.refresh(client)
    
    service = db.query(models.Service).get(appointment.service_id)
    master = db.query(models.Master).get(appointment.master_id)
    
    start_time = appointment.start_time
    end_time = start_time + timedelta(minutes=service.duration_minutes)
    
    new_appointment = models.Appointment(client_id=client.id, master_id=appointment.master_id, service_id=appointment.service_id, start_time=start_time, end_time=end_time)
    db.add(new_appointment); db.commit(); db.refresh(new_appointment)
    return {"message": "Success", "appointment_id": new_appointment.id, "start_time": new_appointment.start_time, "master_name": master.name, "service_name": service.name}

# --- Умный эндпоинт для AI ---
@app.post("/api/v1/appointments/natural")
def create_appointment_from_natural_language(request: AppointmentNaturalLanguageSchema, db: Session = Depends(get_db)):
    logging.info(f"AI Request: {request.dict()}")
    client = db.query(models.Client).filter(models.Client.telegram_user_id == request.telegram_user_id).first()
    if not client:
        client = models.Client(telegram_user_id=request.telegram_user_id, name=request.user_name)
        db.add(client); db.commit(); db.refresh(client)

    service = db.query(models.Service).filter(models.Service.name.ilike(f"%{request.service_name}%")).first()
    if not service: raise HTTPException(404, f"Услуга '{request.service_name}' не найдена.")

    master = None
    if request.master_name:
        master = db.query(models.Master).filter(models.Master.name.ilike(f"%{request.master_name}%")).first()
    if not master:
        master = db.query(models.Master).join(models.Master.services).filter(models.Service.id == service.id).first()
    if not master: raise HTTPException(404, "Мастер не найден.")

    try: start_time = datetime.strptime(f"{request.appointment_date} {request.appointment_time}", "%Y-%m-%d %H:%M")
    except: raise HTTPException(400, "Неверный формат даты/времени")
    
    end_time = start_time + timedelta(minutes=service.duration_minutes)
    
    # Проверка конфликтов (упрощенная)
    count = db.query(models.Appointment).filter(models.Appointment.master_id == master.id, models.Appointment.start_time < end_time, models.Appointment.end_time > start_time).count()
    if count > 0: raise HTTPException(409, "Время занято")

    new_appt = models.Appointment(client_id=client.id, master_id=master.id, service_id=service.id, start_time=start_time, end_time=end_time)
    db.add(new_appt); db.commit(); db.refresh(new_appt)
    return {"message": "Success", "appointment_id": new_appt.id, "start_time": new_appt.start_time.isoformat(), "master_name": master.name, "service_name": service.name}

@app.get("/api/v1/clients/{tid}/appointments", response_model=List[AppointmentInfoSchema])
def get_client_appts(tid: int, db: Session = Depends(get_db)):
    client = db.query(models.Client).filter(models.Client.telegram_user_id == tid).first()
    if not client: return []
    appts = db.query(models.Appointment).filter(models.Appointment.client_id == client.id, models.Appointment.start_time >= datetime.utcnow()).all()
    return [{"id": a.id, "start_time": a.start_time, "service_name": a.service.name, "master_name": a.master.name} for a in appts]

@app.delete("/api/v1/appointments/{aid}")
def delete_appt(aid: int, db: Session = Depends(get_db)):
    a = db.query(models.Appointment).get(aid)
    if a: db.delete(a); db.commit()
    return {"message": "Deleted"}

@app.patch("/api/v1/clients/{tid}")
def update_phone(tid: int, data: ClientUpdateSchema, db: Session = Depends(get_db)):
    c = db.query(models.Client).filter(models.Client.telegram_user_id == tid).first()
    if c: c.phone_number = data.phone_number; db.commit()
    return {"message": "Updated"}