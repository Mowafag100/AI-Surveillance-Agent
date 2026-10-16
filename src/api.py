from datetime import datetime
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

BASE_DIR = Path(__file__).resolve().parent.parent
EVENTS_FILE = BASE_DIR / "logs" / "events.jsonl"
ALERTS_DIR = (BASE_DIR / "alerts").resolve()

app = FastAPI(title="AI Surveillance API", version="1.0")

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
    """قائمة الكاميرات وحالتها (بيانات محاكاة)"""
    return [
        {"id": 1, "name": "Gate", "status": "online"},
        {"id": 2, "name": "Corridor", "status": "online"},
    ]


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
