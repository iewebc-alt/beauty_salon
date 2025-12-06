import sys
import os
from datetime import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from sqlalchemy import text
import models
from database import SessionLocal, engine

def fill_eleganse_data():
    db: Session = SessionLocal()
    
    # 1. Ищем салон "Элеганс"
    print("🔍 Ищу салон 'Элеганс'...")
    salon = db.query(models.Salon).filter(
        (models.Salon.title.ilike("%Элеганс%")) | (models.Salon.name == "salon_elegans")
    ).first()

    if not salon:
        print("❌ Салон 'Элеганс' не найден! Создайте его в /superadmin.")
        return

    print(f"✅ Салон найден: {salon.title} (ID: {salon.id})")

    # 2. Очистка старых данных
    print("🧹 Очистка старых данных салона...")
    
    # Сначала находим ID всех мастеров этого салона
    masters = db.query(models.Master).filter(models.Master.salon_id == salon.id).all()
    master_ids = [m.id for m in masters]
    
    if master_ids:
        # А. Удаляем расписание
        db.query(models.Schedule).filter(models.Schedule.master_id.in_(master_ids)).delete(synchronize_session=False)
        
        # Б. Удаляем связи Мастер-Услуга (ВОТ ЭТОГО НЕ ХВАТАЛО)
        # Так как SQLAlchemy не дает прямого доступа к association table в ORM, делаем через raw SQL
        if master_ids:
            # Превращаем список ID в строку для SQL (1, 2, 3)
            ids_str = ",".join(map(str, master_ids))
            db.execute(text(f"DELETE FROM master_services WHERE master_id IN ({ids_str})"))
            
    # В. Удаляем мастеров
    db.query(models.Master).filter(models.Master.salon_id == salon.id).delete(synchronize_session=False)
    
    # Г. Удаляем услуги
    db.query(models.Service).filter(models.Service.salon_id == salon.id).delete(synchronize_session=False)
    
    db.commit()

    # 3. Создаем Услуги (10 шт)
    print("💅 Создаем услуги...")
    services_data = [
        {"name": "Женская стрижка + укладка", "price": 2500, "duration": 60},
        {"name": "Окрашивание корней", "price": 3500, "duration": 90},
        {"name": "Сложное окрашивание (Airtouch)", "price": 8000, "duration": 240},
        {"name": "Уход 'Счастье для волос'", "price": 4000, "duration": 90},
        {"name": "Маникюр с покрытием Gel", "price": 2200, "duration": 90},
        {"name": "Снятие + Маникюр (без покрытия)", "price": 1200, "duration": 60},
        {"name": "Педикюр SMART полный", "price": 2800, "duration": 90},
        {"name": "Архитектура бровей (хна/краска)", "price": 1200, "duration": 45},
        {"name": "Ламинирование ресниц", "price": 2500, "duration": 60},
        {"name": "Чистка лица комбинированная", "price": 3500, "duration": 90},
    ]

    created_services = {}
    for s_data in services_data:
        service = models.Service(
            salon_id=salon.id,
            name=s_data["name"],
            price=s_data["price"],
            duration_minutes=s_data["duration"]
        )
        db.add(service)
        db.commit()
        db.refresh(service)
        created_services[s_data["name"]] = service

    # 4. Создаем Мастеров (5 шт)
    print("👩‍🦰 Создаем мастеров...")

    m1 = models.Master(salon_id=salon.id, name="Елена Волкова", specialization="Топ-стилист по волосам", description="Эксперт по блонду.")
    m1.services.extend([created_services["Женская стрижка + укладка"], created_services["Окрашивание корней"], created_services["Сложное окрашивание (Airtouch)"], created_services["Уход 'Счастье для волос'"]])
    
    m2 = models.Master(salon_id=salon.id, name="Алина Соколова", specialization="Мастер маникюра", description="Идеальные блики.")
    m2.services.extend([created_services["Маникюр с покрытием Gel"], created_services["Снятие + Маникюр (без покрытия)"], created_services["Педикюр SMART полный"]])
    
    m3 = models.Master(salon_id=salon.id, name="Мария Ким", specialization="Бровист", description="Естественный взгляд.")
    m3.services.extend([created_services["Архитектура бровей (хна/краска)"], created_services["Ламинирование ресниц"]])
    
    m4 = models.Master(salon_id=salon.id, name="Виктория Романова", specialization="Врач-косметолог", description="Медицинское образование.")
    m4.services.extend([created_services["Чистка лица комбинированная"], created_services["Уход 'Счастье для волос'"]])
    
    m5 = models.Master(salon_id=salon.id, name="Дарья Новикова", specialization="Junior-мастер", description="Старательный мастер.")
    m5.services.extend([created_services["Женская стрижка + укладка"], created_services["Маникюр с покрытием Gel"]])

    db.add_all([m1, m2, m3, m4, m5])
    db.commit()
    
    # 5. Графики
    print("📅 Создаем графики...")
    for m in [m1, m4]: # Пн, Ср, Пт
        for d in [1, 3, 5]: db.add(models.Schedule(master_id=m.id, day_of_week=d, start_time=time(10,0), end_time=time(20,0)))
            
    for m in [m2, m3]: # Вт, Чт, Сб
        for d in [2, 4, 6]: db.add(models.Schedule(master_id=m.id, day_of_week=d, start_time=time(9,0), end_time=time(21,0)))
            
    for d in [6, 7]: # Выходные
        db.add(models.Schedule(master_id=m5.id, day_of_week=d, start_time=time(10,0), end_time=time(18,0)))

    db.commit()
    print("✨ Все данные успешно загружены!")
    db.close()

if __name__ == "__main__":
    fill_eleganse_data()
