from datetime import datetime
import csv
import io
import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from src.auth import CurrentUser, SuperUser, alias_router, router as auth_router
from src.config import CONFIG_JSON_PATH, Config, _SETTINGS, load_json_config

BASE_DIR = Path(__file__).resolve().parent.parent
EVENTS_FILE = BASE_DIR / "logs" / "events.jsonl"
ALERTS_DIR = (BASE_DIR / "alerts").resolve()

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
        if attr in ("TELEGRAM_BOT_TOKEN",):
            masked[attr] = _mask_secret(value)
        else:
            masked[attr] = value
    return masked


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
) -> list[dict[str, Any]]:
    """جلب الأحداث الأخيرة مع تصفية اختيارية"""
    events = _read_events()
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
    return events[-limit:]


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
    """القائمة الحقيقية من config.json (مع توافق خلفي نحو CAMERA_URL القديم)"""
    Config.ensure_fresh()
    return [
        {
            "id": int(camera.get("id", index + 1)),
            "name": str(camera.get("name") or f"Camera {index + 1}"),
            "status": "online",
            "url": str(camera.get("url") or ""),
        }
        for index, camera in enumerate(Config.get_cameras())
    ]


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
