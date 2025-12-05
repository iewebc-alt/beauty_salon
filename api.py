import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import logging
import secrets
import calendar
import time as time_module
from fastapi import Depends, FastAPI, HTTPException, status, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo # <--- ВАЖНО: Для работы с московским временем

import models
from database import SessionLocal, engine
from config import ADMIN_USERNAME, ADMIN_PASSWORD

# Создаем таблицы
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

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

# ==========================================
#              PYDANTIC СХЕМЫ
# ==========================================

from pydantic import BaseModel

# Услуги
class ServiceSchema(BaseModel):
    id: int; name: str; price: int; duration_minutes: int
    class Config: from_attributes = True

class ServiceUpdateSchema(BaseModel):
    name: str; price: int; duration_minutes: int

# Мастера
class MasterSchema(BaseModel):
    id: int; name: str; specialization: str; description: Optional[str] = None
    class Config: from_attributes = True

class MasterCreateSchema(BaseModel):
    name: str
    specialization: str
    description: Optional[str] = None
    service_ids: List[int] = []

class MasterUpdateSchema(BaseModel):
    name: str
    specialization: str
    description: Optional[str] = None
    service_ids: List[int] = []

# График работы
class ScheduleItem(BaseModel):
    day_of_week: int
    is_working: bool
    start_time: str
    end_time: str

class MasterScheduleUpdate(BaseModel):
    items: List[ScheduleItem]

# Клиенты
class ClientManualSchema(BaseModel):
    name: str
    phone_number: str
    telegram_user_id: Optional[int] = None

class ClientUpdateSchema(BaseModel):
    phone_number: str

# Записи (Appointments)
class AppointmentInfoSchema(BaseModel):
    id: int; start_time: datetime; service_name: str; master_name: str
    class Config: from_attributes = True

class AppointmentCreateSchema(BaseModel):
    telegram_user_id: int; user_name: str; service_id: int; master_id: int; start_time: datetime

# Новые схемы для админки (ручное создание записи)
class AppointmentAdminCreateSchema(BaseModel):
    client_id: int
    master_id: int
    service_id: int
    start_time: datetime

class AppointmentUpdateSchema(BaseModel):
    master_id: int
    service_id: int
    start_time: datetime

# Вспомогательные
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
        s1=models.Service(name="Маникюр с покрытием", price=2000, duration_minutes=90)
        s2=models.Service(name="Женская стрижка", price=2500, duration_minutes=60)
        s3=models.Service(name="Чистка лица", price=3500, duration_minutes=75)
        db.add_all([s1, s2, s3]); db.commit()
    
    if db.query(models.Master).count() == 0:
        s_manicure=db.query(models.Service).filter_by(name="Маникюр с покрытием").one()
        s_haircut=db.query(models.Service).filter_by(name="Женская стрижка").one()
        
        m1=models.Master(name="Анна Смирнова", specialization="Мастер маникюра", description="Опыт 5 лет.")
        m2=models.Master(name="Елена Волкова", specialization="Парикмахер-стилист", description="Сложные окрашивания.")
        db.add_all([m1, m2]); db.commit()
        
        m1.services.append(s_manicure)
        m2.services.append(s_haircut)
        db.commit()
        
        # График по умолчанию
        schedules=[]
        for d in [1,2,3,4,5]:
            schedules.append(models.Schedule(master_id=m1.id, day_of_week=d, start_time=time(10,0), end_time=time(19,0)))
            schedules.append(models.Schedule(master_id=m2.id, day_of_week=d, start_time=time(10,0), end_time=time(19,0)))
        db.add_all(schedules); db.commit()

with SessionLocal() as db: create_initial_data(db)

# ==========================================
#              АДМИН-ПАНЕЛЬ (HTML)
# ==========================================

@app.get("/admin/schedule")
def admin_schedule_page(request: Request, selected_date_str: Optional[str]=None, db: Session=Depends(get_db), username: str=Depends(authenticate_user)):
    try: 
        selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date() if selected_date_str else date.today()
    except ValueError: 
        selected_date = date.today()
    
    prev_date = selected_date - timedelta(days=1)
    next_date = selected_date + timedelta(days=1)
    
    masters = db.query(models.Master).order_by(models.Master.name).all()
    services = db.query(models.Service).all()
    clients = db.query(models.Client).order_by(models.Client.name).all()
    
    start_of_day = datetime.combine(selected_date, time.min)
    end_of_day = datetime.combine(selected_date, time.max)
    
    appointments = db.query(models.Appointment).options(
        joinedload(models.Appointment.client), 
        joinedload(models.Appointment.service)
    ).filter(
        models.Appointment.start_time.between(start_of_day, end_of_day)
    ).order_by(models.Appointment.start_time).all()
    
    context = {
        "request": request, 
        "selected_date": selected_date, 
        "prev_date": prev_date, 
        "next_date": next_date, 
        "masters": masters, 
        "appointments": appointments,
        "services": services,
        "clients": clients,
        "page": "schedule",
        "username": ADMIN_USERNAME,
        "password": ADMIN_PASSWORD
    }
    return templates.TemplateResponse("schedule.html", context)

