"""كشف المشاجرات والتجمهر المفاجئ (Fight & Crowd Surge Detection).

تُستدعى evaluate_frame من عقدة fight في src/agent.py لكل إطار بعد الكشف،
ولها كاشفان مستقلان على حالة مشتركة:

1) fight (شجار): التلاحم الجسدي السريع بين شخصين —
   نسبة التداخل IoU بين صندوقي شخصين متجاورين فوق FIGHT_IOU_THRESHOLD
   (افتراضي 0.2) مستمرة أكثر من FIGHT_MIN_FRAMES إطاراً (افتراضي 5)،
   مع سرعة حركة عالية لأحدهما (FIGHT_MOTION_THRESHOLD، افتراضي 50 px/s)
   لتمييز الشجار عن الوقوف الملاصق الهادئ (انتظار/حديث).

2) crowd_surge (تجمهر مفاجئ): تقارب المسافات — إذا كانت المسافة بين
   مركزي زوج تنكمش بسرعة CROWD_CONVERGENCE_THRESHOLD (افتراضي 80 px/s)
   وداخل نصف قطر CROWD_CONVERGENCE_RADIUS_PX (افتراضي 150)، فهذا زوج
   "متقارب"؛ ووجود CROWD_MIN_PERSONS (افتراضي 3) أشخاص يتقاربون نحو
   نقطة واحدة (عنقود نجمي حول شخص) يعلن تجمهراً مفاجئاً.

حماية الغمل: مهلة ANOMALY_EVENT_COOLDOWN (إعداد anomaly المشترك) لكل
(كاميرا، زوج/كاميرا، نوع) — الحدث لا يتوالد كل إطار، وتعود أزواج
التلاحم إلى الصفر عند فكّ التداخل.

الوحدات بكسل على إطار المعالجة (640×480) مثل src/anomaly.py.
"""

import time
from collections import deque
from datetime import datetime
from typing import Any

from src.config import Config

# سجل مواقع كل شخص (كاميرا، track_id) — ~2 ثانية كافية لقياس السرعة/التقارب
_PERSON_HISTORY_MAXLEN = 16
# عمر أقصى لعيّنات القياس داخل النافذة (ثوانٍ)
_SPEED_WINDOW_SEC = 1.0
# أقل فاصل زمني مقبول بين عيّنتين (منع تطفر jitter) — 0.03s يسمح بقياس
# السرعة حتى على معدل إطارات ~30fps
_MIN_INTERVAL_SEC = 0.03
# عدد إطارات غياب متسامح قبل مسح حالة الزوج (فقدان كشف لحظي)
_PAIR_MISS_TOLERANCE = 8

# الحالة المشتركة بلا أقفال: كل ثريد كاميرا يمس مفاتيح (camera_id, ...)
# الخاصة بها فقط (نمط src/anomaly.py نفسه)
_person_history: dict[tuple[int, int], deque] = {}
_pair_state: dict[tuple[int, int, int], dict[str, Any]] = {}
_last_fight: dict[tuple[int, int, int], float] = {}
_last_surge: dict[int, float] = {}


def _now_iso() -> str:
    return datetime.now().isoformat()


def _camera_label(camera_id: int, camera_name: str | None) -> str:
    return str(camera_name) if camera_name else f"كاميرا {camera_id}"


def _iou(box_a: list[float], box_b: list[float]) -> float:
    """تداخل صندوقين (IoU) على إطار 640×480"""
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0.0 else 0.0


def _distance(
    p1: tuple[float, float], p2: tuple[float, float]
) -> float:
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5


def _speed_px_s(history: deque) -> float:
    """أقصى سرعة مركز box خلال النافذة (px/s) — 0.0 بلا عيّنات كافية

    أزواج العينات المتتالية (تكافئ الحركة المستمرة) + طرفا النافذة."""
    ts = time.time()
    samples = [s for s in history if ts - s["ts"] <= _SPEED_WINDOW_SEC]
    if len(samples) < 2:
        return 0.0
    best = 0.0
    for i in range(1, len(samples)):
        dt = samples[i]["ts"] - samples[i - 1]["ts"]
        if dt < _MIN_INTERVAL_SEC:
            continue
        d = _distance(
            (samples[i]["cx"], samples[i]["cy"]),
            (samples[i - 1]["cx"], samples[i - 1]["cy"]),
        )
        best = max(best, d / dt)
    dt = samples[-1]["ts"] - samples[0]["ts"]
    if dt >= _MIN_INTERVAL_SEC:
        d = _distance(
            (samples[-1]["cx"], samples[-1]["cy"]),
            (samples[0]["cx"], samples[0]["cy"]),
        )
        best = max(best, d / dt)
    return best


def _cooldown_ok(
    key: tuple[int, ...], last_map: dict[tuple, float], ts: float
) -> bool:
    """مهلة الحدث الواحد (ANOMALY_EVENT_COOLDOWN) لكل مفتاح — تمنع التكرار"""
    if ts - last_map.get(key, -1.0e18) < float(Config.ANOMALY_EVENT_COOLDOWN):
        return False
    last_map[key] = ts
    return True


