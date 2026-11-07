from langgraph.graph import StateGraph, END
from typing import TypedDict, List
import logging
import time
from datetime import datetime
from src.config import Config
from src.detector import Detector
from src.alert import Alert
from src.logger import EventLogger
from src.face_recognizer import get_face_recognizer
from src.anomaly import update_and_evaluate

logger = logging.getLogger(__name__)

class SurveillanceState(TypedDict):
    frame: any
    persons: List[dict]
    alert_sent: bool
    image_path: str
    timestamp: str
    camera_id: int
    camera_name: str
    track_id: int | None      # معرّف الشخص المتتبَّع الذي أطلق الحدث
    event_type: str           # intrusion / employee_entry / running / fall / loitering / فراغ (لا حدث)
    employee_name: str  # اسم الموظف عند التعرف عليه (تفاصيل الحدث)
    employee_role: str
    anomalies: List[dict]  # أحداث الشذوذ السلوكي (running/fall/loitering) — طبقة مستقلة عن intrusion

# المؤقتات الآن لكل كاميرا على حدة (مفتاحها camera_id) — لا مشاركة
# بين الكاميرات: dwell/cooldown لكاميرا لا يؤثر على الأخرى
_last_alert_time: dict[int, float] = {}
_zone_entry_time: dict[int, float | None] = {}
# وقت آخر حدث لكل (camera_id, track_id) — يغطي تنبيه التسلل ودخول الموظف:
# نفس الشخص المتتبَّع لا يعيد حدثاً خلال TRACK_COOLDOWN_SEC، وشخص جديد
# (معرّف آخر) يطلق حدثاً فوراً
_last_track_alert: dict[tuple[int, int], float] = {}


def _prune_track_alerts(now: float, horizon: float) -> None:
    """حذف القديم من _last_track_alert لمنع نموّه بلا حدود — تافه التكلفة

    (تُستدعى فقط عند وجود أشخاص داخل المنطقة؛ القاموس صغير عموماً)"""
    for key in [
        key for key, ts in _last_track_alert.items() if now - ts > horizon
    ]:
        _last_track_alert.pop(key, None)


def detect_node(state: SurveillanceState) -> SurveillanceState:
    detector = Detector()
    persons = detector.detect_persons(state["frame"])
    # التعرف على الوجوه فقط عند وجود أشخاص — صفر تكلفة على الإطارات الفارغة
    if persons:
        get_face_recognizer().recognize(state["frame"], persons)
    state["persons"] = persons
    return state


def anomaly_node(state: SurveillanceState) -> SurveillanceState:
    """كشف السلوك الشاذ (running/fall/loitering) — مستقل تماماً عن منطق
    المنطقة/الوقت/الأدوار في decision_node كي لا يحجبه باب التوقيت أو المهلات,
    والنتيجة تمر عبر state["anomalies"] لمعالجتها في alert_node فقط."""
    camera_key = int(state.get("camera_id") or 0)
    camera_label = str(state.get("camera_name") or f"كاميرا {camera_key}")
    anomalies: List[dict] = []
    for person in state.get("persons") or []:
        anomalies.extend(
            update_and_evaluate(
                camera_key,
                camera_label,
                person.get("track_id"),
                person["bbox"],
            )
        )
    state["anomalies"] = anomalies
    for anomaly in anomalies:
        logger.info(
            f"🚶 حدث سلوكي [{anomaly['event_type']}] في [{camera_label}] "
            f"track={anomaly.get('track_id')}"
        )
    return state

def is_inside_zone(bbox, zone):
    x1, y1, x2, y2 = bbox
    zx1, zy1, zx2, zy2 = zone
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    return zx1 <= cx <= zx2 and zy1 <= cy <= zy2

