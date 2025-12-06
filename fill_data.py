import sys
import os
from datetime import time

# Добавляем текущую папку в путь, чтобы видеть models.py и database.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import models
from database import SessionLocal

def fill_empty_salons():
    db = SessionLocal()
    try:
        # Получаем все активные салоны
        salons = db.query(models.Salon).filter(models.Salon.is_active == True).all()
        print(f"Найдено активных салонов: {len(salons)}")

        for salon in salons:
            # Проверяем, есть ли уже услуги. Если есть - пропускаем.
            if db.query(models.Service).filter(models.Service.salon_id == salon.id).count() > 0:
                print(f"--- Салон '{salon.name}' уже заполнен. Пропускаем.")
                continue

            print(f"+++ Наполняем салон '{salon.name}' демо-данными...")

            # 1. Создаем Услугу
            demo_service = models.Service(
                salon_id=salon.id,
                name="Тестовая стрижка",
                price=1500,
                duration_minutes=60
            )
            db.add(demo_service)
            db.commit()
            db.refresh(demo_service)

            # 2. Создаем Мастера
            demo_master = models.Master(
                salon_id=salon.id,
                name="Мастер (Демо)",
                specialization="Универсал",
                description="Автоматически созданный мастер для теста."
            )
            # Привязываем услугу
            demo_master.services.append(demo_service)
            db.add(demo_master)
            db.commit()
            db.refresh(demo_master)

            # 3. Создаем График (Пн-Пт)
            schedules = []
            for day in range(1, 6):
                schedules.append(models.Schedule(
                    master_id=demo_master.id,
                    day_of_week=day,
                    start_time=time(10, 0),
                    end_time=time(19, 0)
                ))
            db.add_all(schedules)
            db.commit()
            
            print(f"    -> Успешно! Добавлен мастер '{demo_master.name}' и услуга.")

    except Exception as e:
        print(f"ОШИБКА: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    fill_empty_salons()
