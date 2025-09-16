# database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import DATABASE_URL

Base = declarative_base()  # Переместим определение Base сюда

SessionLocal = sessionmaker(autocommit=False, autoflush=False)

def get_engine():
    return create_engine(DATABASE_URL)
