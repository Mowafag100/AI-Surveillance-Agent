from langgraph.graph import StateGraph, END
from typing import TypedDict, List
import logging
import time
from datetime import datetime
from src.config import Config
from src.detector import Detector
from src.alert import Alert
from src.logger import EventLogger

logger = logging.getLogger(__name__)

class SurveillanceState(TypedDict):
    frame: any
    persons: List[dict]
    alert_sent: bool
    image_path: str
    timestamp: str
    camera_id: int
    camera_name: str

# المؤقتات الآن لكل كاميرا على حدة (مفتاحها camera_id) — لا مشاركة
# بين الكاميرات: dwell/cooldown لكاميرا لا يؤثر على الأخرى
_last_alert_time: dict[int, float] = {}
_zone_entry_time: dict[int, float | None] = {}


def detect_node(state: SurveillanceState) -> SurveillanceState:
    detector = Detector()
    persons = detector.detect_persons(state["frame"])
    state["persons"] = persons
    return state

def is_inside_zone(bbox, zone):
    x1, y1, x2, y2 = bbox
    zx1, zy1, zx2, zy2 = zone
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    return zx1 <= cx <= zx2 and zy1 <= cy <= zy2

def decision_node(state: SurveillanceState) -> SurveillanceState:
    global _last_alert_time, _zone_entry_time

    # مفتاح الكاميرا الحالية — كل المؤقتات لكل كاميرا على حدة
    camera_key = int(state.get("camera_id") or 0)

    logger.info(f"👤 عدد الأشخاص المكتشفين: {len(state['persons'])}")

    if not state["persons"]:
        state["alert_sent"] = False
        _zone_entry_time.pop(camera_key, None)
        return state

    # === 1. التحقق من التوقيت ===
    now = datetime.now()
    start_hour = Config.ALERT_START_HOUR
    end_hour = Config.ALERT_END_HOUR

    if end_hour < start_hour:
        is_time_valid = (now.hour >= start_hour or now.hour <= end_hour)
    else:
        is_time_valid = (start_hour <= now.hour <= end_hour)

    logger.info(f"⏰ التوقيت: {now.hour}:{now.minute}, الفترة: {start_hour}-{end_hour}, صالح: {is_time_valid}")

    if not is_time_valid:
        state["alert_sent"] = False
        _zone_entry_time.pop(camera_key, None)
        return state

    # === 2. التحقق من المنطقة ===
    zone = (
        Config.ZONE_TOP_LEFT_X,
        Config.ZONE_TOP_LEFT_Y,
        Config.ZONE_BOTTOM_RIGHT_X,
        Config.ZONE_BOTTOM_RIGHT_Y
    )

    person_in_zone = False
    for person in state["persons"]:
        if is_inside_zone(person["bbox"], zone):
            person_in_zone = True
            break

    logger.info(f"📍 المنطقة: {zone}, الشخص داخل المنطقة: {person_in_zone}")

    if not person_in_zone:
        state["alert_sent"] = False
        _zone_entry_time.pop(camera_key, None)
        return state

    # === 3. مدة البقاء ===
    current_time = time.time()
    if _zone_entry_time.get(camera_key) is None:
        _zone_entry_time[camera_key] = current_time
        state["alert_sent"] = False
        return state

    dwell_time = current_time - (_zone_entry_time[camera_key] or 0.0)
    logger.info(f"⏱️ مدة البقاء: {dwell_time:.2f} ثانية (المطلوب: {Config.ZONE_DWELL_TIME})")

    if dwell_time < Config.ZONE_DWELL_TIME:
        state["alert_sent"] = False
        return state

    # === 4. المهلة ===
    last_alert = _last_alert_time.get(camera_key, 0.0)
    cooldown_remaining = Config.ALERT_COOLDOWN - (current_time - last_alert)
    logger.info(f"🔄 المهلة المتبقية: {cooldown_remaining:.2f} ثانية")

    if current_time - _last_alert_time.get(camera_key, 0.0) < Config.ALERT_COOLDOWN:
        state["alert_sent"] = False
        return state

    # === 5. إرسال التنبيه ===
    logger.info("✅ جميع الشروط متحققة! إرسال تنبيه...")
    import cv2
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    camera_label = str(state.get("camera_name") or f"كاميرا {camera_key}")
    path = f"alerts/alert_{camera_key}_{ts}.jpg"
    cv2.imwrite(path, state["frame"])

    state["image_path"] = path
    state["timestamp"] = ts
    state["alert_sent"] = True
    _last_alert_time[camera_key] = current_time
    _zone_entry_time.pop(camera_key, None)

    return state

def alert_node(state: SurveillanceState) -> SurveillanceState:
    if state["alert_sent"] and state["image_path"]:
        alert = Alert()
        if alert.is_cooldown_over():
            camera_label = str(state.get("camera_name") or f"كاميرا {state.get('camera_id') or 1}")
            alert_message = f"🚨 تسلل محتمل في: {camera_label} الساعة {state['timestamp']}"
            alert.send_telegram(state["image_path"], alert_message)
            # التنبيه البريدي اختياري — يفعّل من ENABLE_EMAIL_ALERTS في config.json/.env
            alert.send_email_alert(state["image_path"], alert_message)
            logger_obj = EventLogger()
            logger_obj.log_event(
                "intrusion",
                {
                    "timestamp": state["timestamp"],
                    "camera_id": state.get("camera_id", 1),
                    "camera_name": camera_label,
                },
                state["image_path"],
            )
    return state

def build_agent():
    builder = StateGraph(SurveillanceState)
    builder.add_node("detect", detect_node)
    builder.add_node("decision", decision_node)
    builder.add_node("alert", alert_node)

    builder.set_entry_point("detect")
    builder.add_edge("detect", "decision")
    builder.add_edge("decision", "alert")
    builder.add_edge("alert", END)

    return builder.compile()