def prune_fight_state(active_camera_ids: set[int]) -> None:
    """نظافة الذاكرة عند حذف/إعادة ضبط الكاميرات حيّاً — حذف مفاتيح كاميرا منحلة"""
    active = set(active_camera_ids)
    for key in [k for k in _person_history if k[0] not in active]:
        _person_history.pop(key, None)
    for key in [k for k in _pair_state if k[0] not in active]:
        _pair_state.pop(key, None)
    for key in [k for k in _last_fight if k[0] not in active]:
        _last_fight.pop(key, None)
    for key in [k for k in _last_surge if k not in active]:
        _last_surge.pop(key, None)


def _check_fights(
    camera_id: int,
    camera_name: str,
    persons: list[dict],
    ts: float,
) -> list[dict[str, Any]]:
    """أزواج التلاحم: IoU مستمر + سرعة عالية → حدث fight لكل زوج مؤهل"""
    threshold = float(Config.FIGHT_IOU_THRESHOLD)
    min_frames = max(1, int(Config.FIGHT_MIN_FRAMES))
    motion = float(Config.FIGHT_MOTION_THRESHOLD)
    label = _camera_label(camera_id, camera_name)

    # تحديث عدّادات الأزواج الموجودة هذا الإطار (وعلامة الحضور)
    present: set[tuple[int, int, int]] = set()
    events: list[dict[str, Any]] = []
    n = len(persons)
    for i in range(n):
        for j in range(i + 1, n):
            tid_a, tid_b = persons[i].get("track_id"), persons[j].get("track_id")
            if tid_a is None or tid_b is None:
                continue  # بلا هوية ثابتة — لا زوج مستدام
            a, b = int(tid_a), int(tid_b)
            pair = (camera_id, min(a, b), max(a, b))
            iou = _iou(persons[i]["bbox"], persons[j]["bbox"])
            state = _pair_state.setdefault(
                pair, {"frames": 0, "max_iou": 0.0, "max_speed": 0.0, "missed": 0}
            )
            state["missed"] = 0

            if iou <= threshold:
                # فكّ التلاحم — العدّاد يعود للصفر فوراً
                state["frames"] = 0
                state["max_iou"] = 0.0
                state["max_speed"] = 0.0
                continue

            present.add(pair)
            speed = max(
                _speed_px_s(_person_history[(camera_id, a)]),
                _speed_px_s(_person_history[(camera_id, b)]),
            )
            state["frames"] = int(state["frames"]) + 1
            state["max_iou"] = max(float(state["max_iou"]), iou)
            state["max_speed"] = max(float(state["max_speed"]), speed)

            if (
                state["frames"] > min_frames
                and state["max_speed"] >= motion
                and _cooldown_ok((camera_id, min(a, b), max(a, b), "fight"), _last_fight, ts)
            ):
                events.append({
                    "event_type": "fight",
                    "timestamp": _now_iso(),
                    "camera_id": camera_id,
                    "camera_name": label,
                    "track_id_a": min(a, b),
                    "track_id_b": max(a, b),
                    "max_iou": round(float(state["max_iou"]), 2),
                    "sustained_frames": int(state["frames"]),
                    "speed_px_s": round(float(state["max_speed"]), 1),
                })

    # أزواج غائبة (فقد كشف لحظي): عدّاد التسامح ثم المسح
    for pair, state in _pair_state.items():
        if pair[0] != camera_id:
            continue
        if pair in present:
            continue
        state["missed"] = int(state["missed"]) + 1
        if int(state["missed"]) > _PAIR_MISS_TOLERANCE:
            state["frames"] = 0
            state["max_iou"] = 0.0
            state["max_speed"] = 0.0
            state["missed"] = 0
    return events


