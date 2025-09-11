# api/routers/bot.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import date, datetime, time, timedelta
import calendar
import logging

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
        start_of_day = datetime.combine(selected_date, time.min)
        end_of_day = datetime.combine(selected_date, time.max)
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
    now_naive = datetime.utcnow()

    for master in potential_masters:
        schedule = db.query(models.Schedule).filter(models.Schedule.master_id == master.id, models.Schedule.day_of_week == day_of_week).first()
        if not schedule: continue
        
        master_appointments = db.query(models.Appointment).filter(
            models.Appointment.master_id == master.id,
            models.Appointment.start_time.between(datetime.combine(selected_date, time.min), datetime.combine(selected_date, time.max))
        ).all()
        
        slot_start = datetime.combine(selected_date, schedule.start_time)
        
        if selected_date == date.today():
            slot_start = max(slot_start, now_naive)
            if slot_start.minute % 15 != 0:
                minutes_to_add = 15 - (slot_start.minute % 15)
                slot_start += timedelta(minutes=minutes_to_add)
                slot_start = slot_start.replace(second=0, microsecond=0)

        workday_end = datetime.combine(selected_date, schedule.end_time)
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
        slot_start_dt = datetime.strptime(f"{selected_date} {slot['time']}", "%Y-%m-%d %H:%M")
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

@router.post("/appointments/natural")
def create_appointment_from_natural_language(request: schemas.AppointmentNaturalLanguageSchema, db: Session = Depends(get_db)):
    logging.info(f"Received natural language appointment request: {request.dict()}")
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
        start_time = datetime.strptime(f"{request.appointment_date} {request.appointment_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты или времени. Используйте YYYY-MM-DD и HH:MM.")
    end_time = start_time + timedelta(minutes=service.duration_minutes)
    master_conflicting = db.query(models.Appointment).filter(models.Appointment.master_id == master.id, models.Appointment.start_time < end_time, models.Appointment.end_time > start_time).count()
    if master_conflicting > 0: raise HTTPException(status_code=409, detail="Это время у выбранного мастера уже занято.")
    client_conflicting = db.query(models.Appointment).filter(models.Appointment.client_id == client.id, models.Appointment.start_time < end_time, models.Appointment.end_time > start_time).count()
    if client_conflicting > 0: raise HTTPException(status_code=409, detail="У Вас уже есть другая запись на это время.")
    new_appointment = models.Appointment(client_id=client.id, master_id=master.id, service_id=service.id, start_time=start_time, end_time=end_time)
    db.add(new_appointment); db.commit(); db.refresh(new_appointment)
    return {
        "id": new_appointment.id,
        "start_time": new_appointment.start_time,
        "service_name": service.name,
        "master_name": master.name
    }

@router.post("/appointments")
def create_appointment(appointment: schemas.AppointmentCreateSchema, db: Session = Depends(get_db)):
    logging.info(f"Received appointment request: {appointment.dict()}")
    client = db.query(models.Client).filter(models.Client.telegram_user_id == appointment.telegram_user_id).first()
    if not client:
        client = models.Client(telegram_user_id=appointment.telegram_user_id, name=appointment.user_name)
        db.add(client); db.commit(); db.refresh(client)
    service = db.query(models.Service).filter(models.Service.id == appointment.service_id).first()
    master = db.query(models.Master).filter(models.Master.id == appointment.master_id).first()
    if not service or not master: raise HTTPException(status_code=404, detail="Service or Master not found")
    start_time = appointment.start_time; end_time = start_time + timedelta(minutes=service.duration_minutes)
    start_time_naive = start_time.replace(tzinfo=None); end_time_naive = end_time.replace(tzinfo=None)
    master_conflicting = db.query(models.Appointment).filter(models.Appointment.master_id == appointment.master_id, models.Appointment.start_time < end_time_naive, models.Appointment.end_time > start_time_naive).count()
    if master_conflicting > 0: raise HTTPException(status_code=409, detail="This time slot has just been booked. Please choose another time.")
    client_conflicting = db.query(models.Appointment).filter(models.Appointment.client_id == client.id, models.Appointment.start_time < end_time_naive, models.Appointment.end_time > start_time_naive).count()
    if client_conflicting > 0: raise HTTPException(status_code=409, detail="У Вас уже есть другая запись на это время.")
    new_appointment = models.Appointment(client_id=client.id, master_id=appointment.master_id, service_id=appointment.service_id, start_time=start_time_naive, end_time=end_time_naive)
    db.add(new_appointment); db.commit(); db.refresh(new_appointment)
    return {
        "id": new_appointment.id,
        "start_time": new_appointment.start_time,
        "service_name": service.name,
        "master_name": master.name
    }

@router.get("/clients/{telegram_user_id}/appointments", response_model=List[schemas.AppointmentInfoSchema])
def get_client_appointments(telegram_user_id: int, db: Session = Depends(get_db)):
    client = db.query(models.Client).filter(models.Client.telegram_user_id == telegram_user_id).first()
    if not client: return []
    now_naive = datetime.utcnow()
    appointments = db.query(models.Appointment).options(
        joinedload(models.Appointment.service),
        joinedload(models.Appointment.master)
    ).filter(
        models.Appointment.client_id == client.id,
        models.Appointment.start_time >= now_naive
    ).order_by(models.Appointment.start_time).all()
    
    result = []
    for appt in appointments:
        result.append({
            "id": appt.id,
            "start_time": appt.start_time,
            "service_name": appt.service.name,
            "master_name": appt.master.name
        })
    return result

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
