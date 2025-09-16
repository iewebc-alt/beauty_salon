# api/main.py
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

# Настройка логирования
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
