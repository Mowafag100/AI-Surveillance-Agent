from datetime import datetime, timedelta
import io
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Annotated, Any, Literal

import arabic_reshaper
import cv2
import numpy as np
from bidi.algorithm import get_display
from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image as _RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select

from src.auth import CurrentUser, DbDep, SuperUser, alias_router, router as auth_router
from src.config import CONFIG_JSON_PATH, Config, _SETTINGS, load_json_config
from src.database import Employee, init_employees
from src.face_recognizer import extract_face_encoding

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
EVENTS_FILE = BASE_DIR / "logs" / "events.jsonl"
ALERTS_DIR = (BASE_DIR / "alerts").resolve()
CAMERA_HEALTH_FILE = BASE_DIR / "logs" / "camera_health.json"
ACKNOWLEDGED_FILE = BASE_DIR / "logs" / "acknowledged.json"

# يحمي كتابة logs/acknowledged.json من تزامن الطلبات
_ack_lock = threading.Lock()

app = FastAPI(title="AI Surveillance API", version="1.0")

app.include_router(auth_router)
app.include_router(alias_router)


class ChatRequest(BaseModel):
    """جسد POST /api/chat — سؤال المستخدم النصّي (حد أقصى حمايًا حمولة الخادم)"""
    message: str = Field(min_length=1, max_length=2000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _read_events() -> list[dict[str, Any]]:
    """قراءة logs/events.jsonl وإسناد id تسلسلي = رقم السطر (1-based)."""
    if not EVENTS_FILE.is_file():
        return []
    events: list[dict[str, Any]] = []
    try:
        with EVENTS_FILE.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    event.setdefault("id", line_no)
                    events.append(event)
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"تعذّر قراءة سجل الأحداث: {exc}"
        ) from exc
    return events


def _find_event(event_id: int) -> dict[str, Any] | None:
    for event in _read_events():
        if event.get("id") == event_id:
            return event
    return None


