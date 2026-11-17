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
from src.fight_detector import evaluate_frame
from src.color_detector import color_match_percentage

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
    fights: List[dict]  # أحداث المشاجرات والتجمهر (fight/crowd_surge) — طبقة مستقلة عن كل ما سبق
    color_events: List[dict]  # أحداث اللون الممنوع (forbidden_color_intrusion) داخل المنطقة الحساسة

# المؤقتات الآن لكل كاميرا على حدة (مفتاحها camera_id) — لا مشاركة
# بين الكاميرات: dwell/cooldown لكاميرا لا يؤثر على الأخرى
_last_alert_time: dict[int, float] = {}
_zone_entry_time: dict[int, float | None] = {}
# وقت آخر حدث لكل (camera_id, track_id) — يغطي تنبيه التسلل ودخول الموظف:
# نفس الشخص المتتبَّع لا يعيد حدثاً خلال TRACK_COOLDOWN_SEC، وشخص جديد
# (معرّف آخر) يطلق حدثاً فوراً
_last_track_alert: dict[tuple[int, int], float] = {}

# وقت آخر قرار كشف اللون الممنوع لكل (camera_id, track_id) — يمنع غمل
# القرارات/التنبيهات كل إطار (الشخص باللون الممنوع داخل المنطقة يقرر مرة
# واحدة كل ANOMALY_EVENT_COOLDOWN: موظفاً كان (كبت) أو مجهولاً (تنبيه))
_last_color_decision: dict[tuple[int, int], float] = {}


def _prune_track_alerts(now: float, horizon: float) -> None:
    """حذف القديم من _last_track_alert لمنع نموّه بلا حدود — تافه التكلفة

    (تُستدعى فقط عند وجود أشخاص داخل المنطقة؛ القاموس صغير عموماً)"""
    for key in [
        key for key, ts in _last_track_alert.items() if now - ts > horizon
    ]:
        _last_track_alert.pop(key, None)


def _log_agent_decision(
    camera_id,
    decision_type: str,
    reasoning: str,
    confidence=None,
) -> None:
    """تسجيل قرار الوكيل في جدول agent_decisions (Audit Trail — استقلالية
    اتخاذ القرار: alert_sent / alert_suppressed / anomaly_escalated).

    الاستيراد متأخر: src/database يرفع استثناء عند غياب DATABASE_URL،
    وأي فشل (قاعدة/شبكة) يُبتلع داخل record_agent_decision_sync —
    لا يكسر خط الكشف/التنبيه إطلاقاً."""
    try:
        from src.database import record_agent_decision_sync
    except Exception:
        return
    record_agent_decision_sync(
        camera_id=str(camera_id),
        decision_type=decision_type,
        reasoning=reasoning,
        confidence=confidence,
    )


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

def fight_node(state: SurveillanceState) -> SurveillanceState:
    """كشف المشاجرات والتجمهر المفاجئ (fight/crowd_surge) — مستقل تماماً عن
    منطق المنطقة/الوقت/الأدوار في decision_node كي لا يحجبه باب التوقيت أو
    المهلات، والنتيجة تمر عبر state["fights"] لمعالجتها في alert_node فقط."""
    camera_key = int(state.get("camera_id") or 0)
    camera_label = str(state.get("camera_name") or f"كاميرا {camera_key}")
    fights = evaluate_frame(camera_key, camera_label, state.get("persons") or [])
    state["fights"] = fights
    for fight in fights:
        logger.info(
            f"🥊 حدث مشاجرات [{fight['event_type']}] في [{camera_label}] "
            f"track={fight.get('track_id_a')}+{fight.get('track_id_b')}"
            if fight["event_type"] == "fight"
            else f"👥 حدث تجمهر [{fight['event_type']}] في [{camera_label}] "
            f"persons={fight.get('persons_count')}"
        )
    return state

def is_inside_zone(bbox, zone):
    x1, y1, x2, y2 = bbox
    zx1, zy1, zx2, zy2 = zone
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    return zx1 <= cx <= zx2 and zy1 <= cy <= zy2

