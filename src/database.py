import os
from urllib.parse import quote
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean
from datetime import datetime

def _normalize_db_url(url: str) -> str:
    """إعادة تشكيل DATABASE_URL منحاً ببيانات دخول مشفرة (quote).

    الإلازم: كلمات المرور التي تحتوي أحرافاً خاصة مثل @ أو ! تُسوّى
    (split عند أول @) فيقتطع host وبالتالي فشل DNS ('Name or service
    not known'). الحل: نسبّ من اليمين (آخر @ فاصل) ثم نعمل quote.
    """
    scheme, _, rest = url.partition("://")
    userinfo, _, hostpart = rest.rpartition("@")
    if not userinfo:
        # لا بيانات دخول في الرابط (مثل sqlite) — لا شيء لنسويه
        return url
    user, _, password = userinfo.partition(":")
    return f"{scheme}://{quote(user, safe='')}:{quote(password, safe='')}@{hostpart}"

# لا قيمة افتراضية هنا: كلمة المرور/الاتصال يجب أن تأتي من البيئة فقط.
DATABASE_URL = _normalize_db_url(os.getenv("DATABASE_URL") or "")
if not os.getenv("DATABASE_URL"):
    raise RuntimeError(
        "❌ متغير DATABASE_URL غير معرّف. "
        "عرّفه في ملف .env أو في بيئة الحاوية (انظر .env.example). "
        "مثال: postgresql+asyncpg://user:password@postgres:5432/surveillance"
    )

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


class Employee(Base):
    """موظف سُجّلت بصمة وجهه — التعرف عليه يمنع تنبيه تسلل كاذب لفريق العمل"""

    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    role = Column(String(255), nullable=True)
    # بصمة الوجه: قائمة floats مرمّزة JSON (لا تُخزَّن الصورة نفسها في القاعدة)
    face_encoding = Column(Text, nullable=False)


_employees_schema_ready = False


async def init_employees() -> None:
    """إنشاء جدول employees مرة واحدة لكل عملية (idempotent) — نفس نمط init_auth_db"""
    global _employees_schema_ready
    if _employees_schema_ready:
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _employees_schema_ready = True