def decision_node(state: SurveillanceState) -> SurveillanceState:
    global _last_alert_time, _zone_entry_time, _last_track_alert

    # مفتاح الكاميرا الحالية — كل المؤقتات لكل كاميرا على حدة
    camera_key = int(state.get("camera_id") or 0)

    logger.info(f"👤 عدد الأشخاص المكتشفين: {len(state['persons'])}")

    state["track_id"] = None
    state["event_type"] = ""
    state["employee_name"] = ""
    state["employee_role"] = ""
    state["alert_sent"] = False

    if not state["persons"]:
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
        _zone_entry_time.pop(camera_key, None)
        return state

    # === 2. التحقق من المنطقة ===
    zone = (
        Config.ZONE_TOP_LEFT_X,
        Config.ZONE_TOP_LEFT_Y,
        Config.ZONE_BOTTOM_RIGHT_X,
        Config.ZONE_BOTTOM_RIGHT_Y
    )

    # كل من هو داخل المنطقة (قد يُطلق أحداً منهم حدثاً حسب المهلة لكل شخص)
    in_zone_persons = [
        p for p in state["persons"] if is_inside_zone(p["bbox"], zone)
    ]

    logger.info(f"📍 المنطقة: {zone}, داخل المنطقة: {len(in_zone_persons)}")

    if not in_zone_persons:
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

    # === 3ب. مهلة منع التكرار لكل شخص متتبَّع (track_id) ===
    track_cooldown = max(float(Config.TRACK_COOLDOWN_SEC), 0.0)
    _prune_track_alerts(current_time, 2.0 * max(track_cooldown, Config.ALERT_COOLDOWN))
    fresh = [
        p for p in in_zone_persons
        if (tid := p.get("track_id")) is None
        or (current_time - _last_track_alert.get((camera_key, tid), 0.0)) >= track_cooldown
    ]
    if not fresh:
        logger.info(f"🔁 كل الأشخاص داخل المنطقة أطلقوا حدثاً قبل أقل من {track_cooldown:.0f} ث — تجاهل")
        state["alert_sent"] = False
        return state

    # الموظفون المعروفون مقابل المجهولون (التعرف على الوجوه يعبّئ name/employee_id)
    employee_persons = [p for p in fresh if p.get("employee_id") is not None]
    unknown_persons = [p for p in fresh if p.get("employee_id") is None]

    # === 4ج. دخول موظف معروف — تسجيل حدث فقط بلا تنبيه (تيليجرام/بريد) ===
    if not unknown_persons and employee_persons:
        trigger = employee_persons[0]
        track_id = trigger.get("track_id")
        if track_id is not None:
            _last_track_alert[(camera_key, track_id)] = current_time
        state["track_id"] = track_id
        state["event_type"] = "employee_entry"
        state["employee_name"] = str(trigger.get("name") or "Unknown")
        state["employee_role"] = str(trigger.get("role") or "")
        state["alert_sent"] = False
        logger.info(
            f"🧑‍💼 دخول موظف: {state['employee_name']} "
            f"({state['employee_role'] or 'بدون وظيفة'}) — الكاميرا [{camera_key}]"
        )
        # مهلة الكاميرا (ALERT_COOLDOWN) للتنبيهات حصراً — لا يحجب تسجيل دخول
        return state

    if not unknown_persons:
        state["alert_sent"] = False
        return state

    # === 4. المهلة  (لكل كاميرا — تحجب تنبيه التسلل حصراً) ===
    last_alert = _last_alert_time.get(camera_key, 0.0)
    cooldown_remaining = Config.ALERT_COOLDOWN - (current_time - last_alert)
    logger.info(f"🔄 المهلة المتبقية: {cooldown_remaining:.2f} ثانية")

    if current_time - _last_alert_time.get(camera_key, 0.0) < Config.ALERT_COOLDOWN:
        state["alert_sent"] = False
        return state

    # === 5. إرسال التنبيه (تسلل — شخص غير معروف) ===
    logger.info("✅ جميع الشروط متحققة! إرسال تنبيه...")
    import cv2
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    camera_label = str(state.get("camera_name") or f"كاميرا {camera_key}")
    path = f"alerts/alert_{camera_key}_{ts}.jpg"
    cv2.imwrite(path, state["frame"])

    trigger = unknown_persons[0]
    state["image_path"] = path
    state["timestamp"] = ts
    state["alert_sent"] = True
    state["event_type"] = "intrusion"
    state["track_id"] = trigger.get("track_id")
    trigger_track_id = trigger.get("track_id")
    if trigger_track_id is not None:
        _last_track_alert[(camera_key, trigger_track_id)] = current_time
    _last_alert_time[camera_key] = current_time
    _zone_entry_time.pop(camera_key, None)

    return state

