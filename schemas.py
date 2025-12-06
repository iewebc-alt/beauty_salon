from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime

# --- ВАЖНО: Определяем базовую конфигурацию один раз ---
# Все остальные модели будут её наследовать
class BaseConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

# Услуги
class ServiceSchema(BaseConfig):
    id: int
    name: str
    price: int
    duration_minutes: int

class ServiceUpdateSchema(BaseConfig):
    name: str
    price: int
    duration_minutes: int

# Мастера
class MasterSchema(BaseConfig):
    id: int
    name: str
    specialization: str
    description: Optional[str] = None

class MasterCreateSchema(BaseConfig):
    name: str
    specialization: str
    description: Optional[str] = None
    service_ids: List[int] = []

class MasterUpdateSchema(BaseConfig):
    name: str
    specialization: str
    description: Optional[str] = None
    service_ids: List[int] = []

# График работы
class ScheduleItem(BaseConfig):
    day_of_week: int
    is_working: bool
    start_time: str
    end_time: str

class MasterScheduleUpdate(BaseConfig):
    items: List[ScheduleItem]

# Клиенты
class ClientManualSchema(BaseConfig):
    name: str
    phone_number: str
    telegram_user_id: Optional[int] = None

class ClientUpdateSchema(BaseConfig):
    phone_number: str

# Записи (Appointments)
class AppointmentInfoSchema(BaseConfig):
    id: int
    start_time: datetime
    service_name: str
    master_name: str

class AppointmentCreateSchema(BaseConfig):
    telegram_user_id: int
    user_name: str
    service_id: int
    master_id: int
    start_time: datetime

class AppointmentAdminCreateSchema(BaseConfig):
    client_id: int
    master_id: int
    service_id: int
    start_time: datetime

class AppointmentUpdateSchema(BaseConfig):
    master_id: int
    service_id: int
    start_time: datetime

class AppointmentNaturalLanguageSchema(BaseConfig):
    telegram_user_id: int
    user_name: str
    service_name: str
    appointment_date: str
    appointment_time: str
    master_name: Optional[str] = None

# Вспомогательные
class AvailableSlotSchema(BaseConfig):
    time: str
    master_id: int

# Салоны
class SalonUpdateSchema(BaseConfig):
    name: str
    telegram_token: str
    admin_password: str
    is_active: bool
