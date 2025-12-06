import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import logging
import secrets
import calendar
import time as time_module
from fastapi import Depends, FastAPI, HTTPException, status, Request, Header
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import models
from database import SessionLocal, engine
from config import ADMIN_USERNAME, ADMIN_PASSWORD, SUPER_ADMIN_USERNAME, SUPER_ADMIN_PASSWORD

# Создаем таблицы
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Dependency БД ---
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# ==========================================
#              АВТОРИЗАЦИЯ
# ==========================================
security = HTTPBasic()

def authenticate_super_admin(credentials: HTTPBasicCredentials = Depends(security)):
    is_username = secrets.compare_digest(credentials.username, SUPER_ADMIN_USERNAME)
    is_password = secrets.compare_digest(credentials.password, SUPER_ADMIN_PASSWORD)
    if not (is_username and is_password):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    return credentials.username

def authenticate_salon_admin(credentials: HTTPBasicCredentials = Depends(security), db: Session = Depends(get_db)):
    if credentials.username == SUPER_ADMIN_USERNAME and credentials.password == SUPER_ADMIN_PASSWORD:
        pass 
    salon = db.query(models.Salon).filter(models.Salon.name == credentials.username).first()
    if not salon or salon.admin_password != credentials.password:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    if not salon.is_active:
        raise HTTPException(status_code=403, detail="Ваш салон отключен")
    return salon

def get_current_salon(x_salon_token: str = Header(None), db: Session = Depends(get_db)):
    if not x_salon_token:
        raise HTTPException(status_code=403, detail="Missing Token")
    salon = db.query(models.Salon).filter(models.Salon.telegram_token == x_salon_token).first()
    if not salon:
        raise HTTPException(status_code=403, detail="Invalid Token")
    if not salon.is_active:
        raise HTTPException(status_code=403, detail="Salon is inactive")
    return salon

# ==========================================
#              PYDANTIC СХЕМЫ
# ==========================================
from pydantic import BaseModel

class ServiceSchema(BaseModel):
    id: int; name: str; price: int; duration_minutes: int
    class Config: from_attributes = True

class ServiceUpdateSchema(BaseModel):
    name: str; price: int; duration_minutes: int

class MasterSchema(BaseModel):
    id: int; name: str; specialization: str; description: Optional[str] = None
    class Config: from_attributes = True

class MasterCreateSchema(BaseModel):
    name: str; specialization: str; description: Optional[str] = None; service_ids: List[int] = []

class MasterUpdateSchema(BaseModel):
    name: str; specialization: str; description: Optional[str] = None; service_ids: List[int] = []

class ScheduleItem(BaseModel):
    day_of_week: int; is_working: bool; start_time: str; end_time: str

class MasterScheduleUpdate(BaseModel):
    items: List[ScheduleItem]

class ClientManualSchema(BaseModel):
    name: str; phone_number: str; telegram_user_id: Optional[int] = None
    class Config: from_attributes = True

class ClientUpdateSchema(BaseModel):
    phone_number: str

class AppointmentCreateSchema(BaseModel):
    telegram_user_id: int; user_name: str; service_id: int; master_id: int; start_time: datetime

class AppointmentAdminCreateSchema(BaseModel):
    client_id: int; master_id: int; service_id: int; start_time: datetime

class AppointmentUpdateSchema(BaseModel):
    master_id: int; service_id: int; start_time: datetime

class AppointmentNaturalLanguageSchema(BaseModel):
    telegram_user_id: int; user_name: str; service_name: str; appointment_date: str; appointment_time: str; master_name: Optional[str] = None

class AvailableSlotSchema(BaseModel):
    time: str; master_id: int

class AppointmentInfoSchema(BaseModel):
    id: int; start_time: datetime; service_name: str; master_name: str
    class Config: from_attributes = True

class SalonUpdateSchema(BaseModel):
    name: str; telegram_token: str; admin_password: str; is_active: bool

class ServiceCreateSchema(BaseModel):
    name: str
    price: int
    duration_minutes: int

# ==========================================
#           СУПЕР-АДМИНКА
# ==========================================