@app.get("/admin/masters")
def admin_masters_page(request: Request, db: Session=Depends(get_db), username: str=Depends(authenticate_user)):
    masters = db.query(models.Master).options(joinedload(models.Master.services)).all()
    services = db.query(models.Service).all()
    
    return templates.TemplateResponse("masters.html", {
        "request": request, 
        "masters": masters, 
        "services": services,
        "page": "masters", 
        "username": ADMIN_USERNAME, 
        "password": ADMIN_PASSWORD
    })

@app.get("/admin/services")
def admin_services_page(request: Request, db: Session=Depends(get_db), username: str=Depends(authenticate_user)):
    services = db.query(models.Service).all()
    return templates.TemplateResponse("services.html", {
        "request": request, 
        "services": services, 
        "page": "services", 
        "username": ADMIN_USERNAME, 
        "password": ADMIN_PASSWORD
    })

@app.get("/admin/clients")
def admin_clients_page(request: Request, db: Session=Depends(get_db), username: str=Depends(authenticate_user)):
    clients = db.query(models.Client).order_by(models.Client.id.desc()).limit(100).all()
    return templates.TemplateResponse("clients.html", {
        "request": request, 
        "clients": clients, 
        "page": "clients", 
        "username": ADMIN_USERNAME, 
        "password": ADMIN_PASSWORD
    })

# ==========================================
#              API ЭНДПОИНТЫ (JSON)
# ==========================================

@app.get("/")
def read_root(): return {"message": "Beauty Salon API is running"}

# --- Services ---

@app.get("/api/v1/services", response_model=List[ServiceSchema])
def get_services(db: Session = Depends(get_db)):
    return db.query(models.Service).join(models.Service.masters).distinct().all()

@app.post("/api/v1/services")
def create_service(service: ServiceSchema, db: Session = Depends(get_db), username: str=Depends(authenticate_user)):
    new_service = models.Service(name=service.name, price=service.price, duration_minutes=service.duration_minutes)
    db.add(new_service); db.commit(); db.refresh(new_service)
    return new_service

@app.put("/api/v1/services/{service_id}")
def update_service(service_id: int, service_data: ServiceUpdateSchema, db: Session = Depends(get_db), username: str=Depends(authenticate_user)):
    service = db.query(models.Service).get(service_id)
    if not service: raise HTTPException(status_code=404, detail="Service not found")
    
    service.name = service_data.name
    service.price = service_data.price
    service.duration_minutes = service_data.duration_minutes
    db.commit()
    return service

# --- Masters ---

@app.get("/api/v1/masters", response_model=List[MasterSchema])
def get_masters(db: Session = Depends(get_db)):
    return db.query(models.Master).all()

@app.post("/api/v1/masters")
def create_master(master_data: MasterCreateSchema, db: Session = Depends(get_db), username: str=Depends(authenticate_user)):
    new_master = models.Master(
        name=master_data.name, 
        specialization=master_data.specialization, 
        description=master_data.description
    )
    if master_data.service_ids:
        services = db.query(models.Service).filter(models.Service.id.in_(master_data.service_ids)).all()
        new_master.services = services

    db.add(new_master); db.commit(); db.refresh(new_master)
    return new_master

@app.put("/api/v1/masters/{master_id}")
def update_master(master_id: int, master_data: MasterUpdateSchema, db: Session = Depends(get_db), username: str=Depends(authenticate_user)):
    master = db.query(models.Master).get(master_id)
    if not master: raise HTTPException(status_code=404, detail="Master not found")
    
    master.name = master_data.name
    master.specialization = master_data.specialization
    master.description = master_data.description
    
    if master_data.service_ids is not None:
        services = db.query(models.Service).filter(models.Service.id.in_(master_data.service_ids)).all()
        master.services = services
        
    db.commit()
    return master

@app.get("/api/v1/services/{service_id}/masters", response_model=List[MasterSchema])
def get_masters_for_service(service_id: int, db: Session = Depends(get_db)):
    service = db.query(models.Service).options(joinedload(models.Service.masters)).filter(models.Service.id == service_id).first()
    if not service: raise HTTPException(status_code=404, detail="Service not found")
    return service.masters

# --- Schedule ---

