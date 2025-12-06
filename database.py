import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base # <-- ИЗМЕНЕНИЕ
from config import DATABASE_URL

# Настройки подключения
connect_args = {}

if ":6432" in DATABASE_URL:
    connect_args = {
        "sslmode": "verify-full",
        "sslrootcert": "root.crt"
    }

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base() # <-- ИЗМЕНЕНИЕ