@app.get("/superadmin")
def super_admin_page(request: Request, db: Session=Depends(get_db), username: str=Depends(authenticate_super_admin)):
    salons = db.query(models.Salon).order_by(models.Salon.id).all()
    base_url = str(request.base_url).rstrip('/')
    return templates.TemplateResponse("super_admin.html", {"request": request, "salons": salons, "base_url": base_url})

@app.post("/superadmin/salons")
async def create_salon(request: Request, db: Session=Depends(get_db), username: str=Depends(authenticate_super_admin)):
    form = await request.form()
    name = form.get("name")
    title = form.get("title")
    token = form.get("token")
    password = form.get("password")
    
    if db.query(models.Salon).filter(models.Salon.telegram_token == token).first():
        raise HTTPException(400, "Token already exists")
        
    new_salon = models.Salon(name=name, title=title, telegram_token=token, admin_password=password)
    db.add(new_salon); db.commit(); db.refresh(new_salon)

    # Демо данные
    s1 = models.Service(salon_id=new_salon.id, name="Стрижка (Тест)", price=1000, duration_minutes=60)
    db.add(s1); db.commit()
    m1 = models.Master(salon_id=new_salon.id, name="Мастер (Тест)", specialization="Универсал")
    m1.services.append(s1)
    db.add(m1); db.commit()
    for d in range(1, 6):
        db.add(models.Schedule(master_id=m1.id, day_of_week=d, start_time=time(10,0), end_time=time(19,0)))
    db.commit()

    return {"status": "ok"}

@app.put("/superadmin/salons/{salon_id}")
def update_salon(salon_id: int, data: SalonUpdateSchema, db: Session=Depends(get_db), username: str=Depends(authenticate_super_admin)):
    salon = db.query(models.Salon).get(salon_id)
    if not salon: raise HTTPException(404, "Salon not found")
    salon.name = data.name; salon.telegram_token = data.telegram_token
    salon.admin_password = data.admin_password; salon.is_active = data.is_active
    db.commit()
    return {"status": "updated"}

# ==========================================
#           АДМИНКА САЛОНА
# ==========================================

@app.get("/admin/schedule")
def admin_schedule_page(request: Request, selected_date_str: Optional[str]=None, db: Session=Depends(get_db), salon: models.Salon = Depends(authenticate_salon_admin)):
    try: selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date() if selected_date_str else date.today()
    except: selected_date = date.today()
    
    masters = db.query(models.Master).filter(models.Master.salon_id == salon.id).all()
    services = db.query(models.Service).filter(models.Service.salon_id == salon.id).all()
    clients = db.query(models.Client).filter(models.Client.salon_id == salon.id).order_by(models.Client.name).all()
    
    start_of_day = datetime.combine(selected_date, time.min)
    end_of_day = datetime.combine(selected_date, time.max)
    
    appointments = db.query(models.Appointment).filter(
        models.Appointment.salon_id == salon.id,
        models.Appointment.start_time.between(start_of_day, end_of_day)
    ).options(joinedload(models.Appointment.client), joinedload(models.Appointment.service)).all()
    
    context = {
        "request": request, "selected_date": selected_date, 
        "prev_date": selected_date - timedelta(days=1), "next_date": selected_date + timedelta(days=1),
        "masters": masters, "appointments": appointments, "services": services, "clients": clients,
        "page": "schedule", "username": salon.name, "password": salon.admin_password
    }
    return templates.TemplateResponse("schedule.html", context)

@app.get("/admin/masters")
def admin_masters_page(request: Request, db: Session=Depends(get_db), salon: models.Salon = Depends(authenticate_salon_admin)):
    masters = db.query(models.Master).filter(models.Master.salon_id == salon.id).options(joinedload(models.Master.services)).all()
    services = db.query(models.Service).filter(models.Service.salon_id == salon.id).all()
    return templates.TemplateResponse("masters.html", {"request": request, "masters": masters, "services": services, "page": "masters", "username": salon.name, "password": salon.admin_password})

@app.get("/admin/services")
def admin_services_page(request: Request, db: Session=Depends(get_db), salon: models.Salon = Depends(authenticate_salon_admin)):
    services = db.query(models.Service).filter(models.Service.salon_id == salon.id).all()
    return templates.TemplateResponse("services.html", {"request": request, "services": services, "page": "services", "username": salon.name, "password": salon.admin_password})

