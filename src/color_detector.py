"""كشف اللون الممنوع في المناطق الحساسة (Restricted Color Detection).

الدوال نقية (بلا حالة) — الحالة/المهلات/قرارات الموظفين في src/agent.py
عقدة color_zone_node:

1) color_match_percentage: تقصّ منطقة الجذع (Torso) من صندوق الشخص —
   من 18% إلى 62% من ارتفاع الـ bbox (يتجاوز الرأس وينتهي قبل الساقين) —
   ثم تحوّلها إلى HSV وتبني Mask للون الهدف بمسافة إقليدية ≤ COLOR_TOLERANCE
   (فرق الصبغة دائري على مدى 0-179 في OpenCV)، وتعيد نسبة البكسلات
   المطابقة من مجموع بكسلات الجذع (%).

2) check_forbidden_color: يجمع النسبة مع عتبة COLOR_MIN_PERCENTAGE
   (افتراضي 30%) ويعيد True/False.

الإحداثيات بكسل على إطار المعالجة (640×480) — نفس إطار YOLO، والمنطقة
الحساسة ZONE_* تحسب على نفس الإطار في src/agent.py.
"""

import cv2
import numpy as np

from src.config import Config

# حدود الجذع ضمن ارتفاع صندوق الشخص (نسبة من الأعلى)
_TORSO_TOP_RATIO = 0.18   # تحت الرأس/الوجه
_TORSO_BOTTOM_RATIO = 0.62  # قبل الساقين


def _hex_to_hsv(target_hex: str) -> tuple[int, int, int]:
    """تحويل #RRGGBB إلى (H, S, V) بمدى OpenCV (H ضمن 0-179)"""
    text = str(target_hex or "").strip().lstrip("#")
    if len(text) != 6:
        raise ValueError(f"لون غير صالح: {target_hex!r}")
    r, g, b = (int(text[i : i + 2], 16) for i in (0, 2, 4))
    bgr_pixel = np.uint8([[[b, g, r]]])
    h, s, v = cv2.cvtColor(bgr_pixel, cv2.COLOR_BGR2HSV)[0][0]
    return int(h), int(s), int(v)


def color_match_percentage(
    frame: np.ndarray,
    person_bbox: list[float],
    target_hex: str,
    tolerance: int,
) -> float | None:
    """نسبة البكسلات المطابقة للون الهدف في منطقة الجذع (%).

    None إن كان الإطار/القصّ غير صالح — المستدعي يقرر (fail-safe: لا تطابق).
    """
    if frame is None or frame.size == 0:
        return None
    x1, y1, x2, y2 = (float(v) for v in person_bbox)
    height = max(1.0, y2 - y1)
    width = max(1.0, x2 - x1)

    # قصّ الجذع: شريط أفقي تحت الرأس وقبل الساقين
    fy1 = int(max(0.0, y1 + _TORSO_TOP_RATIO * height))
    fy2 = int(min(frame.shape[0], y1 + _TORSO_BOTTOM_RATIO * height))
    fx1 = int(max(0.0, x1))
    fx2 = int(min(frame.shape[1], x2))
    if fy2 - fy1 < 4 or fx2 - fx1 < 4:
        return None  # قصّ صغير جداً — خارج الصورة
    torso = frame[fy1:fy2, fx1:fx2]
    if torso.size == 0:
        return None

    hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
    h_ch, s_ch, v_ch = hsv[:, :, 0].astype(np.int32), hsv[:, :, 1].astype(np.int32), hsv[:, :, 2].astype(np.int32)
    h_target, s_target, v_target = _hex_to_hsv(target_hex)

    # مسافة إقليدية في فضاء HSV — فرق الصبغة دائري (مدى OpenCV 0-179)
    dh = np.abs(h_ch - h_target)
    dh = np.minimum(dh, 180 - dh)
    ds = s_ch - s_target
    dv = v_ch - v_target
    mask = (dh * dh + ds * ds + dv * dv) <= float(tolerance) ** 2

    total = mask.size
    if total == 0:
        return None
    return float(np.count_nonzero(mask)) / float(total) * 100.0


def check_forbidden_color(
    frame: np.ndarray,
    person_bbox: list[float],
    target_hex: str,
    tolerance: int,
) -> bool:
    """هل يرتدي الشخص اللون الممنوع؟ نسبة الجذع ≥ COLOR_MIN_PERCENTAGE"""
    percentage = color_match_percentage(
        frame, person_bbox, target_hex, tolerance
    )
    if percentage is None:
        return False
    return percentage >= float(Config.COLOR_MIN_PERCENTAGE)
