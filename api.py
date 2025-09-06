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
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, datetime, time, timedelta

import models
from database import SessionLocal, engine
from config import ADMIN_USERNAME, ADMIN_PASSWORD

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Настройка безопасности ---
security = HTTPBasic()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, stored_password):
    return secrets.compare_digest(plain_password, stored_password)

def authenticate_user(credentials: HTTPBasicCredentials = Depends(security)):
    is_username_correct = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    is_password_correct = verify_password(credentials.password, ADMIN_PASSWORD)
    if not (is_username_correct and is_password_correct):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# --- Pydantic модели (схемы) ---
from pydantic import BaseModel

class ServiceSchema(BaseModel):
    id: int; name: str; price: int; duration_minutes: int
    class Config: orm_mode = True

class MasterSchema(BaseModel):
    id: int; name: str; specialization: str; description: Optional[str] = None
    class Config: orm_mode = True

class AppointmentInfoSchema(BaseModel):
    id: int; start_time: datetime; service_name: str; master_name: str
    class Config: orm_mode = True

class AppointmentCreateSchema(BaseModel):
    telegram_user_id: int; user_name: str; service_id: int; master_id: int; start_time: datetime

class ClientUpdateSchema(BaseModel):
    phone_number: str

class AvailableSlotSchema(BaseModel):
    time: str
    master_id: int

# --- Dependency для получения сессии БД ---
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- Функция для создания начальных данных ---
def create_initial_data(db: Session):
    if db.query(models.Service).count() == 0:
        logging.info("Creating initial services data...")
        service1 = models.Service(name="Маникюр с покрытием", price=2000, duration_minutes=90)
        service2 = models.Service(name="Женская стрижка", price=2500, duration_minutes=60)
        service3 = models.Service(name="Чистка лица", price=3500, duration_minutes=75)
        service4 = models.Service(name="Наращивание ресниц", price=3000, duration_minutes=120)
        service5 = models.Service(name="Оформление бровей", price=1500, duration_minutes=45)
        service6 = models.Service(name="Депиляция", price=3000, duration_minutes=60)
        db.add_all([service1, service2, service3, service4, service5, service6]); db.commit()
        logging.info("Services created.")
    if db.query(models.Master).count() == 0:
        logging.info("Creating initial masters data...")
        s_manicure = db.query(models.Service).filter_by(name="Маникюр с покрытием").one()
        s_haircut = db.query(models.Service).filter_by(name="Женская стрижка").one()
        s_facial = db.query(models.Service).filter_by(name="Чистка лица").one()
        s_eyelash = db.query(models.Service).filter_by(name="Наращивание ресниц").one()
        s_eyebrow = db.query(models.Service).filter_by(name="Оформление бровей").one()
        master1 = models.Master(name="Анна Смирнова", specialization="Мастер маникюра и педикюра", description="Опыт работы более 5 лет.")
        master2 = models.Master(name="Елена Волкова", specialization="Парикмахер-стилист", description="Специализируюсь на сложных окрашиваниях.")
        db.add_all([master1, master2]); db.commit()
        master1.services.extend([s_manicure, s_facial, s_eyelash, s_eyebrow])
        master2.services.append(s_haircut)
        db.commit()
        schedules = [
            models.Schedule(master_id=master1.id, day_of_week=1, start_time=time(10, 0), end_time=time(19, 0)),
            models.Schedule(master_id=master1.id, day_of_week=3, start_time=time(10, 0), end_time=time(19, 0)),
            models.Schedule(master_id=master1.id, day_of_week=5, start_time=time(10, 0), end_time=time(19, 0)),
            models.Schedule(master_id=master2.id, day_of_week=2, start_time=time(9, 0), end_time=time(18, 0)),
            models.Schedule(master_id=master2.id, day_of_week=4, start_time=time(9, 0), end_time=time(18, 0)),
            models.Schedule(master_id=master2.id, day_of_week=6, start_time=time(9, 0), end_time=time(18, 0)),
        ]
        db.add_all(schedules); db.commit()
        logging.info("Masters, services relations and schedules created.")