def color_zone_node(state: SurveillanceState) -> SurveillanceState:
    """كشف اللون الممنوع داخل المنطقة الحساسة فقط (forbidden_color_intrusion) —
    الترتيب صريح: فحص اللون أولاً، ثم تحقق التعرف على الوجوه (نتيجة
    detect_node): موظف معروف → قرار alert_suppressed (تجاهل)، ومجهول →
    حدث في state["color_events"] يعالج في alert_node (تسجيل + تيليجرام/بريد).
    مستقل عن باب التوقيت/المهلات في decision_node — الشرط الوحيد: داخل ZONE.
    """
    state["color_events"] = []
    if not bool(Config.ENABLE_COLOR_DETECTION):
        return state
    frame = state.get("frame")
    persons = state.get("persons") or []
    if frame is None or not persons:
        return state

    camera_key = int(state.get("camera_id") or 0)
    camera_label = str(state.get("camera_name") or f"كاميرا {camera_key}")
    zone = (
        Config.ZONE_TOP_LEFT_X,
        Config.ZONE_TOP_LEFT_Y,
        Config.ZONE_BOTTOM_RIGHT_X,
        Config.ZONE_BOTTOM_RIGHT_Y,
    )
    target_hex = str(Config.FORBIDDEN_COLOR_HEX)
    tolerance = int(Config.COLOR_TOLERANCE)
    min_percentage = float(Config.COLOR_MIN_PERCENTAGE)
    cooldown = float(Config.ANOMALY_EVENT_COOLDOWN)
    now_ts = time.time()

    events: List[dict] = []
    for person in persons:
        if not is_inside_zone(person["bbox"], zone):
            continue  # الميزة تعمل داخل المنطقة الحساسة حصراً

        percentage = color_match_percentage(frame, person["bbox"], target_hex, tolerance)
        if percentage is None or percentage < min_percentage:
            continue

        track_id = person.get("track_id")
        decision_key = (camera_key, int(track_id or 0))
        if now_ts - _last_color_decision.get(decision_key, -1.0e18) < cooldown:
            continue  # قرار هذا الشخص صدر قبل قليل — بلا غمل كل إطار
        _last_color_decision[decision_key] = now_ts

        if person.get("employee_id") is not None:
            # موظف مصرح له (Face Recognition) — كبت التنبيه مع تسجيل السبب
            employee_name = str(person.get("name") or "Unknown")
            logger.info(
                f"🧑‍💼 لون ممنوع {target_hex} ({percentage:.0f}%) داخل المنطقة "
                f"[{camera_label}] لكنه موظف معروف: {employee_name} — تجاهل"
            )
            _log_agent_decision(
                camera_key,
                "alert_suppressed",
                f"Forbidden color {target_hex} matched ({percentage:.0f}% of torso) "
                f"in restricted zone [{camera_label}], but person recognized as "
                f"employee {employee_name}. Alert suppressed.",
                person.get("match_score"),
            )
            continue

        # مجهول يرتدي اللون الممنوع داخل المنطقة الحساسة — حدث فوري
        events.append({
            "event_type": "forbidden_color_intrusion",
            "timestamp": datetime.now().isoformat(),
            "camera_id": camera_key,
            "camera_name": camera_label,
            "track_id": track_id,
            "color_hex": target_hex,
            "match_percentage": round(percentage, 1),
            "tolerance": tolerance,
        })
        logger.info(
            f"🟦 لون ممنوع {target_hex} ({percentage:.0f}%) داخل المنطقة "
            f"[{camera_label}] track={track_id}"
        )

    state["color_events"] = events
    return state

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
        _log_agent_decision(
            camera_key,
            "alert_suppressed",
            f"Person matched employee: {state['employee_name']}"
            f"{' (' + state['employee_role'] + ')' if state['employee_role'] else ''}. "
            "Alert suppressed to prevent false alarm.",
            trigger.get("match_score"),
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

    _log_agent_decision(
        camera_key,
        "alert_sent",
        f"Intruder detected in zone [{camera_label}]. No employee match "
        f"({len(unknown_persons)} unknown person(s), "
        f"dwell {float(Config.ZONE_DWELL_TIME):.0f}s).",
        trigger.get("confidence"),
    )

    return state

def alert_node(state: SurveillanceState) -> SurveillanceState:
    # === -1. أحداث المشاجرات والتجمهر المفاجئ (fight/crowd_surge) ===
    # أحداث حرجة دائماً → قرار في Audit Trail + تيليجرام + بريد (إن فُعّل).
    for fight in state.get("fights") or []:
        import cv2
        event_type = str(fight.get("event_type") or "")
        camera_key = int(fight.get("camera_id") or state.get("camera_id") or 0)
        camera_label = str(fight.get("camera_name") or f"كاميرا {camera_key}")
        ts_snap = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"alerts/{event_type}_{camera_key}_{ts_snap}.jpg"
        try:
            cv2.imwrite(path, state["frame"])
        except Exception as exc:
            path = ""
            logger.warning(f"⚠️ تعذّر حفظ لقطة الحدث [{event_type}]: {exc}")

        if not path:
            continue
        EventLogger().log_event(event_type, dict(fight), path)

        # قرار الوكيل في سجل القرارات (Audit Trail) بنوع الحدث نفسه
        if event_type == "fight":
            reasoning = (
                f"High IoU ({fight.get('max_iou')}) between Person "
                f"#{fight.get('track_id_a')} and #{fight.get('track_id_b')} "
                f"for {fight.get('sustained_frames')} frames "
                f"(speed {fight.get('speed_px_s')} px/s). "
                "Immediate alert triggered."
            )
        else:
            reasoning = (
                f"{fight.get('persons_count')} persons converging toward one "
                f"point (approach {fight.get('approach_speed_px_s')} px/s, "
                f"min distance {fight.get('min_distance_px')} px). "
                "Immediate alert triggered."
            )
        _log_agent_decision(
            camera_key,
            "fight_detected" if event_type == "fight" else "crowd_surge_detected",
            reasoning,
            None,
        )

        alert = Alert()
        timestamp_label = str(fight.get("timestamp") or "")
        if event_type == "fight":
            message = (
                f"🥊 شجار محتمل في: {camera_label} الساعة {timestamp_label} "
                f"(تداخل IoU {fight.get('max_iou')} بين الشخصين "
                f"#{fight.get('track_id_a')} و#{fight.get('track_id_b')} "
                f"لمدة {fight.get('sustained_frames')} إطار)"
            )
        else:
            message = (
                f"👥 تجمهر مفاجئ في: {camera_label} الساعة {timestamp_label} "
                f"({fight.get('persons_count')} أشخاص يتقاربون نحو نقطة واحدة "
                f"بسرعة {fight.get('approach_speed_px_s')} px/s)"
            )
        alert.send_telegram(path, message)
        alert.send_email_alert(path, message)
    state["fights"] = []

    # === -2. أحداث اللون الممنوع داخل المنطقة الحساسة (forbidden_color_intrusion) ===
    # أحداث حرجة → قرار في Audit Trail + تيليجرام + بريد (إن فُعّل).
    # (كبت الموظفين يقرر في color_zone_node نفسه — لا يصل هنا)
    for color_event in state.get("color_events") or []:
        import cv2
        camera_key = int(color_event.get("camera_id") or state.get("camera_id") or 0)
        camera_label = str(color_event.get("camera_name") or f"كاميرا {camera_key}")
        ts_snap = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"alerts/forbidden_color_{camera_key}_{ts_snap}.jpg"
        try:
            cv2.imwrite(path, state["frame"])
        except Exception as exc:
            path = ""
            logger.warning(f"⚠️ تعذّر حفظ لقطة اللون الممنوع: {exc}")

        if not path:
            continue
        EventLogger().log_event("forbidden_color_intrusion", dict(color_event), path)

        _log_agent_decision(
            camera_key,
            "forbidden_color_intrusion",
            f"Person wearing forbidden color {color_event.get('color_hex')} "
            f"({color_event.get('match_percentage')}% of torso) inside restricted "
            f"zone [{camera_label}]. Not recognized as an employee "
            f"(face match unknown). Immediate alert triggered.",
            (float(color_event.get("match_percentage") or 0.0) / 100.0) or None,
        )

        alert = Alert()
        timestamp_label = str(color_event.get("timestamp") or "")
        message = (
            f"🟦 دخول بلون ممنوع ({color_event.get('color_hex')}) في المنطقة "
            f"الحساسة: {camera_label} الساعة {timestamp_label} "
            f"(نسبة مطابقة الزي {color_event.get('match_percentage')}%) — "
            f"شخص غير معروف"
        )
        alert.send_telegram(path, message)
        alert.send_email_alert(path, message)
    state["color_events"] = []

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

        # رفع مستوى الحدث الشاذ (سقوط/جري) — سجل القرار في Audit Trail
        # (loitering لا يرفع تنبيهاً حسب سياسة الإزعاج — لا قرار escalation)
        if anomaly_type == "fall":
            _log_agent_decision(
                int(anomaly.get("camera_id") or 0),
                "anomaly_escalated",
                "Fall detected. Immediate alert triggered.",
                None,
            )
        elif anomaly_type == "running":
            _log_agent_decision(
                int(anomaly.get("camera_id") or 0),
                "anomaly_escalated",
                f"Running detected ({anomaly.get('speed_px_s')} px/s). "
                "Immediate alert triggered.",
                None,
            )

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
    builder.add_node("fight", fight_node)
    builder.add_node("color_zone", color_zone_node)
    builder.add_node("decision", decision_node)
    builder.add_node("alert", alert_node)

    builder.set_entry_point("detect")
    builder.add_edge("detect", "anomaly")
    builder.add_edge("anomaly", "fight")
    builder.add_edge("fight", "color_zone")
    builder.add_edge("color_zone", "decision")
    builder.add_edge("decision", "alert")
    builder.add_edge("alert", END)

    return builder.compile()