@app.get("/api/v1/masters/{master_id}/schedule")
def get_master_schedule(master_id: int, db: Session = Depends(get_db)):
    schedules = db.query(models.Schedule).filter(models.Schedule.master_id == master_id).all()
    result = []
    db_sched_map = {s.day_of_week: s for s in schedules}
    for day in range(1, 8):
        sched = db_sched_map.get(day)
        if sched:
            result.append({"day_of_week": day, "is_working": True, "start_time": sched.start_time.strftime("%H:%M"), "end_time": sched.end_time.strftime("%H:%M")})
        else:
            result.append({"day_of_week": day, "is_working": False, "start_time": "10:00", "end_time": "19:00"})
    return result

@app.post("/api/v1/masters/{master_id}/schedule")
def update_master_schedule(master_id: int, data: MasterScheduleUpdate, db: Session = Depends(get_db), username: str=Depends(authenticate_user)):
    db.query(models.Schedule).filter(models.Schedule.master_id == master_id).delete()
    new_schedules = []
    for item in data.items:
        if item.is_working:
            try:
                st = datetime.strptime(item.start_time, "%H:%M").time()
                et = datetime.strptime(item.end_time, "%H:%M").time()
                new_schedules.append(models.Schedule(master_id=master_id, day_of_week=item.day_of_week, start_time=st, end_time=et))
            except ValueError: continue
    if new_schedules: db.add_all(new_schedules)
    db.commit()
    return {"message": "Schedule updated"}

# --- Clients (Manual) ---

@app.post("/api/v1/clients_manual")
def create_client_manual(data: ClientManualSchema, db: Session = Depends(get_db), username: str=Depends(authenticate_user)):
    tg_id = data.telegram_user_id
    if tg_id is None: tg_id = -int(time_module.time() * 1000)
    if db.query(models.Client).filter(models.Client.telegram_user_id == tg_id).first():
         raise HTTPException(status_code=400, detail="Клиент с таким Telegram ID уже существует")
    new_client = models.Client(name=data.name, phone_number=data.phone_number, telegram_user_id=tg_id)
    db.add(new_client); db.commit(); db.refresh(new_client)
    return new_client

@app.put("/api/v1/clients_manual/{client_id}")
def update_client_manual(client_id: int, data: ClientManualSchema, db: Session = Depends(get_db), username: str=Depends(authenticate_user)):
    client = db.query(models.Client).get(client_id)
    if not client: raise HTTPException(status_code=404, detail="Client not found")
    client.name = data.name
    client.phone_number = data.phone_number
    if data.telegram_user_id is not None and data.telegram_user_id != client.telegram_user_id:
         if db.query(models.Client).filter(models.Client.telegram_user_id == data.telegram_user_id).first():
             raise HTTPException(status_code=400, detail="ID занят")
         client.telegram_user_id = data.telegram_user_id
    db.commit()
    return client


# --- SLOTS & LOGIC (WITH TIMEZONE FIX) ---

@app.get("/api/v1/available-slots", response_model=List[AvailableSlotSchema])
def get_available_slots(service_id: int, selected_date: date, master_id: Optional[int]=None, db: Session=Depends(get_db)):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service: return []
    duration = timedelta(minutes=service.duration_minutes)
    
    masters_query = db.query(models.Master).join(models.Service, models.Master.services).filter(models.Service.id == service_id)
    if master_id: masters_query = masters_query.filter(models.Master.id == master_id)
    potential_masters = masters_query.all()
    
    all_slots = []
    day_of_week = selected_date.isoweekday()
    
    # --- ВАЖНО: Московское время ---
    moscow_tz = ZoneInfo("Europe/Moscow")
    now_in_moscow = datetime.now(moscow_tz)
    
    for master in potential_masters:
        schedule = db.query(models.Schedule).filter(models.Schedule.master_id == master.id, models.Schedule.day_of_week == day_of_week).first()
        if not schedule: continue
        
        start_day = datetime.combine(selected_date, time.min)
        end_day = datetime.combine(selected_date, time.max)
        
        appointments = db.query(models.Appointment).filter(
            models.Appointment.master_id == master.id, 
            models.Appointment.start_time.between(start_day, end_day)
        ).all()
        
        slot_start = datetime.combine(selected_date, schedule.start_time)
        work_end = datetime.combine(selected_date, schedule.end_time)
        
        while slot_start + duration <= work_end:
            # Проверка на прошедшее время (только для текущего дня)
            if selected_date == now_in_moscow.date() and slot_start.time() <= now_in_moscow.time():
                 slot_start += timedelta(minutes=30)
                 continue
            
            slot_end = slot_start + duration
            is_free = True
            for appt in appointments:
                if max(slot_start, appt.start_time) < min(slot_end, appt.end_time):
                    is_free = False
                    break
            if is_free: all_slots.append({"time": slot_start.strftime("%H:%M"), "master_id": master.id})
            slot_start += timedelta(minutes=30)
            
    return sorted(all_slots, key=lambda x: x['time'])

