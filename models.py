from sqlalchemy import (Column, Integer, String, Text, ForeignKey, Table,
                      BigInteger, Time, Date, DateTime, Boolean)
from sqlalchemy.orm import relationship
from database import Base

# Таблица Салонов
class Salon(Base):
    __tablename__ = "salons"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False) # ЭТО ЛОГИН (english)
    title = Column(String(255), nullable=True)              # ЭТО НАЗВАНИЕ (Русский)
    telegram_token = Column(String(255), unique=True, nullable=False)
    admin_password = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    
    masters = relationship("Master", back_populates="salon")
    services = relationship("Service", back_populates="salon")
    clients = relationship("Client", back_populates="salon")
    appointments = relationship("Appointment", back_populates="salon")

master_services = Table('master_services', Base.metadata,
    Column('master_id', Integer, ForeignKey('masters.id'), primary_key=True),
    Column('service_id', Integer, ForeignKey('services.id'), primary_key=True)
)

class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True, index=True)
    salon_id = Column(Integer, ForeignKey('salons.id'), nullable=False)
    telegram_user_id = Column(BigInteger, nullable=False)
    name = Column(String(255))
    phone_number = Column(String(20))
    
    salon = relationship("Salon", back_populates="clients")
    appointments = relationship("Appointment", back_populates="client")

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    salon_id = Column(Integer, ForeignKey('salons.id'), nullable=False)
    name = Column(String(255), index=True)
    price = Column(Integer)
    duration_minutes = Column(Integer)
    
    salon = relationship("Salon", back_populates="services")
    masters = relationship("Master", secondary=master_services, back_populates="services")
    appointments = relationship("Appointment", back_populates="service")

class Master(Base):
    __tablename__ = "masters"
    id = Column(Integer, primary_key=True, index=True)
    salon_id = Column(Integer, ForeignKey('salons.id'), nullable=False)
    name = Column(String(255), index=True)
    specialization = Column(String(255))
    description = Column(Text, nullable=True)
    
    salon = relationship("Salon", back_populates="masters")
    services = relationship("Service", secondary=master_services, back_populates="masters")
    schedules = relationship("Schedule", back_populates="master")
    appointments = relationship("Appointment", back_populates="master")

class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    master_id = Column(Integer, ForeignKey('masters.id'))
    day_of_week = Column(Integer, nullable=False) 
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    master = relationship("Master", back_populates="schedules")

class Appointment(Base):
    __tablename__ = "appointments"
    id = Column(Integer, primary_key=True)
    salon_id = Column(Integer, ForeignKey('salons.id'), nullable=False)
    client_id = Column(Integer, ForeignKey('clients.id'))
    master_id = Column(Integer, ForeignKey('masters.id'))
    service_id = Column(Integer, ForeignKey('services.id'))
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    
    salon = relationship("Salon", back_populates="appointments")
    client = relationship("Client", back_populates="appointments")
    master = relationship("Master", back_populates="appointments")
    service = relationship("Service", back_populates="appointments")
