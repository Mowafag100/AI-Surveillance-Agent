import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean
from datetime import datetime

# استخدم SQLite مؤقتاً
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./surveillance.db")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# ... (نفس تعريفات الجداول السابقة)