def _check_crowd_surge(
    camera_id: int,
    camera_name: str,
    persons: list[dict],
    ts: float,
) -> list[dict[str, Any]]:
    """تقارب المسافات: عنقود ≥ CROWD_MIN_PERSONS أشخاص ينكمشون نحو نقطة واحدة

    زوج "متقارب" = المسافة بين مركزيه تنكمش بسرعة > CROWD_CONVERGENCE_THRESHOLD
    والمسافة الحالية < CROWD_CONVERGENCE_RADIUS_PX. شخص له (الحد الأدنى - 1)
    جارٍ متقارب على الأقل = عنقود نجمي حوله ← تجمهر مفاجئ."""
    if len(persons) < max(2, int(Config.CROWD_MIN_PERSONS)):
        return []

    label = _camera_label(camera_id, camera_name)
    speed_threshold = float(Config.CROWD_CONVERGENCE_THRESHOLD)
    radius = float(Config.CROWD_CONVERGENCE_RADIUS_PX)

    # مركز كل شخص هذا الإطار + المواقع السابقة (العيّنة قبل الحالية —
    # evaluate_frame يضيف موضع الإطار الحالي إلى السجل قبل التقييم)
    now: dict[int, tuple[float, float]] = {}
    prev: dict[int, tuple[float, float, float]] = {}
    for person in persons:
        tid = person.get("track_id")
        if tid is None:
            continue
        x1, y1, x2, y2 = person["bbox"]
        key = (camera_id, int(tid))
        history = _person_history.get(key)
        if history is not None and len(history) >= 2:
            before = history[-2]
            prev[int(tid)] = (before["cx"], before["cy"], before["ts"])
        now[int(tid)] = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    # رسم التقارب: زوج متقارب = حافة موجهة (المتحرك نحو الآخر)
    adjacency: dict[int, set[int]] = {}
    pair_min_distance: dict[tuple[int, int], float] = {}
    ids = list(now)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            d_now = _distance(now[a], now[b])
            if d_now >= radius:
                continue
            pa_info, pb_info = prev.get(a), prev.get(b)
            if pa_info is None or pb_info is None:
                continue
            pa = (pa_info[0], pa_info[1])
            pb = (pb_info[0], pb_info[1])
            d_prev = _distance(pa, pb)
            shrinking = d_prev - d_now
            if shrinking <= 0.0:
                continue
            dt = ts - max(pa_info[2], pb_info[2])
            if dt < _MIN_INTERVAL_SEC:
                continue
            approach_speed = shrinking / dt
            if approach_speed < speed_threshold:
                continue
            # الحافة تُنسب لمن يتحرك نحو الآخر (الأقرب سابقاً يتحرك نحو الأبعد)
            mover_toward_other = _distance(pa, now[b]) < _distance(pb, now[a])
            near, far = (a, b) if mover_toward_other else (b, a)
            adjacency.setdefault(near, set()).add(far)
            adjacency.setdefault(far, set()).add(near)
            pair_min_distance[(min(a, b), max(a, b))] = d_now

    events: list[dict[str, Any]] = []
    if not pair_min_distance:
        return events

    min_persons = max(3, int(Config.CROWD_MIN_PERSONS))
    cluster: set[int] = set()
    best_speed = 0.0
    for person_id, neighbours in adjacency.items():
        if len(neighbours) >= min_persons - 1:
            cluster = {person_id, *neighbours}
            break
    if len(cluster) >= min_persons:
        for (a, b), d_now in pair_min_distance.items():
            if a in cluster and b in cluster:
                pa = (prev[a][0], prev[a][1])
                pb = (prev[b][0], prev[b][1])
                dt = max(_MIN_INTERVAL_SEC, ts - max(prev[a][2], prev[b][2]))
                best_speed = max(best_speed, (_distance(pa, pb) - d_now) / dt)
        events.append({
            "event_type": "crowd_surge",
            "timestamp": _now_iso(),
            "camera_id": camera_id,
            "camera_name": label,
            "person_ids": sorted(cluster),
            "persons_count": len(cluster),
            "approach_speed_px_s": round(best_speed, 1),
            "min_distance_px": round(
                min(
                    d
                    for (a, b), d in pair_min_distance.items()
                    if a in cluster and b in cluster
                ),
                1,
            ),
        })
    return events


def evaluate_frame(
    camera_id: int,
    camera_name: str,
    persons: list[dict],
) -> list[dict[str, Any]]:
    """تحدّث حالة المشاجرات/التجمهر لهذا الإطار وتعيد الأحداث المُطلَقة.

    كل عنصر جاهز للـ EventLogger بنسق أحداث anomaly نفسه — بلا I/O هنا.
    """
    if not bool(Config.ENABLE_FIGHT_DETECTION):
        return []

    ts = time.time()
    label = _camera_label(camera_id, camera_name)

    # تحديث سجل مواقع كل شخص (أساس قياس السرعة والتقارب)
    for person in persons or []:
        tid = person.get("track_id")
        if tid is None:
            continue
        x1, y1, x2, y2 = person["bbox"]
        key = (camera_id, int(tid))
        history = _person_history.get(key)
        if history is None or ts - history[-1]["ts"] > 5.0:
            history = deque(maxlen=_PERSON_HISTORY_MAXLEN)
            _person_history[key] = history
        history.append({
            "ts": ts,
            "cx": (x1 + x2) / 2.0,
            "cy": (y1 + y2) / 2.0,
        })

    events: list[dict[str, Any]] = []

    # --- الشجار (أزواج التلاحم) ---
    events.extend(_check_fights(camera_id, camera_name, persons, ts))

    # --- التجمهر المفاجئ (تقارب المسافات) ---
    surge = _check_crowd_surge(camera_id, camera_name, persons, ts)
    if surge and _cooldown_ok((camera_id, "crowd_surge"), _last_surge, ts):
        events.extend(surge)

    return events
