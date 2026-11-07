"""كشف السلوك الشاذ (Behavioral Anomaly Detection) لكل (كاميرا، شخص متتبَّع).

تُستدعى update_and_evaluate من عقدة anomaly في src/agent.py لكل شخص في كل إطار،
وفيها ثلاثة كواشف مستقلة على الحالة المشتركة (مفتاحها (camera_id, track_id)):

1) running (جري): سرعة مركز الـ Bounding Box ضمن نافذة متدحرة (~1.2 ثانية).
   الإطارات منقّحة مسبقاً إلى 640×480 في main.py، لذلك العتبة
   RUN_SPEED_THRESHOLD_PX (افتراضي 150 px/s) تقارن بكسلاً ببكسل —
   المشي الطبيعي ~20-60 px/s والجري يتجاوزها بكثير.

2) fall (سقوط): انقلاب نسبة العرض/الطول — العرض أكبر من الطول (شخص مستلقي)
   فوق FALL_ASPECT_RATIO_THRESHOLD (إعداد موجود مسبقاً: 1.2 — يُعاد استخدامه)
   بشرط أن الشخص كان واقفاً (نسبة أقل من العتبة خلال آخر 1.5 ثانية) قبل
   الانقلاب. يمكن لاحقاً رفع الدقة بنموذج yolov8n-pose.pt (مفاصل الجسم)
   دون تغيير واجهة هذا الملف.

3) loitering (توقّف مشبوه): لوح (anchor) بَيَّن موقع الشخص عندما اقترب من
   المنطقة الحساسة (داخلها أو ضمن LOITERING_RADIUS_PX من حدودها). إذا بقيت
   حركته داخل تلك الدائرة (مساحة صغيرة) لمدة LOITERING_SEC (افتراضي 60 ثانية)
   ← حدث loitering مرة واحدة لكل جلسة استمرارية؛ الخروج من المساحة أو محيط
   المنطقة ينهي الجلسة (وينتهي أيضاً عند الانقطاع الزمني الطويل للتعقب).
   سياسة التنبيه (تيليجرام أم لا) تُقرر في src/agent.py — الحدث يصل
   سجل الأحداث/UI دائماً.

حماية الغمل (spam): مهلة ANOMALY_EVENT_COOLDOWN (افتراضي 20 ثانية) لكل
(كاميرا، شخص، نوع) — الحدث لا يتوالد كل إطار.
"""

import time
from collections import deque
from datetime import datetime
from typing import Any

from src.config import Config

# نافذة تقييم السرعة بالثواني — تكفي للفروق الحقيقية بين المشي والجري
_SPEED_WINDOW_SEC = 1.2
# أقل فاصل زمني مقبول بين عيّنتين (أقل من هذا = تطفر jitter في قياس المركز)
_SPEED_MIN_INTERVAL_SEC = 0.15
# أقل عدد عيّنات داخل النافذة لقبول قياس السرعة
_SPEED_MIN_SAMPLES = 3
# نافذة كشف السقوط (انقلاب النسبة بعد ثبات واقف)
_FALL_WINDOW_SEC = 1.5
# سجل حركة كل شخص — ~ ثوانٍ كافية عند ~3 إطارات/ثانية لكل كاميرا (0.05 وقفة)
_HISTORY_MAXLEN = 60

# الحالة المشتركة بلا أقفال: كل ثريد كاميرا يمس مفاتيح (camera_id, track_id)
# الخاصة بها فقط (نمط نفس agent.py مع مؤقتاتها لكل كاميرا)
_track_history: dict[tuple[int, int], deque] = {}
_track_anchor: dict[tuple[int, int], dict[str, Any]] = {}
_last_anomaly: dict[tuple[int, int, str], float] = {}


def _now_iso() -> str:
    return datetime.now().isoformat()


def _distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """مسافة إقليدية بالبكسل على إطار المعالجة (640×480)"""
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5