with SessionLocal() as db:
    create_initial_data(db)

# ========= Секция Веб-админки (ЗАЩИЩЕННАЯ) =========
@app.get("/admin/schedule")
def admin_schedule_page(request: Request, selected_date_str: Optional[str] = None, db: Session = Depends(get_db), username: str = Depends(authenticate_user)):
    if selected_date_str:
        try: selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
        except ValueError: selected_date = date.today()
    else: selected_date = date.today()
    prev_date, next_date = selected_date - timedelta(days=1), selected_date + timedelta(days=1)
    masters_on_schedule = db.query(models.Master).order_by(models.Master.name).all()
    start_of_day, end_of_day = datetime.combine(selected_date, time.min), datetime.combine(selected_date, time.max)
    appointments = db.query(models.Appointment).order_by(models.Appointment.start_time).filter(models.Appointment.start_time.between(start_of_day, end_of_day)).all()
    all_services = db.query(models.Service).order_by(models.Service.name).all()
    all_masters = db.query(models.Master).order_by(models.Master.name).all()
    context = {"request": request, "selected_date": selected_date, "prev_date": prev_date, "next_date": next_date, "masters": masters_on_schedule, "appointments": appointments, "all_services": all_services, "all_masters": all_masters}
    return templates.TemplateResponse("schedule.html", context)

# ========= Секция API для бота (ОТКРЫТАЯ) =========
@app.get("/")
def read_root(): return {"message": "Beauty Salon API is running"}
@app.get("/api/v1/services", response_model=List[ServiceSchema])
def get_services(db: Session = Depends(get_db)): return db.query(models.Service).all()
@app.get("/api/v1/masters", response_model=List[MasterSchema])
def get_masters(db: Session = Depends(get_db)): return db.query(models.Master).all()

@app.get("/api/v1/available-slots", response_model=List[AvailableSlotSchema])
def get_available_slots(service_id: int, selected_date: date, master_id: Optional[int] = None, db: Session = Depends(get_db)):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service: raise HTTPException(status_code=404, detail="Service not found")
    duration = timedelta(minutes=service.duration_minutes)
    masters_query = db.query(models.Master).join(models.Service, models.Master.services).filter(models.Service.id == service_id)
    if master_id: masters_query = masters_query.filter(models.Master.id == master_id)
    potential_masters = masters_query.all()
    if not potential_masters:
        if master_id: raise HTTPException(status_code=404, detail=f"Master with id {master_id} not found or doesn't provide service with id {service_id}")
        return []
    all_available_slots = []
    day_of_week = selected_date.isoweekday()
    for master in potential_masters:
        schedule = db.query(models.Schedule).filter(models.Schedule.master_id == master.id, models.Schedule.day_of_week == day_of_week).first()
        if not schedule: continue
        start_of_day, end_of_day = datetime.combine(selected_date, time.min), datetime.combine(selected_date, time.max)
        appointments = db.query(models.Appointment).filter(models.Appointment.master_id == master.id, models.Appointment.start_time.between(start_of_day, end_of_day)).all()
        slot_start = datetime.combine(selected_date, schedule.start_time)
        workday_end = datetime.combine(selected_date, schedule.end_time)
        slot_step = timedelta(minutes=15)
        while slot_start + duration <= workday_end:
            slot_end = slot_start + duration
            is_free = True
            for appt in appointments:
                if max(slot_start, appt.start_time) < min(slot_end, appt.end_time): is_free = False; break
            if is_free: all_available_slots.append({"time": slot_start.strftime("%H:%M"), "master_id": master.id})
            slot_start += slot_step
    return sorted(all_available_slots, key=lambda x: x['time'])