@app.get("/admin/clients")
def admin_clients_page(request: Request, db: Session=Depends(get_db), salon: models.Salon = Depends(authenticate_salon_admin)):
    clients = db.query(models.Client).filter(models.Client.salon_id == salon.id).order_by(models.Client.id.desc()).limit(100).all()
    return templates.TemplateResponse("clients.html", {"request": request, "clients": clients, "page": "clients", "username": salon.name, "password": salon.admin_password})

# ==========================================
#           API БОТА
# ==========================================

# --- Clients (ИСПРАВЛЕННАЯ ЛОГИКА) ---
@app.patch("/api/v1/clients/{tid}")
def update_phone(tid: int, data: ClientUpdateSchema, db: Session = Depends(get_db), salon: models.Salon = Depends(get_current_salon)):
    # Ищем клиента
    c = db.query(models.Client).filter(models.Client.telegram_user_id == tid, models.Client.salon_id == salon.id).first()
    
    if not c:
        # Если клиента нет - СОЗДАЕМ ЕГО!
        new_client = models.Client(
            salon_id=salon.id,
            telegram_user_id=tid,
            name="Клиент из Telegram", # Имя обновится позже, если нужно
            phone_number=data.phone_number
        )
        db.add(new_client)
        db.commit()
        return {"message": "Created"}
    
    # Если есть - обновляем
    c.phone_number = data.phone_number
    db.commit()
    return {"message": "Updated"}

@app.get("/api/v1/clients/by_telegram/{tg_id}", response_model=Optional[ClientManualSchema])
def get_client_by_telegram(tg_id: int, db: Session = Depends(get_db), salon: models.Salon = Depends(get_current_salon)):
    client = db.query(models.Client).filter(models.Client.telegram_user_id == tg_id, models.Client.salon_id == salon.id).first()
    return client

# --- Appointments (Natural AI) ---
@app.post("/api/v1/appointments/natural")
def create_appointment_from_natural_language(req: AppointmentNaturalLanguageSchema, db: Session = Depends(get_db), salon: models.Salon = Depends(get_current_salon)):
    # ИСПРАВЛЕНО: используем 'req' вместо 'request'
    logging.info(f"AI Request for Salon '{salon.name}': {req.dict()}")
    
    client = db.query(models.Client).filter(models.Client.telegram_user_id == req.telegram_user_id, models.Client.salon_id == salon.id).first()
    if not client:
        client = models.Client(telegram_user_id=req.telegram_user_id, name=req.user_name, salon_id=salon.id)
        db.add(client); db.commit(); db.refresh(client)

    service = db.query(models.Service).filter(models.Service.name.ilike(f"%{req.service_name}%"), models.Service.salon_id == salon.id).first()
    if not service: raise HTTPException(404, f"Услуга '{req.service_name}' не найдена.")

    master = None
    if req.master_name:
        master = db.query(models.Master).filter(models.Master.name.ilike(f"%{req.master_name}%"), models.Master.salon_id == salon.id).first()
    if not master:
        master = db.query(models.Master).join(models.Master.services).filter(models.Service.id == service.id, models.Master.salon_id == salon.id).first()
    if not master: raise HTTPException(404, "Подходящий мастер не найден.")

    try: start_time = datetime.strptime(f"{req.appointment_date} {req.appointment_time}", "%Y-%m-%d %H:%M")
    except: raise HTTPException(400, "Invalid date")
    
    end_time = start_time + timedelta(minutes=service.duration_minutes)
    
    if db.query(models.Appointment).filter(models.Appointment.master_id == master.id, models.Appointment.start_time < end_time, models.Appointment.end_time > start_time).count() > 0:
        raise HTTPException(409, "Time booked")

    new_appt = models.Appointment(salon_id=salon.id, client_id=client.id, master_id=master.id, service_id=service.id, start_time=start_time, end_time=end_time)
    db.add(new_appt); db.commit(); db.refresh(new_appt)
    return {"message": "Success", "start_time": start_time.isoformat(), "service_name": service.name, "master_name": master.name}

# --- Остальные методы (без изменений) ---
@app.get("/api/v1/services", response_model=List[ServiceSchema])
def get_services(db: Session = Depends(get_db), salon: models.Salon = Depends(get_current_salon)):
    return db.query(models.Service).filter(models.Service.salon_id == salon.id).all()

