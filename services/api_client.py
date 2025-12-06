import httpx
from typing import List, Optional, Dict, Any
from config import API_URL

class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=self.base_url)

    # Вспомогательный метод для заголовков
    def _headers(self, token: str):
        return {"X-Salon-Token": token}

    async def get_services(self, token: str) -> List[Dict[str, Any]]:
        response = await self.client.get("/api/v1/services", headers=self._headers(token))
        response.raise_for_status()
        return response.json()

    async def get_masters_for_service(self, service_id: int, token: str) -> List[Dict[str, Any]]:
        response = await self.client.get(f"/api/v1/services/{service_id}/masters", headers=self._headers(token))
        response.raise_for_status()
        return response.json()

    async def get_all_masters(self, token: str) -> List[Dict[str, Any]]:
        response = await self.client.get("/api/v1/masters", headers=self._headers(token))
        response.raise_for_status()
        return response.json()

    async def get_active_days(self, service_id: int, year: int, month: int, token: str, master_id: Optional[int] = None) -> List[int]:
        params = {"service_id": service_id, "year": year, "month": month}
        if master_id: params["master_id"] = master_id
        response = await self.client.get("/api/v1/active-days-in-month", params=params, headers=self._headers(token))
        response.raise_for_status()
        return response.json()

    async def get_available_slots(self, service_id: int, selected_date: str, token: str, master_id: Optional[int] = None) -> List[Dict[str, Any]]:
        params = {"service_id": service_id, "selected_date": selected_date}
        if master_id: params["master_id"] = master_id
        response = await self.client.get("/api/v1/available-slots", params=params, headers=self._headers(token))
        response.raise_for_status()
        return response.json()

    async def create_appointment(self, payload: Dict[str, Any], token: str) -> Dict[str, Any]:
        response = await self.client.post("/api/v1/appointments", json=payload, headers=self._headers(token))
        response.raise_for_status()
        return response.json()

    async def get_client_appointments(self, telegram_user_id: int, token: str) -> List[Dict[str, Any]]:
        response = await self.client.get(f"/api/v1/clients/{telegram_user_id}/appointments", headers=self._headers(token))
        response.raise_for_status()
        return response.json()

    async def delete_appointment(self, appointment_id: int, token: str):
        response = await self.client.delete(f"/api/v1/bot/appointments/{appointment_id}", headers=self._headers(token))
        response.raise_for_status()

    async def update_client_phone(self, telegram_user_id: int, phone_number: str, token: str):
        payload = {"phone_number": phone_number}
        response = await self.client.patch(f"/api/v1/clients/{telegram_user_id}", json=payload, headers=self._headers(token))
        response.raise_for_status()

    async def create_natural_appointment(self, payload: Dict[str, Any], token: str) -> Dict[str, Any]:
        response = await self.client.post("/api/v1/appointments/natural", json=payload, headers=self._headers(token))
        response.raise_for_status()
        return response.json()

    async def get_client_by_tg_id(self, telegram_id: int, token: str) -> Optional[Dict[str, Any]]:
        response = await self.client.get(f"/api/v1/clients/by_telegram/{telegram_id}", headers=self._headers(token))
        if response.status_code == 200 and response.content:
            return response.json()
        return None

api_client = ApiClient(API_URL)
