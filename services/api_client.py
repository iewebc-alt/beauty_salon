# services/api_client.py
import httpx
from typing import List, Optional, Dict, Any
from datetime import date
import json
from config import API_URL

class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=self.base_url)

    async def get_services(self) -> List[Dict[str, Any]]:
        response = await self.client.get("/api/v1/services")
        response.raise_for_status()
        return response.json()

    async def get_masters_for_service(self, service_id: int) -> List[Dict[str, Any]]:
        response = await self.client.get(f"/api/v1/services/{service_id}/masters")
        response.raise_for_status()
        return response.json()

    async def get_all_masters(self) -> List[Dict[str, Any]]:
        response = await self.client.get("/api/v1/masters")
        response.raise_for_status()
        return response.json()

    async def get_active_days(self, service_id: int, year: int, month: int, telegram_user_id: int, master_id: Optional[int] = None) -> List[int]:
        params = {"service_id": service_id, "year": year, "month": month, "telegram_user_id": telegram_user_id}
        if master_id:
            params["master_id"] = master_id
        response = await self.client.get("/api/v1/active-days-in-month", params=params)
        response.raise_for_status()
        return response.json()

    async def get_available_slots(self, service_id: int, selected_date: str, telegram_user_id: int, master_id: Optional[int] = None) -> List[Dict[str, Any]]:
        params = {"service_id": service_id, "selected_date": selected_date, "telegram_user_id": telegram_user_id}
        if master_id:
            params["master_id"] = master_id
        response = await self.client.get("/api/v1/available-slots", params=params)
        response.raise_for_status()
        return response.json()

    async def create_appointment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = await self.client.post("/api/v1/appointments", json=payload)
        response.raise_for_status()
        return response.json()

    async def get_client_appointments(self, telegram_user_id: int) -> List[Dict[str, Any]]:
        response = await self.client.get(f"/api/v1/clients/{telegram_user_id}/appointments")
        response.raise_for_status()
        return response.json()

    async def delete_appointment(self, appointment_id: int):
        response = await self.client.delete(f"/api/v1/appointments/{appointment_id}")
        response.raise_for_status()

    async def update_client_phone(self, telegram_user_id: int, phone_number: str):
        payload = {"phone_number": phone_number}
        response = await self.client.patch(f"/api/v1/clients/{telegram_user_id}", json=payload)
        response.raise_for_status()

    async def get_salon_info(self) -> Dict[str, Any]:
        response = await self.client.get("/api/v1/salon-info")
        response.raise_for_status()
        return response.json()

    async def check_availability(self, service_name: str, appointment_date: str) -> List[Dict[str, Any]]:
        all_services_resp = await self.get_services()
        service_id = None
        for service in all_services_resp:
            if service['name'].lower() in service_name.lower():
                service_id = service['id']
                break
        if not service_id:
            return []
        params = {"service_id": service_id, "selected_date": appointment_date, "telegram_user_id": 0}
        response = await self.client.get("/api/v1/available-slots", params=params)
        response.raise_for_status()
        return response.json()
        
    async def create_natural_appointment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = await self.client.post("/api/v1/appointments/natural", json=payload)
        response.raise_for_status()
        return response.json()

api_client = ApiClient(API_URL)