@app.post("/api/v1/services")
def create_service(service: ServiceCreateSchema, db: Session = Depends(get_db), salon: models.Salon = Depends(authenticate_salon_admin)):
    new_service = models.Service(salon_id=salon.id, name=service.name, price=service.price, duration_minutes=service.duration_minutes)
    db.add(new_service); db.commit(); db.refresh(new_service)
    return new_service

@app.put("/api/v1/services/{service_id}")
def update_service(service_id: int, service_data: ServiceUpdateSchema, db: Session = Depends(get_db), salon: models.Salon = Depends(authenticate_salon_admin)):
    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.salon_id == salon.id).first()
    if not service: raise HTTPException(404, "Not found")
    service.name = service_data.name; service.price = service_data.price; service.duration_minutes = service_data.duration_minutes
    db.commit()
    return service

@app.get("/api/v1/masters", response_model=List[MasterSchema])
def get_masters(db: Session = Depends(get_db), salon: models.Salon = Depends(get_current_salon)):
    return db.query(models.Master).filter(models.Master.salon_id == salon.id).all()

@app.post("/api/v1/masters")
def create_master(master_data: MasterCreateSchema, db: Session = Depends(get_db), salon: models.Salon = Depends(authenticate_salon_admin)):
    new_master = models.Master(salon_id=salon.id, name=master_data.name, specialization=master_data.specialization, description=master_data.description)
    if master_data.service_ids:
        services = db.query(models.Service).filter(models.Service.id.in_(master_data.service_ids), models.Service.salon_id == salon.id).all()
        new_master.services = services
    db.add(new_master); db.commit(); db.refresh(new_master)
    return new_master

@app.put("/api/v1/masters/{master_id}")
def update_master(master_id: int, master_data: MasterUpdateSchema, db: Session = Depends(get_db), salon: models.Salon = Depends(authenticate_salon_admin)):
    master = db.query(models.Master).filter(models.Master.id == master_id, models.Master.salon_id == salon.id).first()
    if not master: raise HTTPException(404, "Not found")
    master.name = master_data.name; master.specialization = master_data.specialization; master.description = master_data.description
    if master_data.service_ids is not None:
        services = db.query(models.Service).filter(models.Service.id.in_(master_data.service_ids), models.Service.salon_id == salon.id).all()
        master.services = services
    db.commit()
    return master

@app.get("/api/v1/services/{service_id}/masters", response_model=List[MasterSchema])
def get_masters_for_service(service_id: int, db: Session = Depends(get_db), salon: models.Salon = Depends(get_current_salon)):
    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.salon_id == salon.id).first()
    return service.masters if service else []

@app.get("/api/v1/masters/{master_id}/schedule")
def get_master_schedule(master_id: int, db: Session = Depends(get_db), salon: models.Salon = Depends(authenticate_salon_admin)):
    schedules = db.query(models.Schedule).filter(models.Schedule.master_id == master_id).all()
    result = []
    db_sched_map = {s.day_of_week: s for s in schedules}
    for day in range(1, 8):
        sched = db_sched_map.get(day)
        if sched: result.append({"day_of_week": day, "is_working": True, "start_time": sched.start_time.strftime("%H:%M"), "end_time": sched.end_time.strftime("%H:%M")})
        else: result.append({"day_of_week": day, "is_working": False, "start_time": "10:00", "end_time": "19:00"})
    return result

@app.post("/api/v1/masters/{master_id}/schedule")
def update_master_schedule(master_id: int, data: MasterScheduleUpdate, db: Session = Depends(get_db), salon: models.Salon = Depends(authenticate_salon_admin)):
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
    return {"message": "OK"}

@app.post("/api/v1/clients_manual")
def create_client_manual(data: ClientManualSchema, db: Session = Depends(get_db), salon: models.Salon = Depends(authenticate_salon_admin)):
    tg_id = data.telegram_user_id
    if tg_id is None: tg_id = -int(time_module.time() * 1000)
    if db.query(models.Client).filter(models.Client.telegram_user_id == tg_id, models.Client.salon_id == salon.id).first():
         raise HTTPException(400, "Exists")
    new_client = models.Client(salon_id=salon.id, name=data.name, phone_number=data.phone_number, telegram_user_id=tg_id)
    db.add(new_client); db.commit()
    return new_client

