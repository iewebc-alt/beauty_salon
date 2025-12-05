# tests/test_api.py
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.conftest import db, populate_test_data
from models import Service, Master, Client, Appointment

# Добавляем корневую директорию проекта в PYTHONPATH
sys.path.append(str(Path(__file__).resolve().parents[2]))

# Импортируем приложение после настройки пути
from api.main import app

client = TestClient(app)

class TestServicesAPI:
    @pytest.mark.usefixtures("populate_test_data")
    def test_get_services(self, db: Session):
        """Тестирует получение списка услуг."""
        response = client.get("/api/v1/services")
        assert response.status_code == 200
        services = response.json()
        assert len(services) > 0
        first_service = services[0]
        assert "id" in first_service
        assert "name" in first_service
        assert "price" in first_service
        assert "duration_minutes" in first_service

    @pytest.mark.usefixtures("populate_test_data")
    def test_get_service_by_id(self, db: Session):
        """Тестирует получение услуги по ID."""
        service = db.query(Service).first()
        assert service is not None
        
        response = client.get(f"/api/v1/services/{service.id}")
        assert response.status_code == 200
        service_data = response.json()
        assert service_data["id"] == service.id
        assert service_data["name"] == service.name

class TestAppointmentsAPI:
    @pytest.mark.usefixtures("populate_test_data")
    def test_create_and_get_appointment(self, db: Session):
        """Тестирует успешное создание записи и ее последующее получение."""
        appointment_data = {
            "telegram_user_id": 12345,
            "user_name": "Тестовый Пользователь",
            "service_id": 1,
            "master_id": 1,
            "start_time": "2025-10-20T10:00:00Z"
        }
        
        response_create = client.post("/api/v1/appointments", json=appointment_data)
        assert response_create.status_code == 200
        
        appointment_id = response_create.json().get("id")
        assert appointment_id is not None
        
        response_get = client.get(f"/api/v1/appointments/{appointment_id}")
        assert response_get.status_code == 200
        appointment = response_get.json()
        assert appointment["telegram_user_id"] == 12345
        assert appointment["service_id"] == 1
        assert appointment["master_id"] == 1

    @pytest.mark.usefixtures("populate_test_data")
    def test_client_double_booking_prevented(self, db: Session):
        """Тестирует, что система НЕ ПОЗВОЛЯЕТ клиенту записаться на время, на которое у него уже есть другая запись."""
        user_id = 12345
        first_appointment = {
            "telegram_user_id": user_id,
            "user_name": "Дважды Записанный",
            "service_id": 1,
            "master_id": 1,
            "start_time": "2025-10-21T11:00:00Z"
        }
        
        response1 = client.post("/api/v1/appointments", json=first_appointment)
        assert response1.status_code == 200
        
        second_appointment = {
            "telegram_user_id": user_id,
            "user_name": "Дважды Записанный",
            "service_id": 2,
            "master_id": 2,
            "start_time": "2025-10-21T11:00:00Z"
        }
        response2 = client.post("/api/v1/appointments", json=second_appointment)
        assert response2.status_code == 409
        assert "У Вас уже есть другая запись" in response2.json().get("detail", "")