@app.get("/api/health")
async def health() -> dict[str, str]:
    """فحوصاة الخادم"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.post("/api/chat")
async def chat_endpoint(payload: ChatRequest, current_user: CurrentUser) -> dict[str, str]:
    """المساعد الذكي للمحادثة — محمي بـ JWT (Bearer أو كوكي auth_cookie).

    يجيب من بيانات الأحداث الحقيقية في logs/events.jsonl حصراً:
    منطق src/chat.py لا يقرأ config.json/.env ولا يلمس أي توكن أو كلمة
    مرور، وسياق النموذج (LLM) يمرّ عبر قائمة بيضاء لحقول الأحداث فقط."""
    from src.chat import answer_question  # استيراد متأخر — يبقى التحميل خفيفاً

    try:
        result = answer_question(payload.message)
    except Exception as exc:
        logger.error(f"❌ فشل المساعد الذكي: {exc}")
        raise HTTPException(status_code=500, detail="تعذّر توليد الرد") from exc
    logger.info(f"💬 مساعد ذكي [{result.get('provider')}]: {payload.message[:80]}")
    return {"reply": result.get("reply", ""), "provider": result.get("provider", "stats")}


def _mask_secret(value: Any) -> str:
    """إخفاء التوكن جزئياً: أول 4 أحرف فقط"""
    text = str(value) if value else ""
    return f"{text[:4]}****" if text else ""


def _mask_settings() -> dict[str, Any]:
    """عرض الإعدادات الحالية مع إخفاء التوكنات"""
    masked: dict[str, Any] = {}
    for attr in _SETTINGS:
        value = getattr(Config, attr)
        if attr in ("TELEGRAM_BOT_TOKEN", "SMTP_PASSWORD"):
            masked[attr] = _mask_secret(value)
        else:
            masked[attr] = value
    return masked


def _read_camera_health() -> dict[str, Any]:
    """قراءة logs/camera_health.json المكتوب من حاوية agent — {} إن لم يوجد"""
    try:
        if CAMERA_HEALTH_FILE.is_file():
            with CAMERA_HEALTH_FILE.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
                return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _read_acknowledged() -> dict[str, Any]:
    """قراءة logs/acknowledged.json — {event_id: {acknowledged, ack_by, ack_time}}"""
    try:
        if ACKNOWLEDGED_FILE.is_file():
            with ACKNOWLEDGED_FILE.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
                return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _write_acknowledged_atomic(acks: dict[str, Any]) -> None:
    """كتابة logs/acknowledged.json دريّة (tmp + replace)"""
    ACKNOWLEDGED_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = ACKNOWLEDGED_FILE.with_suffix(".json.tmp")
    with _ack_lock:
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(acks, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, ACKNOWLEDGED_FILE)


def _write_json_config_atomic(overrides: dict[str, Any]) -> None:
    """كتابة config.json: ذرّية (tmp + replace) محلياً، وكتابة مباشرة داخل
    الحاوية لأن config.json مُوحَّد مع ملف واحد من المضيف (لا يمكن استبدال
    نقطة الحجب mountpoint — خطأ errno 16 Device or resource busy)."""
    import tempfile

    CONFIG_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=CONFIG_JSON_PATH.parent,
            prefix="config.json.",
            suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
                json.dump(overrides, handle, indent=2, ensure_ascii=False)
            os.replace(tmp_path, CONFIG_JSON_PATH)
        except OSError:
            Path(tmp_path).unlink(missing_ok=True)
            raise
    except OSError:
        # الوضع داخل الحاوية: كتابة مباشرة إذا كانت الملف (نفسنا file bind mount)
        with CONFIG_JSON_PATH.open("w", encoding="utf-8") as handle:
            json.dump(overrides, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())


@app.post("/api/settings")
async def update_settings(payload: dict[str, Any], admin_user: SuperUser) -> dict[str, Any]:
    """تحديث config.json — يتطلب مستخدماً مفعّلاً بصلاحيات المشرف (JWT)"""
    # قبول المفاتيح المعروفة فقط، والتحقق من صحة الأنواع قبل الحفظ
    allowed = set(_SETTINGS)
    unknown = [key for key in payload if key not in allowed]
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"مفاتيح غير معروفة: {', '.join(sorted(unknown))}"
        )

    # التحقق من صحة القيم (محاكاة التحويل دون تعديل الحالة)
    for key, value in payload.items():
        parser = _SETTINGS[key][1]
        try:
            parser(value)
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=400, detail=f"قيمة غير صالحة لـ {key}: {value!r}"
            ) from exc

    # دمج التعديلات فوق الإعدادات الموجودة (الحفاظ على المفاتيح الأخرى)
    current = load_json_config()
    current.update(payload)

    try:
        _write_json_config_atomic(current)
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"تعذّر كتابة config.json: {exc}"
        ) from exc

    # تحميل فوري للعملية الحالية (حاوية API)، والوكيل يلتقطها عبر Hot Reload
    Config.reload()
    return {"status": "updated", "keys": sorted(payload)}


# ------------------- Employees (التعرف على الوجوه) -------------------

# أقصى حجم صورة لموظف (10 ميجابايت) — حماية من الذاكرة/أعباء الرفع
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@app.post("/api/employees", status_code=201)
async def create_employee(
    admin_user: SuperUser,
    db: DbDep,
    name: Annotated[str, Form(min_length=1, max_length=255)],
    role: Annotated[str, Form()] = "",
    photo: Annotated[UploadFile, File()] = None,
) -> dict[str, Any]:
    """تسجيل موظف — استخراج بصمة الوجه من الصورة المرفوعة وحفظها (مشرف فقط)"""
    if photo is None:
        raise HTTPException(status_code=400, detail="صورة الوجه مطلوبة")
    await init_employees()
    data = await photo.read(_MAX_UPLOAD_BYTES + 1)
    if not data or len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="الصورة مفقودة أو أكبر من 10 ميغابايت")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="صيغة الصورة غير مدعومة")
    encoding = extract_face_encoding(img)
    if encoding is None:
        raise HTTPException(
            status_code=400,
            detail="لم يُكتشف وجه واضح — استخدم صورة مقربة وواضحة للوجه"
        )
    employee = Employee(
        name=name.strip(),
        role=role.strip() or None,
        face_encoding=json.dumps(encoding),
    )
    db.add(employee)
    await db.commit()
    await db.refresh(employee)
    logger.info(f"🧑‍💼 موظف جديد: {employee.name} (id={employee.id})")
    return {"id": employee.id, "name": employee.name, "role": employee.role or ""}


@app.get("/api/employees")
async def list_employees(
    current_user: CurrentUser, db: DbDep
) -> list[dict[str, Any]]:
    """قائمة الموظفين (id/name/role فقط — البصمة غير مكشوفة خارجياً)"""
    await init_employees()
    rows = (await db.execute(select(Employee).order_by(Employee.id))).scalars().all()
    return [{"id": e.id, "name": e.name, "role": e.role or ""} for e in rows]


@app.delete("/api/employees/{employee_id}", status_code=204)
async def delete_employee(
    employee_id: int, admin_user: SuperUser, db: DbDep
) -> Response:
    """حذف موظف — يمحو بصمته من التعرف ضمن ثوانٍ (مشرف فقط)"""
    await init_employees()
    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="الموظف غير موجود")
    await db.delete(employee)
    await db.commit()
    logger.info(f"🗑️ حُذف الموظف {employee.name} (id={employee_id})")
    return Response(status_code=204)


# ------------------- Read endpoints -------------------


@app.get("/api/settings")
async def get_settings(current_user: CurrentUser) -> dict[str, Any]:
    """الإعدادات الحالية مع إخفاء التوكن جزئياً — تتطلب مصادقة"""
    # تعديلات من خارج عملية POST نفسها (يدوياً/حاوية أخرى) تُلتقط هنا
    Config.ensure_fresh()
    return _mask_settings()


@app.get("/api/events")
async def get_events(
    limit: int = Query(default=50, ge=1, le=1000),
    camera_id: int | None = Query(default=None),
    event_type: str | None = Query(default=None),
    acknowledged: bool | None = Query(default=None),
) -> list[dict[str, Any]]:
    """جلب الأحداث الأخيرة مع تصفية اختيارية:
    camera_id / event_type / acknowledged (true أو false — غياب المعامل = الكل)"""
    events = _read_events()
    # دمج حالة التأكيد من logs/acknowledged.json
    acks = _read_acknowledged()
    for event in events:
        ack = acks.get(str(event.get("id")))
        if isinstance(ack, dict):
            event["acknowledged"] = bool(ack.get("acknowledged"))
            event["ack_by"] = ack.get("ack_by")
            event["ack_time"] = ack.get("ack_time")
        else:
            event["acknowledged"] = False
    if camera_id is not None:
        events = [
            e
            for e in events
            if e.get("camera_id") == camera_id
            or (
                isinstance(e.get("details"), dict)
                and e["details"].get("camera_id") == camera_id
            )
        ]
    if event_type is not None:
        events = [e for e in events if e.get("event") == event_type]
    if acknowledged is not None:
        events = [e for e in events if bool(e.get("acknowledged")) is acknowledged]
    return events[-limit:]


@app.post("/api/events/{event_id}/acknowledge")
async def acknowledge_event(event_id: int, admin_user: SuperUser) -> dict[str, Any]:
    """تأكيد مراجعة حدث (يتطلب JWT مشرف) — يسجّل في logs/acknowledged.json:
    {id: {acknowledged: true, ack_by: email, ack_time: iso}}"""
    event = _find_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    acks = _read_acknowledged()
    now_iso = datetime.now().isoformat()
    acks[str(event_id)] = {
        "acknowledged": True,
        "ack_by": admin_user.email,
        "ack_time": now_iso,
    }
    try:
        _write_acknowledged_atomic(acks)
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"تعذّر كتابة ملف التأكيد: {exc}"
        ) from exc

    return {
        "id": event_id,
        "acknowledged": True,
        "ack_by": admin_user.email,
        "ack_time": now_iso,
    }


@app.get("/api/events/{event_id}")
async def get_event(event_id: int) -> dict[str, Any]:
    """تفاصيل حدث واحد"""
    event = _find_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.get("/api/events/{event_id}/image")
async def get_event_image(event_id: int) -> FileResponse:
    """تحميل صورة الحدث (مؤمَّن داخل alerts/)"""
    event = _find_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    image_value = event.get("image")
    if not isinstance(image_value, str) or not image_value:
        raise HTTPException(status_code=404, detail="Event has no image")

    candidate = (ALERTS_DIR / Path(image_value).name).resolve()
    if not candidate.is_relative_to(ALERTS_DIR) or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(candidate)


@app.get("/api/cameras")
async def get_cameras() -> list[dict[str, Any]]:
    """القائمة الحقيقية من config.json (مع توافق خلفي نحو CAMERA_URL القديم).
    status يُحسب من logs/camera_health.json عند توفره (online/offline/unknown)"""
    Config.ensure_fresh()
    health_data = _read_camera_health()
    health_cameras = (
        health_data.get("cameras") if isinstance(health_data.get("cameras"), dict) else {}
    )
    return [
        {
            "id": int(camera.get("id", index + 1)),
            "name": str(camera.get("name") or f"Camera {index + 1}"),
            "status": _camera_status(int(camera.get("id", index + 1)), health_cameras),
            "url": str(camera.get("url") or ""),
        }
        for index, camera in enumerate(Config.get_cameras())
    ]


def _camera_status(camera_id: int, health_cameras: dict[str, Any]) -> str:
    """حالة الكاميرا من خطوط بيانات الصحة — unknown إن لم يصل أي تقرير بعد"""
    entry = health_cameras.get(str(camera_id))
    if isinstance(entry, dict) and entry.get("status") in ("online", "offline"):
        return str(entry["status"])
    return "unknown"


@app.get("/api/cameras/health")
async def get_cameras_health() -> dict[str, Any]:
    """حالة صحة الكاميرات من تقارير حاوية agent (logs/camera_health.json):
    online/offline لكل كاميرا + آخر وقت استلام إطار (last_seen)."""
    health_data = _read_camera_health()
    cameras_section = health_data.get("cameras")
    cameras_section = cameras_section if isinstance(cameras_section, dict) else {}

    cameras: list[dict[str, Any]] = []
    for camera_id, entry in sorted(cameras_section.items(), key=lambda kv: int(kv[0])):
        if not isinstance(entry, dict):
            continue
        try:
            numeric_id = int(camera_id)
        except (TypeError, ValueError):
            continue
        cameras.append(
            {
                "id": numeric_id,
                "name": str(entry.get("name") or f"Camera {numeric_id}"),
                "url": str(entry.get("url") or ""),
                "status": "online" if entry.get("status") == "online" else "offline",
                "last_seen": entry.get("last_seen"),
            }
        )
    return {
        "timestamp": health_data.get("timestamp"),
        "timeout_sec": health_data.get("timeout_sec"),
        "cameras": cameras,
    }


# ------------------- Live View (MJPEG Streaming) -------------------

# تحديد الحدود (boundary) لرسائل multipart/x-mixed-replace
_STREAM_BOUNDARY = "frame"
_STREAM_HEADER = (
    f"--{_STREAM_BOUNDARY}\r\nContent-Type: image/jpeg\r\n\r\n".encode()
)


async def _stream_generator(
    request: Request,
    url: str,
    jpeg_quality: int,
    max_fps: int,
    max_failures: int = 30,
    connect_attempts: int = 10,
):
    """مولد بث async يفتح VideoCapture ويبث إطارات JPEG عبر multipart.

    لماذا مولد async بدل المتزامن؟
    - القراءات الحاجبة (VideoCapture/read/imencode) تذهب إلى asyncio.to_thread
      فلا تُجمّد حلقة الأحداث (طلبات أخرى مثل /api/cameras/health تبقى سريعة).
    - uvicorn (spec_version 2.3) يُلغي مولد البث عبر CancelledError عند قطع
      العميل (listen_for_disconnect بالتوازي في StreamingResponse)، فتعمل كتلة
      finally حتماً وتحرر الكاميرا (cap.release) دون انتظار GC. للاطمئنان أكثر
      نستقصي request.is_disconnected في كل دورة — فبعد فقد العميل تبقى كتابة
      uvicorn صامتة ولن تُلغي البث تلقائياً.
    - البث للعرض فقط ولا تمرَّر الإطارات على نموذج YOLO (تخفيف الحمل).
    """
    import asyncio

    import cv2

    cap: Any = None
    failures = 0
    frame_interval = 1.0 / max_fps if max_fps > 0 else 0.0

    try:
        while True:
            # فحص انقطاع العميل أولاً — uvicorn يواصل "الكتابة" بلا فائدة بعد الفقد
            if await request.is_disconnected():
                logger.info("ℹ️ قطع عميل مشاهد البث — تحرير الكاميرا")
                break

            if cap is None:
                cap = await asyncio.to_thread(cv2.VideoCapture, url)
                if not (cap and cap.isOpened()):
                    cap.release()
                    cap = None
                    failures += 1
                    if failures >= connect_attempts:
                        logger.warning(
                            f"⚠️ البث انتهى — تعذر فتح الكاميرا ({url})"
                        )
                        break
                    await asyncio.sleep(0.5)
                    continue

            ret, frame = await asyncio.to_thread(cap.read)
            if not ret:
                failures += 1
                cap.release()
                cap = None
                if failures >= max_failures:
                    logger.warning(
                        f"⚠️ البث انتهى — {failures} قراءة فاشلة متتالية ({url})"
                    )
                    break
                continue

            failures = 0

            # تصغير حجم الإطار كالوكيل (يقلل النقل على الشبكة)
            if frame.shape[0] > 480:
                frame = cv2.resize(frame, (640, 480))

            # ترميز JPEG أيضاً في الخلفية
            ok, buf = await asyncio.to_thread(
                cv2.imencode, ".jpg", frame, [
                    cv2.IMWRITE_JPEG_QUALITY, jpeg_quality
                ]
            )
            if ok:
                yield _STREAM_HEADER + buf.tobytes() + b"\r\n"

            await asyncio.sleep(frame_interval)
    except (GeneratorExit, asyncio.CancelledError):
        # انقطاع العميل (إلغاء الاستجابة) — تحرير الموارد في finally ثم إعادة الرفع
        logger.info("ℹ️ قطع عميل مشاهد البث — تحرير الكاميرا (إلغاء)")
        raise
    finally:
        if cap is not None:
            # استدعاء sync قصير — cv2.release سريع (إلغاء لا يعمل داخل finally)
            cap.release()
            logger.debug("ℹ️ تم تحرير VideoCapture للكاميرا")


@app.get("/api/cameras/{camera_id}/stream")
async def stream_camera(
    request: Request,
    camera_id: int,
    current_user: CurrentUser,
    q: int = Query(default=70, ge=10, le=100, description="جودة JPEG"),
    fps: int = Query(default=10, ge=1, le=30, description="أقصى إطارات بالثانية"),
) -> StreamingResponse:
    """البث المباشر MJPEG للكاميرا — يتطلب JWT (Bearer أو كوكي auth_cookie).

    بث مستقل عن خط معالجة YOLO: يفتح اتصالاً مباشراً بالكاميرا
    ويلقط إطارات JPEG (عرض فقط — بلا استدلال لتخفيف الحمل)."""
    Config.ensure_fresh()
    camera = next(
        (c for c in Config.get_cameras() if int(c.get("id", -1)) == camera_id),
        None,
    )
    if camera is None or not str(camera.get("url") or "").strip():
        raise HTTPException(status_code=404, detail="Camera not found")

    return StreamingResponse(
        _stream_generator(
            request=request,
            url=str(camera["url"]),
            jpeg_quality=q,
            max_fps=fps,
        ),
        media_type=f"multipart/x-mixed-replace; boundary={_STREAM_BOUNDARY}",
        headers={
            # بلا ترويسات نصية عربية: ترويسات HTTP ترميزها latin-1 حصراً
            # (اسم كاميرا عربي في X-Camera-Name كان يسبب UnicodeEncodeError وخطأ 500)
            "Cache-Control": "no-store, no-transform",
        },
    )


# ------------------- تقرير PDF أحادي اللغة (اليوم/الأسبوع) -------------------

# خط النظام العربي الجاهز (DejaVu من fonts-dejavu-core في صورة Docker) —
# مسار بديل عبر متغير PDF_ARABIC_FONT لمن يحبّ خط عربي آخر
_PDF_FONT_CANDIDATES = (
    Path(os.environ.get("PDF_ARABIC_FONT") or "/__unset__"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf"),
)
_PDF_FONT_NAME = "DejaVuPdf"
_pdf_fonts_ready = False
_pdf_fonts_lock = threading.Lock()

# كل نص التقرير بلغة واحدة (طلب صريح بلا تقرير مختلط) — en يطابق المفاتيح
_PDF_LABELS: dict[str, dict[str, str]] = {
    "ar": {
        "title": "تقرير المراقبة الذكية",
        "subtitle": "الفترة: {period} — تاريخ التصدير: {date}",
        "period_day": "اليوم",
        "period_week": "آخر 7 أيام",
        "stat_total": "الإجمالي",
        "ev_intrusion": "تسلل",
        "ev_fall": "سقوط",
        "ev_fight": "شجار",
        "ev_running": "جري",
        "ev_loitering": "توقّف مشبوه",
        "ev_employee_entry": "دخول موظف",
        "showing_note": "يُعرض في الجدول آخر {shown} من {total} حدثاً في الفترة",
        "section_latest": "أحدث الأحداث",
        "no_events": "لا أحداث مسجلة خلال هذه الفترة",
        "h_time": "الوقت",
        "h_camera": "الكاميرا",
        "h_event": "نوع الحدث",
        "h_employee": "الموظف",
        "h_snapshot": "اللقطة",
        "unknown_camera": "كاميرا {camera_id}",
        "page": "صفحة {number}",
        "generated": "وُلِّد في {date}",
    },
    "en": {
        "title": "AI Surveillance Report",
        "subtitle": "Period: {period} — Generated on: {date}",
        "period_day": "Today",
        "period_week": "Last 7 days",
        "stat_total": "Total",
        "ev_intrusion": "Intrusion",
        "ev_fall": "Fall",
        "ev_fight": "Fight",
        "ev_running": "Running",
        "ev_loitering": "Loitering",
        "ev_employee_entry": "Employee Entry",
        "showing_note": "Table shows the latest {shown} of {total} events in the period",
        "section_latest": "Latest Events",
        "no_events": "No events registered in this period",
        "h_time": "Time",
        "h_camera": "Camera",
        "h_event": "Event",
        "h_employee": "Employee",
        "h_snapshot": "Snapshot",
        "unknown_camera": "Camera {camera_id}",
        "page": "Page {number}",
        "generated": "Generated at {date}",
    },
}


def ar(text: Any) -> str:
    """تشكيل نص للطباعة في reportlab: ربط حروف العربية + إعادة ترتيب RTL

    reportlab يرسم محارف متفرقة — بدون التشكيل (arabic_reshaper) والترتيب
    (python-bidi) تظهر العربية مقطّعة وباتجاه معكوس. على النصوص الآسيوية
    (إنجليزي/أرقام/شرطات نطاق) يعيد الحرف نفسه، فاستخدامه الآمن على أي قيمة بيانات."""
    return get_display(arabic_reshaper.reshape(str(text)))


def _ensure_pdf_font() -> None:
    """تسجيل خط TTF عربي من النظام مرة واحدة (الطلبات تصل متزامنة)"""
    global _pdf_fonts_ready
    with _pdf_fonts_lock:
        if _pdf_fonts_ready:
            return
        font_path = next((p for p in _PDF_FONT_CANDIDATES if p.is_file()), None)
        if font_path is None:
            raise HTTPException(
                status_code=500,
                detail=(
                    "لا يوجد خط نظامي يدعم العربية — ثبّت fonts-dejavu-core "
                    "أو عيّن PDF_ARABIC_FONT لمسار ملف TTF عربي"
                ),
            )
        pdfmetrics.registerFont(TTFont(_PDF_FONT_NAME, str(font_path)))
        _pdf_fonts_ready = True


def _pdf_thumbnail(event: dict[str, Any]) -> Any | None:
    """مصغرة لقطة الحدث (مسار alerts من event.image) — None إن فُقدت الصورة"""
    image_rel = event.get("image")
    if not isinstance(image_rel, str) or not image_rel:
        return None
    frame = cv2.imread(str(Path(image_rel)))
    if frame is None:
        return None
    height, width = frame.shape[:2]
    if width <= 0 or height <= 0:
        return None
    scale = min(64.0 / width, 48.0 / height)  # مقاس نقطة الجدول (pt)
    resized = cv2.resize(
        frame, (max(1, int(width * scale)), max(1, int(height * scale)))
    )
    ok, buf = cv2.imencode(".jpg", resized)
    if not ok:
        return None
    thumb_height = 40.0 * resized.shape[0] / max(1, resized.shape[1])
    return _RLImage(
        io.BytesIO(buf.tobytes()), width=40.0, height=thumb_height
    )


@app.get("/api/reports/pdf")
async def export_pdf_report(
    admin_user: SuperUser,
    period: Annotated[Literal["day", "week"], Query()] = "day",
    lang: Annotated[Literal["ar", "en"], Query()] = "ar",
) -> Response:
    """تقرير PDF بلغة واحدة `?lang=ar` أو `?lang=en` (افتراضي عربي) مع
    `?period=day|week` — إحصائيات مطابقة حرفياً لصفوف الجدول (تُحسب من القائمة
    نفسها المصغّرة) + صور مصغرة، وفلترة تقويمية (اليوم من منتصف الليل) — JWT مشرف"""
    _ensure_pdf_font()
    labels = _PDF_LABELS["en" if lang == "en" else "ar"]

    now = datetime.now()
    if period == "day":
        # "اليوم" التقويمي (من منتصف الليل) — كان "آخر 24 ساعة" فيубликов
        # أرقام مختلفة بين الملخص والنافذة الدال/الحكم، وهو سبب التناقض
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        # آخر 7 أيام تقويمية شاملة اليوم الحالي
        start = (now - timedelta(days=6)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    # مصدر حقيقة وحيد: قائمة أحداث الفترة N ← الجدول آخر K = min(10, N)
    events_in_range: list[dict[str, Any]] = []
    for event in _read_events():
        timestamp = event.get("timestamp")
        if not isinstance(timestamp, str):
            continue
        try:
            event_time = datetime.fromisoformat(timestamp)
        except ValueError:
            continue
        if event_time < start:
            continue
        events_in_range.append(event)
    # ترتيب تصاعدي حتكون الأحدث أسفل الجدول (قراءة طبيعية) ثم آخر 10
    events_shown = sorted(
        events_in_range, key=lambda e: e.get("timestamp", "")
    )[-10:]
    total_in_period = len(events_in_range)
    event_counter: dict[str, int] = {}
    for event in events_shown:
        event_type = str(event.get("event", ""))
        event_counter[event_type] = event_counter.get(event_type, 0) + 1

    title_style = ParagraphStyle(
        name="ReportTitle", fontName=_PDF_FONT_NAME, fontSize=18,
        leading=24, alignment=TA_CENTER, textColor=colors.HexColor("#111827"),
    )
    sub_style = ParagraphStyle(
        name="ReportSub", fontName=_PDF_FONT_NAME, fontSize=9, leading=13,
        alignment=TA_CENTER, textColor=colors.HexColor("#4B5563"),
    )
    section_style = ParagraphStyle(
        name="ReportSection", fontName=_PDF_FONT_NAME, fontSize=12, leading=16,
        alignment=TA_CENTER if lang == "en" else TA_RIGHT,
        textColor=colors.HexColor("#111827"),
        spaceBefore=12, spaceAfter=6,
    )

    period_label = labels["period_day"] if period == "day" else labels["period_week"]
    subtitle = labels["subtitle"].format(
        period=period_label,
        # "/" لا="-" (الشرطة تُقلب الأرقام داخل bidi) — تاريخ بصيغة ق_LAYER.preferences
        date=now.strftime("%d/%m/%Y"),
    )
    story: list[Any] = [
        Paragraph(ar(labels["title"]), title_style),
        Spacer(1, 4),
        Paragraph(ar(subtitle), sub_style),
        Spacer(1, 10),
    ]

    # ---- الإحصائيات: تُحسب من events_shown نفسه فتطابق الجدول دائماً ----
    stat_columns = [
        (labels["stat_total"], len(events_shown), colors.HexColor("#E5E7EB")),
        (labels["ev_intrusion"], event_counter.get("intrusion", 0), colors.HexColor("#DBEAFE")),
        (labels["ev_fall"], event_counter.get("fall", 0), colors.HexColor("#FEE2E2")),
        (labels["ev_running"], event_counter.get("running", 0), colors.HexColor("#FEF9C3")),
        (labels["ev_loitering"], event_counter.get("loitering", 0), colors.HexColor("#FFEDD5")),
        (labels["ev_fight"], event_counter.get("fight", 0), colors.HexColor("#FEF3C7")),
        (labels["ev_employee_entry"], event_counter.get("employee_entry", 0), colors.HexColor("#D1FAE5")),
    ]
    stat_table = Table(
        [
            [ar(label) for label, _, _ in stat_columns],
            [str(value) for _, value, _ in stat_columns],
        ],
        colWidths=[2.55 * cm] * len(stat_columns),
        rowHeights=[0.7 * cm, 1.0 * cm],
    )
    stat_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _PDF_FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("FONTSIZE", (0, 1), (-1, 1), 16),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#9CA3AF")),
                *[
                    ("BACKGROUND", (index, 0), (index, 1), bg)
                    for index, (_, _, bg) in enumerate(stat_columns)
                ],
            ]
        )
    )
    story.append(stat_table)
    if total_in_period > len(events_shown):
        # التوضيح يمنع "التناقض" الظاهري: مجموع الملخص = صفوف الجدول (K)
        story.append(
            Spacer(1, 6),
        )
        story.append(
            Paragraph(
                ar(
                    labels["showing_note"].format(
                        shown=len(events_shown), total=total_in_period
                    )
                ),
                sub_style,
            )
        )

    # ---- جدول الأحداث مع لقطات مصغرة ----
    story.append(Paragraph(ar(labels["section_latest"]), section_style))
    if not events_shown:
        story.append(Paragraph(ar(labels["no_events"]), sub_style))
    else:
        rows: list[list[Any]] = [
            [ar(labels[key]) for key in
             ("h_time", "h_camera", "h_event", "h_employee", "h_snapshot")]
        ]
        for event in events_shown:
            details = event.get("details") or {}
            event_type = str(event.get("event", ""))
            raw_timestamp = str(event.get("timestamp", ""))
            try:
                time_format = "%H:%M:%S" if period == "day" else "%Y-%m-%d %H:%M"
                shown_time = datetime.fromisoformat(raw_timestamp).strftime(time_format)
            except ValueError:
                shown_time = raw_timestamp
            employee_label = "—"
            if event_type == "employee_entry" and details.get("employee_name"):
                employee_label = str(details["employee_name"])
                if details.get("role"):
                    employee_label += f" ({details['role']})"
            camera_label = details.get("camera_name")
            if not camera_label:
                camera_label = labels["unknown_camera"].format(
                    camera_id=str(details.get("camera_id", "؟"))
                )
            event_label = labels.get(f"ev_{event_type}", event_type or "؟")
            rows.append(
                [
                    shown_time,
                    ar(camera_label),        # اسم كاميرا/موظف عربي محتمل — يُشكّل دائماً
                    ar(event_label),
                    ar(employee_label),
                    _pdf_thumbnail(event) or ar("—"),
                ]
            )
        events_table = Table(
            rows,
            colWidths=[3.0 * cm, 4.3 * cm, 3.0 * cm, 4.7 * cm, 3.0 * cm],
        )
        events_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), _PDF_FONT_NAME),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#9CA3AF")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (4, 1), (4, -1), "CENTER"),
                    *[
                        ("BACKGROUND", (0, row), (-1, row), colors.HexColor("#F9FAFB"))
                        for row in range(2, len(rows), 2)
                    ],
                ]
            )
        )
        story.append(events_table)

    # ---- تذييل الصفحات: رقم الصفحة + سطر التوليد بلغة التقرير ----
    def _pdf_page_footer(canvas_obj: Any, doc: Any) -> None:
        canvas_obj.saveState()
        canvas_obj.setFont(_PDF_FONT_NAME, 8)
        canvas_obj.setFillColor(colors.HexColor("#6B7280"))
        canvas_obj.drawRightString(
            A4[0] - 1.5 * cm,
            0.8 * cm,
            ar(labels["page"].format(number=canvas_obj.getPageNumber())),
        )
        canvas_obj.drawCentredString(
            A4[0] / 2,
            0.8 * cm,
            ar(labels["generated"].format(date=now.strftime("%Y/%m/%d %H:%M"))),
        )
        canvas_obj.restoreState()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.6 * cm,
        title=labels["title"],
        author="AI Surveillance Agent",
    )
    doc.build(story, onFirstPage=_pdf_page_footer, onLaterPages=_pdf_page_footer)
    pdf_bytes = buffer.getvalue()
    logger.info(
        f"📄 تقرير PDF [{lang}/{period}]: {len(events_shown)} من "
        f"{total_in_period} حدثاً — {len(pdf_bytes)} بايت"
    )
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={
            # ترويسات HTTP ترميزها latin-1 حصراً — اسم ملف ASCII دائماً
            "Content-Disposition": f'attachment; filename="surveillance_report_{lang}_{now:%Y%m%d}.pdf"',
        },
    )



@app.get("/api/stats/daily")
async def get_daily_stats() -> dict[str, Any]:
    """إحصائيات اليوم — تشمل أنواع كشف السلوك الشاذ (running/loitering)"""
    today = datetime.now().date()
    counts: dict[str, Any] = {
        "total": 0,
        "fall": 0,
        "fight": 0,
        "intrusion": 0,
        "running": 0,
        "loitering": 0,
    }
    for event in _read_events():
        timestamp = event.get("timestamp")
        if not isinstance(timestamp, str):
            continue
        try:
            event_date = datetime.fromisoformat(timestamp).date()
        except ValueError:
            continue
        if event_date != today:
            continue
        counts["total"] += 1
        event_type = event.get("event")
        if event_type in counts and event_type != "total":
            counts[event_type] += 1
    return {**counts, "date": today.isoformat()}
