"""مصادقة المستخدمين — مستوحاة من قالب full-stack-fastapi-template-nextjs.

الأنماط المقتبسة من القالب (backend/app):
  - models.py          → User + Token + TokenPayload
  - core/security.py   → bcrypt + إنشاء JWT
  - api/deps.py        → get_current_user / get_current_active_superuser
  - api/routes/login.py + users.py → مسارات الدخول/التسجيل
مع تكييفها للعمل فوق SQLAlchemy Async (asyncpg) الموجود في src/database.py،
وفق طلب المهمة: python-jose + passlib (بدل PyJWT في القالب).
"""

import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError
from sqlalchemy import Boolean, Column, String, func, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Base, async_session, engine

logger = logging.getLogger(__name__)

# --- إعدادات JWT من البيئة (مثل القالب: changethis مع تحذير، لا فشل عند الإقلاع) ---
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 7))
ALGORITHM = "HS256"
DEFAULT_SECRET = ("", "change_me", "change_me_jwt_secret")

if not JWT_SECRET_KEY or JWT_SECRET_KEY in DEFAULT_SECRET:
    # السر الافتراضي خطر — نستبدله بسر عشوائي مؤقت (الجلسات تنقطع عند إعادة التشغيل)
    logger.warning(
        "⚠️ JWT_SECRET_KEY غير مضبوط (أو مبدل بالافتراضي) — وُلّد سر عشوائي مؤقت. "
        "اضبط JWT_SECRET_KEY في .env"
    )
    JWT_SECRET_KEY = secrets.token_hex(32)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 password flow — الرابط يظهر في /docs ويتوافق مع POST /api/auth/login
# auto_error=False: لنجلب التوكن بأنفسنا للسماح أيضاً بكوكي auth_cookie (نمط القالب)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# اسم الكوكي المصادق عليه (نفس AUTH_COOKIE في الواجهة)
AUTH_COOKIE_NAME = "auth_cookie"


# ----------------------------- Models --------------------------------------


class User(Base):
    """نموذج المستخدم (مقلّد من backend/app/models.py في القالب)"""

    __tablename__ = "users"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    is_superuser = Column(Boolean, nullable=False, default=False)
    full_name = Column(String(255), nullable=True)


class UserRegister(BaseModel):
    """بيانات التسجيل (نفس قيود القالب: كلمة مرور 6-40 حرفاً)"""

    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=6, max_length=40)
    full_name: str | None = Field(default=None, max_length=255)


class FirstAdminCreate(BaseModel):
    """إنشاء أول مستخدم admin عبر المسار البذري"""

    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=6, max_length=40)


class Token(BaseModel):
    """JWT — نفس شكل القالب: توكن + انتهاء مطلق (Unix timestamp)"""

    access_token: str
    expires: int


class TokenPayload(BaseModel):
    sub: str | None = None


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    is_active: bool
    is_superuser: bool
    full_name: str | None


class Message(BaseModel):
    message: str


# ----------------------------- Security ------------------------------------


def create_access_token(subject: str | Any, expires_delta: timedelta) -> str:
    """إنشاء JWT — مطابق لـ backend/app/core/security.py في القالب"""
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {"exp": expire, "sub": str(subject)}
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


# ----------------------------- Dependencies --------------------------------


async def get_db() -> AsyncIterator[AsyncSession]:
    """جلسة قاعدة بيانات لكل طلب"""
    async with async_session() as session:
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(User))
    return int(result.scalar_one())