@app.get("/api/v1/active-days-in-month", response_model=List[int])
def get_active_days(service_id: int, year: int, month: int, master_id: Optional[int]=None, db: Session=Depends(get_db)):
    try: num_days = calendar.monthrange(year, month)[1]
    except: return []
    active_days = []
    
    # --- ВАЖНО: Московское время ---
    moscow_tz = ZoneInfo("Europe/Moscow")
    today_moscow = datetime.now(moscow_tz).date()

    for day in range(1, num_days + 1):
        current_date = date(year, month, day)
        if current_date < today_moscow: continue
        
        if get_available_slots(service_id, current_date, master_id, db):
            active_days.append(day)
    return active_days

# --- APPOINTMENTS (BOT) ---
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
    
    conflicting = db.query(models.Appointment).filter(
        models.Appointment.master_id == master.id, 
        models.Appointment.start_time < end_time, 
        models.Appointment.end_time > start_time
    ).count()
    if conflicting > 0: raise HTTPException(status_code=409, detail="This time slot is booked.")
    
    new_appointment = models.Appointment(client_id=client.id, master_id=master.id, service_id=service.id, start_time=start_time, end_time=end_time)
    db.add(new_appointment); db.commit(); db.refresh(new_appointment)
    
    return {"message": "Success", "appointment_id": new_appointment.id, "start_time": new_appointment.start_time, "master_name": master.name, "service_name": service.name}

# --- APPOINTMENTS (NATURAL AI) ---
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
    if not master: raise HTTPException(404, "Подходящий мастер не найден.")

    try: start_time = datetime.strptime(f"{request.appointment_date} {request.appointment_time}", "%Y-%m-%d %H:%M")
    except: raise HTTPException(400, "Неверный формат даты/времени")
    
    end_time = start_time + timedelta(minutes=service.duration_minutes)
    
    count = db.query(models.Appointment).filter(models.Appointment.master_id == master.id, models.Appointment.start_time < end_time, models.Appointment.end_time > start_time).count()
    if count > 0: raise HTTPException(409, "Время занято")

    new_appt = models.Appointment(client_id=client.id, master_id=master.id, service_id=service.id, start_time=start_time, end_time=end_time)
    db.add(new_appt); db.commit(); db.refresh(new_appt)
    return {"message": "Success", "appointment_id": new_appt.id, "start_time": new_appt.start_time.isoformat(), "master_name": master.name, "service_name": service.name}

# --- APPOINTMENTS (ADMIN MANUAL) ---
@app.post("/api/v1/appointments/admin")
def create_appointment_admin(appt: AppointmentAdminCreateSchema, db: Session = Depends(get_db), username: str=Depends(authenticate_user)):
    service = db.query(models.Service).get(appt.service_id)
    if not service: raise HTTPException(404, "Услуга не найдена")
    end_time = appt.start_time + timedelta(minutes=service.duration_minutes)
    
    if db.query(models.Appointment).filter(models.Appointment.master_id == appt.master_id, models.Appointment.start_time < end_time, models.Appointment.end_time > appt.start_time).count() > 0:
        raise HTTPException(409, "Это время занято")

    new_appt = models.Appointment(client_id=appt.client_id, master_id=appt.master_id, service_id=appt.service_id, start_time=appt.start_time, end_time=end_time)
    db.add(new_appt); db.commit(); db.refresh(new_appt)
    return new_appt

@app.put("/api/v1/appointments/{appt_id}")
def update_appointment(appt_id: int, appt_data: AppointmentUpdateSchema, db: Session = Depends(get_db), username: str=Depends(authenticate_user)):
    appt = db.query(models.Appointment).get(appt_id)
    if not appt: raise HTTPException(404, "Запись не найдена")
    
    service = db.query(models.Service).get(appt_data.service_id)
    end_time = appt_data.start_time + timedelta(minutes=service.duration_minutes)
    
    if db.query(models.Appointment).filter(models.Appointment.id != appt_id, models.Appointment.master_id == appt_data.master_id, models.Appointment.start_time < end_time, models.Appointment.end_time > appt_data.start_time).count() > 0:
        raise HTTPException(409, "Это время занято")
        
    appt.master_id = appt_data.master_id; appt.service_id = appt_data.service_id; appt.start_time = appt_data.start_time; appt.end_time = end_time
    db.commit()
    return appt

# --- COMMON ---
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