def _is_near_zone(cx: float, cy: float, pad: float) -> bool:
    """داخل المنطقة الحساسة أو ضمن توسيع pad بكسل حول حدودها (بجوارها)"""
    zx1 = min(Config.ZONE_TOP_LEFT_X, Config.ZONE_BOTTOM_RIGHT_X) - pad
    zy1 = min(Config.ZONE_TOP_LEFT_Y, Config.ZONE_BOTTOM_RIGHT_Y) - pad
    zx2 = max(Config.ZONE_TOP_LEFT_X, Config.ZONE_BOTTOM_RIGHT_X) + pad
    zy2 = max(Config.ZONE_TOP_LEFT_Y, Config.ZONE_BOTTOM_RIGHT_Y) + pad
    return zx1 <= cx <= zx2 and zy1 <= cy <= zy2


def _check_running(ts: float, key: tuple[int, int]) -> float:
    """أقصى سرعة مركز box ضمن النافذة (px/s) — 0.0 إن لم يوجد قياس موثوق

    أزواج العينات المتتالية (تكافئ الحركة المستمرة) + طرفي النافذة (التقط
    السرعة الصافية كاملة عبر الفترة)."""
    samples = [s for s in _track_history[key] if ts - s["ts"] <= _SPEED_WINDOW_SEC]
    if len(samples) < _SPEED_MIN_SAMPLES:
        return 0.0
    best = 0.0
    for i in range(1, len(samples)):
        dt = samples[i]["ts"] - samples[i - 1]["ts"]
        if dt < _SPEED_MIN_INTERVAL_SEC:
            continue
        best = max(
            best,
            _distance(
                (samples[i]["cx"], samples[i]["cy"]),
                (samples[i - 1]["cx"], samples[i - 1]["cy"]),
            ) / dt,
        )
    dt = samples[-1]["ts"] - samples[0]["ts"]
    if dt >= _SPEED_MIN_INTERVAL_SEC:
        best = max(
            best,
            _distance(
                (samples[-1]["cx"], samples[-1]["cy"]),
                (samples[0]["cx"], samples[0]["cy"]),
            ) / dt,
        )
    return best


def _check_fall(ts: float, key: tuple[int, int]) -> tuple[float, float] | None:
    """سقوط: انتقال (واقف ثم مستلقي) — يعيد (النسبة الحالية، قبله) أو None

    لا يُقيَّم ممن هو مستلقٍ من البداية (شخص جالس/نائم من أول ظهور) —
    الإشارة المطلقة هي «الانقلاب المفاجئ»."""
    samples = [s for s in _track_history[key] if ts - s["ts"] <= _FALL_WINDOW_SEC]
    if len(samples) < 3:
        return None
    current_ratio = samples[-1]["aspect"]
    if current_ratio < float(Config.FALL_ASPECT_RATIO_THRESHOLD):
        return None
    upright = [
        s for s in samples[:-1]
        if s["aspect"] < float(Config.FALL_ASPECT_RATIO_THRESHOLD)
    ]
    if not upright:
        return None
    return current_ratio, upright[-1]["aspect"]


def _check_loitering(
    ts: float, key: tuple[int, int], cx: float, cy: float
) -> dict[str, Any] | None:
    """توقّف ثابت في مساحة صغيرة داخل/قرب المنطقة الحساسة فوق عتبة المدة.

    جلسة واحدة لكل استمرارية: الحدثّ يُطلق مرة عند تجاوز المدة، ثم يصمت
    فيظل ثانياً («fired») حتى تنتهي الجلسة بالحركة أو الخروج."""
    radius = float(Config.LOITERING_RADIUS_PX)
    near = _is_near_zone(cx, cy, radius)
    anchor = _track_anchor.get(key)

    if anchor is None:
        if near:
            _track_anchor[key] = {"cx": cx, "cy": cy, "ts": ts}
        return None

    if not near:
        # خرج من محيط المنطقة الحساسة — تنتهي جلسة التوقّف
        _track_anchor.pop(key, None)
        return None

    if _distance((anchor["cx"], anchor["cy"]), (cx, cy)) > radius:
        # تجاوز الدائرة من نقطة اللوح — تحرّك خارج المساحة الصغيرة:
        # إنهاء الجلسة، والظهور مجدداً تبدأ لوحاً (anchor) جديداً
        _track_anchor.pop(key, None)
        return None

    if anchor.get("fired"):
        return None  # حادث هذا الجلسة أصدر حدثه — بلا إعادة حتى انتهى بلايينه

    duration = ts - anchor["ts"]
    if duration < float(Config.LOITERING_SEC):
        return None

    anchor["fired"] = ts
    return {"duration_sec": round(duration, 1)}