async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    """التحقق من بيانات الدخول — مثل crud.authenticate في القالب"""
    user = await get_user_by_email(db, email)
    if not user or not user.hashed_password:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def get_current_user(
    db: DbDep,
    bearer_token: Annotated[str | None, Depends(oauth2_scheme)],
    request: Request,
) -> User:
    """حارس المصادقة — مطابق لـ backend/app/api/deps.py في القالب.

    يقبل التوكن من رأس Authorization: Bearer (curl/البرمجيات)
    أو من كوكي auth_cookie (الواجهة — نمط HttpOnly cookie في القالب).
    """
    token = bearer_token or request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="غير مصادق"
        )
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        token_data = TokenPayload(**payload)
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="تعذّر التحقق من بيانات الاعتماد",
        )
    try:
        user_id = uuid.UUID(token_data.sub) if token_data.sub else None
    except ValueError:
        user_id = None
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="توكن غير صالح"
        )
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="مستخدم غير مفعّل")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_active_superuser(current_user: CurrentUser) -> User:
    """حارس صلاحيات المشرف (نمط القالب)"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="المستخدم لا يملك صلاحيات كافية",
        )
    return current_user


SuperUser = Annotated[User, Depends(get_current_active_superuser)]


async def init_auth_db() -> None:
    """إنشاء جدول users في نفس قاعدة PostgreSQL الموجودة (idempotent)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ----------------------------- Router --------------------------------------

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=201, response_model=UserPublic)
async def register(user_in: UserRegister, db: DbDep) -> User:
    """تسجيل مستخدم جديد — أول مستخدم في النظام يصبح admin تلقائياً (bootstrap)"""
    await init_auth_db()
    if await get_user_by_email(db, user_in.email):
        raise HTTPException(
            status_code=400, detail="يوجد مستخدم بهذا البريد الإلكتروني"
        )
    is_first_user = await get_user_count(db) == 0
    user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        is_superuser=is_first_user,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info(f"👤 مستخدم جديد: {user.email} (admin={user.is_superuser})")
    return user


@router.post("/login", response_model=Token)
async def login_access_token(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbDep
) -> Token:
    """دخول OAuth2 Password Flow — حقل username يحمل البريد الإلكتروني"""
    user = await authenticate(db, form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=401, detail="بريد إلكتروني أو كلمة مرور غير صحيحة"
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="مستخدم غير مفعّل")
    expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    token = create_access_token(str(user.id), expires_delta)
    expires = int((datetime.now(timezone.utc) + expires_delta).timestamp())
    return Token(access_token=token, expires=expires)


@router.post("/test-token", response_model=UserPublic)
async def test_token(current_user: CurrentUser) -> User:
    """فحص صلاحية التوكن — يعيد بيانات المستخدم الحالي"""
    return current_user


@router.post("/logout", response_model=Message)
async def logout() -> Message:
    """تسجيل الخروج — حذف الكوكي يتم في الواجهة (نمط القالب)"""
    return Message(message="تم تسجيل الخروج")


@router.post("/create-admin", status_code=201, response_model=UserPublic)
async def create_admin(admin_in: FirstAdminCreate, db: DbDep) -> User:
    """بذرة أول admin — مسموح فقط عندما لا يوجد أي مستخدم في النظام"""
    await init_auth_db()
    if await get_user_count(db) > 0:
        raise HTTPException(
            status_code=403, detail="غير مسموح — يوجد مستخدمون بالفعل"
        )
    if await get_user_by_email(db, admin_in.email):
        raise HTTPException(status_code=400, detail="البريد مستخدم مسبقاً")
    user = User(
        email=admin_in.email,
        hashed_password=get_password_hash(admin_in.password),
        is_superuser=True,
        full_name="Admin",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info(f"👑 تم إنشاء أول admin: {user.email}")
    return user


# ------------------- مسارات بديلة (مطلوبة في المواصفة) -------------------
# تبقى مسارات /api/auth/* قائمة كما هي — هذه مجرد أسماء أسهل:
alias_router = APIRouter(tags=["auth"])


@alias_router.post("/api/login", response_model=Token)
async def login_alias(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbDep
) -> Token:
    """POST /api/login — اختصار لـ POST /api/auth/login (نفس المنطق تماماً)"""
    return await login_access_token(form, db)


@alias_router.get("/api/me", response_model=UserPublic)
async def me_alias(current_user: CurrentUser) -> User:
    """GET /api/me — بيانات المستخدم الحالي (بديل GET لـ POST /api/auth/test-token)"""
    return current_user
