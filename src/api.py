from datetime import datetime
import csv
import io
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from src.auth import CurrentUser, SuperUser, alias_router, router as auth_router
from src.config import CONFIG_JSON_PATH, Config, _SETTINGS, load_json_config

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


@app.get("/api/reports/export")
async def export_reports(admin_user: SuperUser) -> StreamingResponse:
    """تصدير الأحداث كملف CSV (utf-8-sig لفتحه بـ Excel مع العربية) — للمشرفين فقط"""
    buffer = io.StringIO()
    # BOM يضمن قراءة العربيات في Excel مباشرة
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(["timestamp", "event", "camera_id", "camera_name", "details", "image"])
    for event in _read_events():
        details = event.get("details") or {}
        writer.writerow([
            event.get("timestamp", ""),
            event.get("event", ""),
            details.get("camera_id", ""),
            details.get("camera_name", ""),
            json.dumps(details, ensure_ascii=False) if details else "",
            event.get("image", ""),
        ])

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="events_report.csv"',
        },
    )


@app.get("/api/stats/daily")
async def get_daily_stats() -> dict[str, Any]:
    """إحصائيات اليوم"""
    today = datetime.now().date()
    counts: dict[str, Any] = {"total": 0, "fall": 0, "fight": 0, "intrusion": 0}
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
        if event_type in ("fall", "fight", "intrusion"):
            counts[event_type] += 1
    return {**counts, "date": today.isoformat()}