def _cooldown_ok(
    ts: float, camera_id: int, track_id: int | None, anomaly_type: str
) -> bool:
    """مهلة الحدث الواحد لكل (كاميرا، شخص، نوع) — تمنع التكرار كل إطار"""
    cooldown_key = (camera_id, int(track_id or 0), anomaly_type)
    cooldown = float(Config.ANOMALY_EVENT_COOLDOWN)
    if ts - _last_anomaly.get(cooldown_key, -1.0e18) < cooldown:
        return False
    _last_anomaly[cooldown_key] = ts
    return True


def prune_camera_alarms(active_camera_ids: set[int]) -> None:
    """نظافة الذاكرة عند حذف/إعادة ضبط الكاميرات حيّاً — حذف مفاتيح كاميرا منحلة"""
    active = set(active_camera_ids)
    for store in (_track_history, _track_anchor):
        for key in [k for k in store if k[0] not in active]:
            store.pop(key, None)
    for key in [k for k in _last_anomaly if k[0] not in active]:
        _last_anomaly.pop(key, None)


def update_and_evaluate(
    camera_id: int,
    camera_name: str,
    track_id: int | None,
    bbox: list[float],
) -> list[dict[str, Any]]:
    """تحدّث حالة الشخص لهذا الإطار وتعيد قائمة أحداث الشذوذ المُطلَقة.

    كل عنصر جاهز للـ EventLogger بنسق employee_entry نفسه:
      {timestamp, camera_id, camera_name, track_id, + حقول الكاشف}
    مع مفتاح event_type (running/fall/loitering) لمعالجة التنبيهات في
    alert_node. لا دولار هنا أي وظيفة I/O (حفظ/إرسال) — منهجياً نقية.
    """
    if not bool(Config.ENABLE_ANOMALY_DETECTION) or track_id is None:
        # بلا تفعيل أو بلا معرّف تتبّع ثابت — السرعة/الاستمرارية غير قابلة للقياس
        return []

    x1, y1, x2, y2 = bbox
    width = max(1.0, float(x2) - float(x1))
    height = max(1.0, float(y2) - float(y1))
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    aspect = width / height

    key = (camera_id, int(track_id))
    ts = time.time()

    history = _track_history.get(key)
    if history is None or ts - history[-1]["ts"] > 10.0:
        # شخص جديد/كاميرا عادت، أو انقطاع طويل في التعقب — سجل جديد:
        # الأحداث القديمة لا تسري على الحاضر (ولوح التوقّف القديم يُمهَل)
        history = deque(maxlen=_HISTORY_MAXLEN)
        _track_history[key] = history
        _track_anchor.pop(key, None)
    history.append({"ts": ts, "cx": cx, "cy": cy, "aspect": aspect})

    detected: list[dict[str, Any]] = []

    # --- الجري ---
    speed = _check_running(ts, key)
    if (
        speed >= float(Config.RUN_SPEED_THRESHOLD_PX)
        and _cooldown_ok(ts, camera_id, track_id, "running")
    ):
        detected.append({
            "event_type": "running",
            "timestamp": _now_iso(),
            "camera_id": camera_id,
            "camera_name": camera_name or f"كاميرا {camera_id}",
            "track_id": track_id,
            "speed_px_s": round(speed, 1),
        })

    # --- السقوط ---
    fall = _check_fall(ts, key)
    if fall is not None and _cooldown_ok(ts, camera_id, track_id, "fall"):
        current_ratio, prev_ratio = fall
        detected.append({
            "event_type": "fall",
            "timestamp": _now_iso(),
            "camera_id": camera_id,
            "camera_name": camera_name or f"كاميرا {camera_id}",
            "track_id": track_id,
            "aspect_ratio": round(current_ratio, 2),
            "prev_aspect_ratio": round(prev_ratio, 2),
        })

    # --- التوقّف المشبوه ---
    loiter = _check_loitering(ts, key, cx, cy)
    if loiter is not None and _cooldown_ok(ts, camera_id, track_id, "loitering"):
        detected.append({
            "event_type": "loitering",
            "timestamp": _now_iso(),
            "camera_id": camera_id,
            "camera_name": camera_name or f"كاميرا {camera_id}",
            "track_id": track_id,
            "duration_sec": loiter["duration_sec"],
        })

    return detected