@app.put("/api/v1/clients_manual/{client_id}")
def update_client_manual(client_id: int, data: ClientManualSchema, db: Session = Depends(get_db), salon: models.Salon = Depends(authenticate_salon_admin)):
    client = db.query(models.Client).get(client_id)
    if not client: raise HTTPException(404, "Not found")
    client.name = data.name; client.phone_number = data.phone_number
    if data.telegram_user_id is not None and data.telegram_user_id != client.telegram_user_id:
         if db.query(models.Client).filter(models.Client.telegram_user_id == data.telegram_user_id, models.Client.salon_id == salon.id).first():
             raise HTTPException(400, "ID busy")
         client.telegram_user_id = data.telegram_user_id
    db.commit()
    return client

@app.get("/api/v1/available-slots", response_model=List[AvailableSlotSchema])
def get_available_slots(service_id: int, selected_date: date, master_id: Optional[int]=None, db: Session=Depends(get_db), salon: models.Salon = Depends(get_current_salon)):
    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.salon_id == salon.id).first()
    if not service: return []
    duration = timedelta(minutes=service.duration_minutes)
    masters_query = db.query(models.Master).join(models.Service, models.Master.services).filter(models.Service.id == service_id, models.Master.salon_id == salon.id)
    if master_id: masters_query = masters_query.filter(models.Master.id == master_id)
    potential_masters = masters_query.all()
    all_slots = []
    day_of_week = selected_date.isoweekday()
    moscow_tz = ZoneInfo("Europe/Moscow")
    now_in_moscow = datetime.now(moscow_tz)
    for master in potential_masters:
        schedule = db.query(models.Schedule).filter(models.Schedule.master_id == master.id, models.Schedule.day_of_week == day_of_week).first()
        if not schedule: continue
        start_day = datetime.combine(selected_date, time.min)
        end_day = datetime.combine(selected_date, time.max)
        appointments = db.query(models.Appointment).filter(models.Appointment.master_id == master.id, models.Appointment.start_time.between(start_day, end_day)).all()
        slot_start = datetime.combine(selected_date, schedule.start_time)
        work_end = datetime.combine(selected_date, schedule.end_time)
        while slot_start + duration <= work_end:
            if selected_date == now_in_moscow.date() and slot_start.time() <= now_in_moscow.time():
                 slot_start += timedelta(minutes=30); continue
            slot_end = slot_start + duration
            is_free = True
            for appt in appointments:
                if max(slot_start, appt.start_time) < min(slot_end, appt.end_time):
                    is_free = False; break
            if is_free: all_slots.append({"time": slot_start.strftime("%H:%M"), "master_id": master.id})
            slot_start += timedelta(minutes=30)
    return sorted(all_slots, key=lambda x: x['time'])

@app.get("/api/v1/active-days-in-month", response_model=List[int])
def get_active_days(service_id: int, year: int, month: int, master_id: Optional[int]=None, db: Session=Depends(get_db), salon: models.Salon = Depends(get_current_salon)):
    try: num_days = calendar.monthrange(year, month)[1]
    except: return []
    active_days = []
    moscow_tz = ZoneInfo("Europe/Moscow")
    today_moscow = datetime.now(moscow_tz).date()
    for day in range(1, num_days + 1):
        current_date = date(year, month, day)
        if current_date < today_moscow: continue
        if get_available_slots(service_id, current_date, master_id, db, salon):
            active_days.append(day)
    return active_days

@app.post("/api/v1/appointments")
def create_appointment(appt: AppointmentCreateSchema, db: Session = Depends(get_db), salon: models.Salon = Depends(get_current_salon)):
    client = db.query(models.Client).filter(models.Client.telegram_user_id == appt.telegram_user_id, models.Client.salon_id == salon.id).first()
    if not client:
        client = models.Client(telegram_user_id=appt.telegram_user_id, name=appt.user_name, salon_id=salon.id)
        db.add(client); db.commit(); db.refresh(client)
    service = db.query(models.Service).filter(models.Service.id == appt.service_id, models.Service.salon_id == salon.id).first()
    master = db.query(models.Master).filter(models.Master.id == appt.master_id, models.Master.salon_id == salon.id).first()
    start_time = appt.start_time
    end_time = start_time + timedelta(minutes=service.duration_minutes)
    if db.query(models.Appointment).filter(models.Appointment.master_id == master.id, models.Appointment.start_time < end_time, models.Appointment.end_time > start_time).count() > 0:
        raise HTTPException(409, "Time booked")
    new_appt = models.Appointment(salon_id=salon.id, client_id=client.id, master_id=master.id, service_id=service.id, start_time=start_time, end_time=end_time)
    db.add(new_appt); db.commit(); db.refresh(new_appt)
    return {"message": "Success", "appointment_id": new_appt.id}

