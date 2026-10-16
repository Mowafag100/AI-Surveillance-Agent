from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import json
import os
from datetime import datetime, timedelta
from src.logger import EventLogger

# ... (استيرادات أخرى)

@app.get("/api/events")
async def get_events(limit: int = 50, camera_id: int = None, event_type: str = None):
    """جلب الأحداث الأخيرة مع تصفية اختيارية"""
    events = []
    log_file = "logs/events.jsonl"
    if not os.path.exists(log_file):
        return []

    with open(log_file, "r") as f:
        lines = f.readlines()[-limit*2:]  # قراءة أكثر قليلاً للتأكد
        for line in lines:
            try:
                event = json.loads(line)
                if camera_id and event.get("camera_id") != camera_id:
                    continue
                if event_type and event.get("event") != event_type:
                    continue
                events.append(event)
            except:
                continue

    return events[-limit:]

@app.get("/api/cameras")
async def get_cameras():
    """جلب قائمة الكاميرات وحالتها (محاكاة)"""
    # في الإصدار الحقيقي، نأخذ من قاعدة البيانات أو ملف الإعدادات
    return [
        {"id": 1, "name": "Gate", "status": "online"},
        {"id": 2, "name": "Corridor", "status": "online"},
    ]

@app.get("/api/stats/daily")
async def get_daily_stats():
    """إحصائيات اليوم"""
    today = datetime.now().date()
    events = []
    log_file = "logs/events.jsonl"
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            for line in f:
                try:
                    event = json.loads(line)
                    event_date = datetime.fromisoformat(event["timestamp"]).date()
                    if event_date == today:
                        events.append(event)
                except:
                    continue

    total = len(events)
    fall = sum(1 for e in events if e.get("event") == "fall")
    fight = sum(1 for e in events if e.get("event") == "fight")
    intrusion = sum(1 for e in events if e.get("event") == "intrusion")

    return {"total": total, "fall": fall, "fight": fight, "intrusion": intrusion, "date": today.isoformat()}

@app.get("/api/events/{id}/image")
async def get_event_image(id: int):
    """تحميل صورة الحدث"""
    # في الواقع، نبحث عن الصورة في مجلد alerts/
    # نستخدم معرف الحدث للعثور على الصورة المناسبة
    image_path = f"alerts/alert_{id}.jpg"
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path)