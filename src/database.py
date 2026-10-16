import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean
from datetime import datetime

# لا قيمة افتراضية هنا: كلمة المرور/الاتصال يجب أن تأتي من البيئة فقط.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "❌ متغير DATABASE_URL غير معرّف. "
        "عرّفه في ملف .env أو في بيئة الحاوية (انظر .env.example). "
        "مثال: postgresql+asyncpg://user:password@postgres:5432/surveillance"
    )

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# ... (نفس تعريفات الجداول السابقة)