@app.post("/api/v1/appointments/admin")
def create_appointment_admin(appt: AppointmentAdminCreateSchema, db: Session = Depends(get_db), salon: models.Salon = Depends(authenticate_salon_admin)):
    service = db.query(models.Service).filter(models.Service.id == appt.service_id, models.Service.salon_id == salon.id).first()
    if not service: raise HTTPException(404, "Service not found")
    end_time = appt.start_time + timedelta(minutes=service.duration_minutes)
    if db.query(models.Appointment).filter(models.Appointment.master_id == appt.master_id, models.Appointment.start_time < end_time, models.Appointment.end_time > appt.start_time).count() > 0:
        raise HTTPException(409, "Time booked")
    new_appt = models.Appointment(salon_id=salon.id, client_id=appt.client_id, master_id=appt.master_id, service_id=appt.service_id, start_time=appt.start_time, end_time=end_time)
    db.add(new_appt); db.commit(); db.refresh(new_appt)
    return new_appt

@app.put("/api/v1/appointments/{appt_id}")
def update_appointment(appt_id: int, appt_data: AppointmentUpdateSchema, db: Session = Depends(get_db), salon: models.Salon = Depends(authenticate_salon_admin)):
    appt = db.query(models.Appointment).filter(models.Appointment.id == appt_id, models.Appointment.salon_id == salon.id).first()
    if not appt: raise HTTPException(404, "Not found")
    service = db.query(models.Service).get(appt_data.service_id)
    end_time = appt_data.start_time + timedelta(minutes=service.duration_minutes)
    if db.query(models.Appointment).filter(models.Appointment.id != appt_id, models.Appointment.master_id == appt_data.master_id, models.Appointment.start_time < end_time, models.Appointment.end_time > appt_data.start_time).count() > 0:
        raise HTTPException(409, "Time booked")
    appt.master_id = appt_data.master_id; appt.service_id = appt_data.service_id; appt.start_time = appt_data.start_time; appt.end_time = end_time
    db.commit()
    return appt

@app.delete("/api/v1/appointments/{aid}")
def delete_appt_admin(aid: int, db: Session = Depends(get_db), salon: models.Salon = Depends(authenticate_salon_admin)):
    a = db.query(models.Appointment).filter(models.Appointment.id == aid, models.Appointment.salon_id == salon.id).first()
    if a: db.delete(a); db.commit()
    return {"message": "Deleted"}

@app.delete("/api/v1/bot/appointments/{aid}")
def delete_appt_bot(aid: int, db: Session = Depends(get_db), salon: models.Salon = Depends(get_current_salon)):
    # Бот может удалить запись, только если она принадлежит этому салону
    a = db.query(models.Appointment).filter(models.Appointment.id == aid, models.Appointment.salon_id == salon.id).first()
    if not a: 
        raise HTTPException(404, "Appointment not found")
    db.delete(a)
    db.commit()
    return {"message": "Deleted by bot"}

@app.get("/api/v1/clients/{tid}/appointments", response_model=List[AppointmentInfoSchema])
def get_client_appts(tid: int, db: Session = Depends(get_db), salon: models.Salon = Depends(get_current_salon)):
    client = db.query(models.Client).filter(models.Client.telegram_user_id == tid, models.Client.salon_id == salon.id).first()
    if not client: return []
    appts = db.query(models.Appointment).filter(models.Appointment.client_id == client.id, models.Appointment.start_time >= datetime.utcnow()).all()
    return [{"id": a.id, "start_time": a.start_time, "service_name": a.service.name, "master_name": a.master.name} for a in appts]