# --- ИСПРАВЛЕННЫЙ ПОРЯДОК: Эта функция теперь ВЫШЕ get_active_days ---
@app.get("/api/v1/active-days-in-month", response_model=List[int])
def get_active_days(service_id: int, year: int, month: int, master_id: Optional[int] = None, db: Session = Depends(get_db)):
    try:
        num_days_in_month = calendar.monthrange(year, month)[1]
    except calendar.IllegalMonthError:
        return []
    active_days_list = []
    for day in range(1, num_days_in_month + 1):
        current_date = date(year, month, day)
        if current_date < date.today():
            continue
        slots = get_available_slots(service_id=service_id, selected_date=current_date, master_id=master_id, db=db)
        if slots:
            active_days_list.append(day)
    return active_days_list

@app.post("/api/v1/appointments")
def create_appointment(appointment: AppointmentCreateSchema, db: Session = Depends(get_db)):
    # ... (код без изменений)
    logging.info(f"Received appointment request: {appointment.dict()}")
    client = db.query(models.Client).filter(models.Client.telegram_user_id == appointment.telegram_user_id).first()
    if not client:
        client = models.Client(telegram_user_id=appointment.telegram_user_id, name=appointment.user_name)
        db.add(client); db.commit(); db.refresh(client)
    service = db.query(models.Service).filter(models.Service.id == appointment.service_id).first()
    master = db.query(models.Master).filter(models.Master.id == appointment.master_id).first()
    if not service or not master: raise HTTPException(status_code=404, detail="Service or Master not found")
    start_time = appointment.start_time
    end_time = start_time + timedelta(minutes=service.duration_minutes)
    conflicting_appointments = db.query(models.Appointment).filter(models.Appointment.master_id == appointment.master_id, models.Appointment.start_time < end_time, models.Appointment.end_time > start_time).count()
    if conflicting_appointments > 0: raise HTTPException(status_code=409, detail="This time slot has just been booked. Please choose another time.")
    new_appointment = models.Appointment(client_id=client.id, master_id=appointment.master_id, service_id=appointment.service_id, start_time=start_time, end_time=end_time)
    db.add(new_appointment); db.commit(); db.refresh(new_appointment)
    return {"message": "Appointment created successfully", "appointment_id": new_appointment.id, "start_time": new_appointment.start_time, "master_name": master.name, "service_name": service.name}

@app.get("/api/v1/clients/{telegram_user_id}/appointments", response_model=List[AppointmentInfoSchema])
def get_client_appointments(telegram_user_id: int, db: Session = Depends(get_db)):
    # ... (код без изменений)
    client = db.query(models.Client).filter(models.Client.telegram_user_id == telegram_user_id).first()
    if not client: return []
    now = datetime.utcnow()
    appointments = db.query(models.Appointment).filter(models.Appointment.client_id == client.id, models.Appointment.start_time >= now).order_by(models.Appointment.start_time).all()
    result = []
    for appt in appointments:
        result.append({"id": appt.id, "start_time": appt.start_time, "service_name": appt.service.name, "master_name": appt.master.name})
    return result

@app.delete("/api/v1/appointments/{appointment_id}")
def delete_appointment(appointment_id: int, db: Session = Depends(get_db)):
    # ... (код без изменений)
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appointment: raise HTTPException(status_code=404, detail="Appointment not found")
    db.delete(appointment); db.commit()
    return {"message": "Appointment cancelled successfully"}

@app.patch("/api/v1/clients/{telegram_user_id}")
def update_client_phone(telegram_user_id: int, client_data: ClientUpdateSchema, db: Session = Depends(get_db)):
    # ... (код без изменений)
    client = db.query(models.Client).filter(models.Client.telegram_user_id == telegram_user_id).first()
    if not client: raise HTTPException(status_code=404, detail="Client not found")
    client.phone_number = client_data.phone_number; db.commit()
    return {"message": "Phone number updated successfully"}