def alert_node(state: SurveillanceState) -> SurveillanceState:
    # === 0. أحداث الشذوذ السلوكي (running/fall/loitering) ===
    # سياسة التنبيه: running/fall أحداث حرجة → تيليجرام + بريد كالعادة؛
    # loitering يُسجَّل للتقارير/الواجهة فقط بلا تيليجرام (لتقليل الإزعاج).
    for anomaly in state.get("anomalies") or []:
        import cv2
        anomaly_type = str(anomaly.get("event_type") or "")
        camera_key = int(anomaly.get("camera_id") or state.get("camera_id") or 0)
        camera_label = str(anomaly.get("camera_name") or f"كاميرا {camera_key}")
        ts_snap = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"alerts/{anomaly_type}_{camera_key}_{ts_snap}.jpg"
        try:
            cv2.imwrite(path, state["frame"])
        except Exception as exc:
            path = ""
            logger.warning(f"⚠️ تعذّر حفظ لقطة الحدث السلوكي [{anomaly_type}]: {exc}")

        if not path:
            continue
        EventLogger().log_event(anomaly_type, dict(anomaly), path)

        if anomaly_type != "loitering":  # لا إزعاج تيليجرام للتوقّف المشبوه
            alert = Alert()
            timestamp_label = str(anomaly.get("timestamp") or "")
            if anomaly_type == "running":
                message = (
                    f"🏃 جري مشتبه به في: {camera_label} الساعة {timestamp_label} "
                    f"(السرعة {anomaly.get('speed_px_s')} px/s)"
                )
            else:  # fall
                message = f"⚠️ سقوط محتمل لشخص في: {camera_label} الساعة {timestamp_label}"
            alert.send_telegram(path, message)
            alert.send_email_alert(path, message)
    state["anomalies"] = []

    if state.get("event_type") == "employee_entry":
        # دخول موظف معروف — لقطة + تسجيل حدث فقط، بلا تيليجرام/بريد
        import cv2
        camera_key = int(state.get("camera_id") or 1)
        camera_label = str(state.get("camera_name") or f"كاميرا {camera_key}")
        ts = state.get("timestamp") or datetime.now().strftime("%Y%m%d_%H%M%S")
        state["timestamp"] = ts
        path = f"alerts/employee_{camera_key}_{ts}.jpg"
        cv2.imwrite(path, state["frame"])
        state["image_path"] = path
        EventLogger().log_event(
            "employee_entry",
            {
                "timestamp": datetime.now().isoformat(),
                "camera_id": camera_key,
                "camera_name": camera_label,
                "employee_name": state.get("employee_name") or "Unknown",
                "role": state.get("employee_role") or "",
                "track_id": state.get("track_id"),
            },
            path,
        )
        return state

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
                    "track_id": state.get("track_id"),
                },
                state["image_path"],
            )
    return state

def build_agent():
    builder = StateGraph(SurveillanceState)
    builder.add_node("detect", detect_node)
    builder.add_node("anomaly", anomaly_node)
    builder.add_node("decision", decision_node)
    builder.add_node("alert", alert_node)

    builder.set_entry_point("detect")
    builder.add_edge("detect", "anomaly")
    builder.add_edge("anomaly", "decision")
    builder.add_edge("decision", "alert")
    builder.add_edge("alert", END)

    return builder.compile()