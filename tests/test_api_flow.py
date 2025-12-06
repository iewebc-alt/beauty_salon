import base64
from config import SUPER_ADMIN_USERNAME, SUPER_ADMIN_PASSWORD
from datetime import date, timedelta # Добавляем импорт для даты

# Вспомогательная функция для Basic Auth заголовка
def basic_auth(username, password):
    token = base64.b64encode(f"{username}:{password}".encode('utf-8')).decode("ascii")
    return {"Authorization": f"Basic {token}"}

def test_full_flow(client):
    # 1. СУПЕР-АДМИН: Создаем салон
    super_auth = basic_auth(SUPER_ADMIN_USERNAME, SUPER_ADMIN_PASSWORD)
    salon_data = {
        "name": "test_salon",
        "title": "Тестовый Салон",
        "token": "123:TEST_TOKEN",
        "password": "admin"
    }
    # Используем FormData
    response = client.post("/superadmin/salons", data=salon_data, headers=super_auth)
    assert response.status_code == 200
    assert "ok" in response.json()["status"]

    # 2. АДМИН САЛОНА: Создаем услугу
    salon_auth = basic_auth("test_salon", "admin")
    
    # Pydantic теперь ожидает ID, но при создании мы его не знаем. 
    # API должен его проигнорировать. Мы передадим все поля, кроме ID.
    service_data = {"name": "Стрижка", "price": 1000, "duration_minutes": 60}
    response = client.post("/api/v1/services", json=service_data, headers=salon_auth)
    assert response.status_code == 200
    service_id = response.json()["id"]

    # 3. АДМИН САЛОНА: Создаем мастера
    master_data = {
        "name": "Мастер Тест",
        "specialization": "Профи",
        "description": "Тест",
        "service_ids": [service_id]
    }
    response = client.post("/api/v1/masters", json=master_data, headers=salon_auth)
    assert response.status_code == 200
    master_id = response.json()["id"]

    # 4. АДМИН САЛОНА: Создаем график
    schedule_items = [{"day_of_week": i, "is_working": True, "start_time": "10:00", "end_time": "19:00"} for i in range(1, 8)]
    response = client.post(f"/api/v1/masters/{master_id}/schedule", json={"items": schedule_items}, headers=salon_auth)
    assert response.status_code == 200

    # 5. БОТ: Проверяем доступные слоты
    bot_headers = {"X-Salon-Token": "123:TEST_TOKEN"}
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    
    response = client.get(
        f"/api/v1/available-slots?service_id={service_id}&selected_date={tomorrow}", 
        headers=bot_headers
    )
    assert response.status_code == 200
    slots = response.json()
    assert len(slots) > 0 
    assert slots[0]["time"] == "10:00"

    # 6. БОТ: Создаем запись
    appt_data = {
        "telegram_user_id": 999999,
        "user_name": "Test Client",
        "service_id": service_id,
        "master_id": master_id,
        "start_time": f"{tomorrow}T10:00:00"
    }
    response = client.post("/api/v1/appointments", json=appt_data, headers=bot_headers)
    assert response.status_code == 200
    assert "Success" in response.json()["message"]

    # 7. БОТ: Проверяем конфликт
    response = client.post("/api/v1/appointments", json=appt_data, headers=bot_headers)
    assert response.status_code == 409
    assert "booked" in response.json()["detail"]
