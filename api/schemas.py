# api/schemas.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class ServiceSchema(BaseModel):
    id: int; name: str; price: int; duration_minutes: int
    class Config: from_attributes = True

class MasterSchema(BaseModel):
    id: int; name: str; specialization: str; description: Optional[str] = None
    class Config: from_attributes = True

class AppointmentInfoSchema(BaseModel):
    id: int; start_time: datetime; service_name: str; master_name: str
    class Config: from_attributes = True

class AppointmentCreateSchema(BaseModel):
    telegram_user_id: int; user_name: str; service_id: int; master_id: int; start_time: datetime

class ClientUpdateSchema(BaseModel):
    phone_number: str

class AvailableSlotSchema(BaseModel):
    time: str; master_id: int

class AppointmentNaturalLanguageSchema(BaseModel):
    telegram_user_id: int; user_name: str; service_name: str; appointment_date: str; appointment_time: str; master_name: Optional[str] = None

class SimpleServiceSchema(BaseModel):
    name: str; price: int; duration_minutes: int
    class Config: from_attributes = True

class SimpleMasterSchema(BaseModel):
    name: str; specialization: str; services: list[str]

class SalonInfoSchema(BaseModel):
    services: list[SimpleServiceSchema]; masters: list[SimpleMasterSchema]
