import logging
import os
import threading
from urllib.parse import quote
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean
from datetime import datetime

logger = logging.getLogger(__name__)

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


class AgentDecision(Base):
    """سجل قرارات الوكيل (Audit Trail) — إثبات استقلالية اتخاذ القرار:
    كل تنبيه أُرسل أو أُلغي أو حدث شاذ رُفع مستواه يُسجَّل هنا بسببه"""

    __tablename__ = "agent_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.now, index=True)
    camera_id = Column(String(64), nullable=False, default="")
    # القيم المتوقعة: alert_sent / alert_suppressed / anomaly_escalated / camera_offline
    decision_type = Column(String(64), nullable=False, index=True)
    reasoning = Column(Text, nullable=False, default="")
    confidence = Column(Float, nullable=True)


_employees_schema_ready = False


async def init_employees() -> None:
    """إنشاء جدول employees مرة واحدة لكل عملية (idempotent) — نفس نمط init_auth_db"""
    global _employees_schema_ready
    if _employees_schema_ready:
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _employees_schema_ready = True


_agent_decisions_schema_ready = False


async def init_agent_decisions() -> None:
    """إنشاء جدول agent_decisions مرة واحدة لكل عملية (idempotent) — API"""
    global _agent_decisions_schema_ready
    if _agent_decisions_schema_ready:
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _agent_decisions_schema_ready = True


# ------------------- تسجيل قرارات الوكيل من حاوية agent -------------------
# ثريدات الكاميرا في main.py متزامنة (بلا event loop)، فالكتابة هنا عبر
# psycopg2 (نفس منهج face_recognizer) باتصال قصير لكل قرار — الأحداث نادرة
# (مقيدة بمهلات التكرار) فلا ضغط على القاعدة.

# RLock وليس Lock: record_agent_decision_sync يحمل القفل ثم يستدعي
# ensure_agent_decisions_table الذي يعيد اكتسابه — Lock العادي كان سيتجمّد
_decision_write_lock = threading.RLock()
_decision_table_ready = False


def _psycopg_url() -> str:
    """DATABASE_URL بصيغة psycopg2 (postgresql:// بدل postgresql+asyncpg://).

    نفس تشكيل _normalize_db_url (تقسيم عند آخر @ و quote بيانات الدخول) —
    كلمة المرور الخام من docker-compose قد تحتوي @ / ! وتكسر التحويل الأعمى."""
    url = os.getenv("DATABASE_URL") or ""
    if not url:
        return ""
    return _normalize_db_url(url).replace("postgresql+asyncpg://", "postgresql://", 1)


def ensure_agent_decisions_table() -> bool:
    """CREATE TABLE IF NOT EXISTS — idempotent، يُستدعى عند تشغيل الوكيل
    وأول تسجيل قرار (يغطي أي ترتيب إقلاع بين حاويتي agent و API)"""
    global _decision_table_ready
    url = _psycopg_url()
    if not url:
        logger.warning("⚠️ DATABASE_URL غير معرّف — سجل قرارات الوكيل معطّل")
        return False
    try:
        import psycopg2

        with _decision_write_lock:
            if _decision_table_ready:
                return True
            conn = psycopg2.connect(url, connect_timeout=3)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "CREATE TABLE IF NOT EXISTS agent_decisions ("
                        "id SERIAL PRIMARY KEY, "
                        '"timestamp" TIMESTAMP NOT NULL DEFAULT NOW(), '
                        "camera_id VARCHAR(64) NOT NULL DEFAULT '', "
                        "decision_type VARCHAR(64) NOT NULL, "
                        "reasoning TEXT NOT NULL DEFAULT '', "
                        "confidence DOUBLE PRECISION)"
                    )
                    cur.execute(
                        "CREATE INDEX IF NOT EXISTS ix_agent_decisions_timestamp "
                        "ON agent_decisions (timestamp)"
                    )
                    cur.execute(
                        "CREATE INDEX IF NOT EXISTS ix_agent_decisions_decision_type "
                        "ON agent_decisions (decision_type)"
                    )
                conn.commit()
            finally:
                conn.close()
            _decision_table_ready = True
        return True
    except Exception as exc:
        logger.warning(f"⚠️ تعذّر إنشاء جدول قرارات الوكيل: {exc}")
        return False


def record_agent_decision_sync(
    camera_id,
    decision_type: str,
    reasoning: str,
    confidence=None,
) -> bool:
    """إدراج قرار في agent_decisions متزامناً (يعمل داخل ثريدات الكاميرا).

    fail-open حصراً: أي فشل (قاعدة/شبكة) يُسجَّل تحذيراً فقط ولا يرفع
    استثناءً أبداً كي لا يُعطَّل خط الكشف/التنبيه في الوكيل."""
    url = _psycopg_url()
    if not url:
        return False
    try:
        import psycopg2

        with _decision_write_lock:
            ensure_agent_decisions_table()
            conn = psycopg2.connect(url, connect_timeout=3)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO agent_decisions "
                        '("timestamp", camera_id, decision_type, reasoning, confidence) '
                        "VALUES (NOW(), %s, %s, %s, %s)",
                        (str(camera_id), decision_type, reasoning, confidence),
                    )
                conn.commit()
            finally:
                conn.close()
        return True
    except Exception as exc:
        logger.warning(f"⚠️ تعذّر تسجيل قرار الوكيل [{decision_type}]: {exc}")
        return False
