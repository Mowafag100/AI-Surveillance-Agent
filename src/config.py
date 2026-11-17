import os
import json
import logging
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# مسار ملف الإعدادات الديناميكية: جذر المشروع محلياً، /app/config.json داخل الحاوية
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_JSON_PATH = BASE_DIR / "config.json"

def _parse_cameras(value: Any) -> list[dict[str, Any]]:
    """مضبّط إعداد CAMERAS — يقبل JSON string أو list ويوحّدها:
    [{"id": int, "name": str, "url": str}] — url إلزامي، id/name اختياريان."""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        value = json.loads(text)  # JSONDecodeError فرع من ValueError
    if not isinstance(value, list):
        raise ValueError("CAMERAS يجب أن تكون مصفوفة JSON")
    cameras: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict) or not str(item.get("url") or "").strip():
            # تجاهل الصفوف الفارغة تماماً (مسماة بلا رابط أو غيرها خاطئة)
            if isinstance(item, dict) and str(item.get("name") or "").strip():
                raise ValueError(f"الكاميرا رقم {index} بلا رابط")
            continue
        entry: dict[str, Any] = {
            "id": int(item.get("id", index)),
            "name": str(item.get("name") or f"الكاميرا {index}"),
            "url": str(item["url"]).strip(),
        }
        # الإعدادات المنفردة (Per-Camera Settings) — تُحفظ داخل كائن الكاميرا
        settings = _parse_camera_settings(item.get("id", index), item.get("settings"))
        if settings:
            entry["settings"] = settings
        cameras.append(entry)
    return cameras


def _parse_model_size(value: Any) -> str:
    """مضبّط إعداد MODEL_SIZE — يقبل الحرف n/s/m أو كامل الاسم
    yolov8n/yolov8s/yolov8m ويعيد الحرف فقط ضمن {n,s,m}."""
    text = str(value or "").strip().lower()
    for prefix in ("yolov8", "yolo"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    text = text.replace(".pt", "")
    if text not in ("n", "s", "m"):
        raise ValueError("MODEL_SIZE يجب أن يكون أحد: n، s، m")
    return text


def _parse_hour(value: Any) -> int:
    """ساعة ضمن 0-23 — النافذة تعبر منتصف الليل حين end < start (مسموح)"""
    hour = int(value)
    if not 0 <= hour <= 23:
        raise ValueError("الساعة يجب أن تكون ضمن 0-23")
    return hour


def _parse_port(value: Any) -> int:
    """منفذ SMTP ضمن 1-65535"""
    port = int(value)
    if not 1 <= port <= 65535:
        raise ValueError("منفذ SMTP يجب أن يكون ضمن 1-65535")
    return port


def _parse_hex_color(value: Any) -> str:
    """مضبّط لون سداسي #RRGGBB — يقبل بـ/بلا # ويوحدّه حرفياً كبيراً"""
    text = str(value or "").strip()
    if not text.startswith("#"):
        text = "#" + text
    text = text.upper()
    if len(text) != 7 or any(c not in "0123456789ABCDEF" for c in text[1:]):
        raise ValueError("FORBIDDEN_COLOR_HEX يجب أن يكون بصيغة #RRGGBB")
    return text


def _parse_color_tolerance(value: Any) -> int:
    """تسامح مطابقة اللون ضمن 0-255 (مسافة في فضاء HSV)"""
    tolerance = int(float(value))
    if not 0 <= tolerance <= 255:
        raise ValueError("COLOR_TOLERANCE يجب أن يكون ضمن 0-255")
    return tolerance


def _parse_color_percentage(value: Any) -> float:
    """نسبة ظهور اللون في الجذع ضمن 0-100 (%)"""
    percentage = float(value)
    if not 0.0 <= percentage <= 100.0:
        raise ValueError("COLOR_MIN_PERCENTAGE يجب أن يكون ضمن 0-100")
    return percentage


# تعريف الإعدادات الديناميكية القابلة للتعديل عبر config.json أو الـ API
# الصيغة: الاسم داخل Config -> (اسم متغير البيئة في .env، دالة التحويل، القيمة الافتراضية)
_SETTINGS: dict[str, tuple[str, Callable[[Any], Any], Any]] = {
    # الكاميرا — CAMERAS قائمة الكاميرات الحقيقية، CAMERA_URL توافق خلفي
    "CAMERA_URL": ("CAMERA_URL", str, "http://172.35.33.208:8080/video"),
    "CAMERAS": ("CAMERAS", _parse_cameras, []),
    # Telegram
    "TELEGRAM_BOT_TOKEN": ("TELEGRAM_BOT_TOKEN", str, ""),
    "TELEGRAM_CHAT_ID": ("TELEGRAM_CHAT_ID", str, ""),
    # الكشف والتنبيه
    "ALERT_COOLDOWN": ("ALERT_COOLDOWN", int, 30),
    # مهلة منع التكرار لكل شخص متتبَّع (track_id) بالثواني — تمنع التنبيهات
    # المتكررة لنفس الشخص؛ شخص جديد (track_id آخر) يطلق تنبيهاً فوراً
    "TRACK_COOLDOWN_SEC": ("TRACK_COOLDOWN_SEC", int, 60),
    "MIN_CONFIDENCE": ("MIN_CONFIDENCE", float, 0.3),
    "MODEL_SIZE": ("MODEL_SIZE", _parse_model_size, "n"),
    "FALL_ASPECT_RATIO_THRESHOLD": ("FALL_ASPECT_RATIO_THRESHOLD", float, 1.2),
    "FIGHT_SPEED_THRESHOLD": ("FIGHT_SPEED_THRESHOLD", int, 100),
    "FIGHT_DISTANCE_THRESHOLD": ("FIGHT_DISTANCE_THRESHOLD", int, 50),
    "ZONE_DWELL_TIME": ("ZONE_DWELL_TIME", float, 2.0),
    # التعرف على الوجوه: تشابه كوسين الأدنى لمطابقة موظف — معايرة على لقطات
    # المراقبة الحقيقية: تكرارات الجلسة نفسها 0.82-0.96 والوجوه المختلفة ≤0.79
    "FACE_MATCH_THRESHOLD": ("FACE_MATCH_THRESHOLD", float, 0.85),
    # كشف السلوك الشاذ (src/anomaly.py): مضاد إجمالي + عتبات الكواشف الثلاثة.
    # FALL_ASPECT_RATIO_THRESHOLD أعلاه يُعاد استخدامه لكشف السقوط
    "ENABLE_ANOMALY_DETECTION": (
        "ENABLE_ANOMALY_DETECTION",
        lambda v: str(v).strip().lower() in ("1", "true", "yes", "on"),
        True,
    ),
    # سرعة الجري على إطار المعالجة 640×480 — المشي ~20-60 px/s (تحويل حيّ)
    "RUN_SPEED_THRESHOLD_PX": ("RUN_SPEED_THRESHOLD_PX", float, 150.0),
    # مدة الثبات في مساحة صغيرة قرب المنطقة الحساسة قبل حدث loitering
    "LOITERING_SEC": ("LOITERING_SEC", float, 60.0),
    # نصف قطر «المساحة الصغيرة» حول لوح الشخص (بكسل) — تجاوزها ينهي الجلسة
    "LOITERING_RADIUS_PX": ("LOITERING_RADIUS_PX", float, 40.0),
    # مهلة منع تكرار حدث شاذ لكل (كاميرا، شخص، نوع) — يمنع الغمل كل إطار
    "ANOMALY_EVENT_COOLDOWN": ("ANOMALY_EVENT_COOLDOWN", float, 20.0),
    # مراقبة الصحة: مهلة انقطاع الكاميرا بالثواني قبل اعتبارها غير متصلة
    "CAMERA_TIMEOUT_SEC": ("CAMERA_TIMEOUT_SEC", float, 30),
    # كشف المشاجرات والتجمهر (src/fight_detector.py): مفتاح + عتبات الشجار والتجمهر
    "ENABLE_FIGHT_DETECTION": (
        "ENABLE_FIGHT_DETECTION",
        lambda v: str(v).strip().lower() in ("1", "true", "yes", "on"),
        True,
    ),
    # أقل تداخل (IoU) بين صندوقي شخصين متجاورين يُعدّ تلاحماً جسدياً
    "FIGHT_IOU_THRESHOLD": ("FIGHT_IOU_THRESHOLD", float, 0.2),
    # سرعة الحركة العالية أثناء التلاحم (px/s على إطار 640×480) — تميّز الشجار
    # عن الوقوف الملاصق الهادئ (انتظار/حديث)
    "FIGHT_MOTION_THRESHOLD": ("FIGHT_MOTION_THRESHOLD", float, 50.0),
    # عدد الإطارات المتتالية لاستمرار التداخل قبل إعلان شجار (>5 إطارات)
    "FIGHT_MIN_FRAMES": ("FIGHT_MIN_FRAMES", int, 5),
    # سرعة تقارب المسافات بين الأشخاص (px/s) فوقها يُعدّ التوجّه "تجمهراً مفاجئاً"
    "CROWD_CONVERGENCE_THRESHOLD": ("CROWD_CONVERGENCE_THRESHOLD", float, 80.0),
    # أقل عدد أشخاص يتقاربون نحو نقطة واحدة لاعتباره تجمهراً
    "CROWD_MIN_PERSONS": ("CROWD_MIN_PERSONS", int, 3),
    # نصف قطر التقارب (بكسل) — المسافة الأقصى بين مركزي زوج تُحتسب في العنقود
    "CROWD_CONVERGENCE_RADIUS_PX": ("CROWD_CONVERGENCE_RADIUS_PX", float, 150.0),
    # كشف اللون الممنوع (src/color_detector.py): زيّ محدد داخل المنطقة الحساسة
    "ENABLE_COLOR_DETECTION": (
        "ENABLE_COLOR_DETECTION",
        lambda v: str(v).strip().lower() in ("1", "true", "yes", "on"),
        True,
    ),
    # اللون الممنوع بصيغة سداسية (افتراضي أزرق — زيّ الطلاب)
    "FORBIDDEN_COLOR_HEX": ("FORBIDDEN_COLOR_HEX", _parse_hex_color, "#0000FF"),
    # تسامح تفاوت درجات اللون (مسافة إقليدية في فضاء HSV) — 0 يعني اللون نفسه حرفياً
    "COLOR_TOLERANCE": ("COLOR_TOLERANCE", _parse_color_tolerance, 40),
    # أقل نسبة بكسلات مطابقة في منطقة الجذع (%) لاعتبار الشخص يرتدي اللون
    "COLOR_MIN_PERCENTAGE": ("COLOR_MIN_PERCENTAGE", _parse_color_percentage, 30.0),
    # البريد الإلكتروني (تنبيهات SMTP — اختيارية عبر ENABLE_EMAIL_ALERTS)
    "SMTP_HOST": ("SMTP_HOST", str, ""),
    "SMTP_PORT": ("SMTP_PORT", _parse_port, 587),
    "SMTP_USER": ("SMTP_USER", str, ""),
    "SMTP_PASSWORD": ("SMTP_PASSWORD", str, ""),
    "ALERT_EMAIL_TO": ("ALERT_EMAIL_TO", str, ""),
    "ENABLE_EMAIL_ALERTS": (
        "ENABLE_EMAIL_ALERTS",
        lambda v: str(v).strip().lower() in ("1", "true", "yes", "on"),
        False,
    ),
    # المنطقة الحساسة
    "ZONE_TOP_LEFT_X": ("ZONE_TOP_LEFT_X", int, 100),
    "ZONE_TOP_LEFT_Y": ("ZONE_TOP_LEFT_Y", int, 100),
    "ZONE_BOTTOM_RIGHT_X": ("ZONE_BOTTOM_RIGHT_X", int, 400),
    "ZONE_BOTTOM_RIGHT_Y": ("ZONE_BOTTOM_RIGHT_Y", int, 300),
    # التوقيت
    "ALERT_START_HOUR": ("ALERT_START_HOUR", _parse_hour, 0),
    "ALERT_END_HOUR": ("ALERT_END_HOUR", _parse_hour, 23),
    # عرض نافذة الفيديو (false في Docker/الخوادم)
    "SHOW_PREVIEW": ("SHOW_PREVIEW", lambda v: str(v).lower() in ("1", "true", "yes"), False),
}


# المفاتيح المسموح تجاوزها لكل كاميرا على حدة داخل camera["settings"] في config.json —
# قائمة بيضاء حصراً: أي مفتاح آخر (توكنات/نموذج/بريد…) يُهمل مع تحذير
CAMERA_OVERRIDABLE_SETTINGS: frozenset[str] = frozenset({
    # نافذة التنبيه (تعبر منتصف الليل حين end < start)
    "ALERT_START_HOUR", "ALERT_END_HOUR",
    # المنطقة الحساسة وزمن البقاء
    "ZONE_TOP_LEFT_X", "ZONE_TOP_LEFT_Y",
    "ZONE_BOTTOM_RIGHT_X", "ZONE_BOTTOM_RIGHT_Y",
    "ZONE_DWELL_TIME",
    # مهلات التنبيه ومنع التكرار
    "ALERT_COOLDOWN", "TRACK_COOLDOWN_SEC", "ANOMALY_EVENT_COOLDOWN",
    # اللون الممنوع
    "ENABLE_COLOR_DETECTION", "FORBIDDEN_COLOR_HEX",
    "COLOR_TOLERANCE", "COLOR_MIN_PERCENTAGE",
    # المشاجرات والتجمهر
    "ENABLE_FIGHT_DETECTION", "FIGHT_IOU_THRESHOLD",
    "FIGHT_MOTION_THRESHOLD", "FIGHT_MIN_FRAMES",
    "CROWD_CONVERGENCE_THRESHOLD", "CROWD_MIN_PERSONS",
    "CROWD_CONVERGENCE_RADIUS_PX",
})


def _parse_camera_settings(camera_id: Any, value: Any) -> dict[str, Any]:
    """ضبط كائن settings المنفردة للكاميرا — المفاتيح من القائمة المسموحة
    حصراً والقيم تمر عبر مضبّط الإعداد العام نفسه؛ الفاشل يُهمل مع تحذير
    (لا يُفشل تحميل الكاميرات كلها بسبب إعداد منفرد خاطئ)."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        logger.warning(
            f"⚠️ settings الكاميرا {camera_id} يجب أن تكون كائناً — تم تجاهلها"
        )
        return {}
    parsed: dict[str, Any] = {}
    for key, raw in value.items():
        if key not in CAMERA_OVERRIDABLE_SETTINGS:
            logger.warning(
                f"⚠️ الكاميرا {camera_id}: الإعداد {key} لا يقبل التخصيص — تم تجاهله"
            )
            continue
        try:
            parsed[key] = _SETTINGS[key][1](raw)
        except (ValueError, TypeError) as exc:
            logger.warning(
                f"⚠️ الكاميرا {camera_id}: قيمة غير صالحة لـ {key}: {raw!r} "
                f"({exc}) — تم تجاهلها"
            )
    return parsed


def load_json_config() -> dict[str, Any]:
    """قراءة config.json إذا وُجد — يعيد {} إن لم يوجد أو كان تالفًا"""
    try:
        if CONFIG_JSON_PATH.is_file():
            with CONFIG_JSON_PATH.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
                return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(f"⚠️ تعذّر قراءة config.json: {exc}")
    return {}


def get_config_mtime() -> float:
    """وقت آخر تعديل لـ config.json (0.0 إن لم يوجد) — لكشف التغيير الحيّ"""
    try:
        return CONFIG_JSON_PATH.stat().st_mtime
    except OSError:
        return 0.0


class Config:
    """إعدادات النظام — تُقرأ من config.json أولاً ثم يتراجع إلى (.env) ثم الافتراضي."""

    # ثوابت لا تتغير عبر الـ API (مسارات فقط)
    MODEL_PATH = "models/yolov8n.pt"
    ALERTS_DIR = "alerts"
    LOGS_DIR = "logs"
    _applied_mtime: float = 0.0

    @classmethod
    def ensure_fresh(cls) -> None:
        """لتعديلات config.json من خارج عملية POST نفسها (يدوياً/حاوية أخرى):
        مقارنة mtime المحفوظ مع الحالي — إعادة تحميل مرة واحدة عند الاختلاف فقط."""
        current_mtime = get_config_mtime()
        if current_mtime != cls._applied_mtime:
            cls.reload()

    @classmethod
    def get_cameras(cls) -> list[dict[str, Any]]:
        """قائمة الكاميرات الفعّالة — توافق خلفي: عند فراغ CAMERAS
        تُبنى كاميرا واحدة من CAMERA_URL القديم."""
        cameras = getattr(cls, "CAMERAS", []) or []
        if cameras:
            return cameras
        url = str(getattr(cls, "CAMERA_URL", "") or "")
        if not url:
            return []
        return [{"id": 1, "name": "Camera 1", "url": url}]

    @classmethod
    def _apply(cls) -> None:
        """تطبيق الإعدادات: الأولوية config.json ← os.getenv (.env) ← الافتراضي."""
        overrides = load_json_config()
        for attr, (env_key, parser, default) in _SETTINGS.items():
            source = default
            # 1) القيمة من ملف config.json (الأعلى أولوية)
            if attr in overrides:
                source = overrides[attr]
            # 2) وإلا من متغيرات البيئة/.env
            elif env_key in os.environ:
                source = os.environ[env_key]

            # التحويل مع تجاهل القيم غير الصالحة
            try:
                value = parser(source)
            except (ValueError, TypeError):
                logger.warning(f"⚠️ قيمة غير صالحة للإعداد {attr}: {source!r} — تم تجاهلها")
                value = default
            setattr(cls, attr, value)
        cls._applied_mtime = get_config_mtime()

    @classmethod
    def reload(cls) -> None:
        """إعادة تحميل كل الإعدادات ديناميكياً دون إعادة تشغيل العملية"""
        cls._apply()
        logger.info("🔄 تمت إعادة تحميل الإعدادات من المعاد تعديلها")


# التهيئة الأولية عند الاستيراد (تحاكي السلوك القديم تماماً مع config.json فارغ)
Config._apply()


def get_camera_setting(camera_id: Any, key: str) -> Any:
    """قيمة إعداد لرقم كاميرا محدد مع الرجوع للعام (Fallback):
    1) settings الكاميرا داخل config.json إن احتوت المفتاح (القيمة تعيد
       المرور عبر مضبّط الإعداد نفسه — يتراجع للعام عند فشل التحويل)،
    2) وإلا القيمة العامة Config.<key> (من config.json/.env/الافتراضي).

    قراءة فقط وثريد-آمنة: لا حالة تتغير — كل ثريد كاميرا يقرأ قيمه الخاصة
    أثناء العمل المشترك (Multi-Camera) دون تضارب.
    """
    if key not in _SETTINGS:
        raise KeyError(f"إعداد غير معروف: {key}")
    try:
        wanted = int(camera_id)
    except (TypeError, ValueError):
        return getattr(Config, key)
    for camera in Config.get_cameras():
        try:
            current = int(camera.get("id", -1))
        except (TypeError, ValueError):
            continue
        if current != wanted:
            continue
        overrides = camera.get("settings")
        if isinstance(overrides, dict) and key in overrides:
            parser = _SETTINGS[key][1]
            try:
                return parser(overrides[key])
            except (ValueError, TypeError) as exc:
                logger.warning(
                    f"⚠️ الكاميرا {wanted}: قيمة غير صالحة لـ {key} "
                    f"({overrides[key]!r}: {exc}) — الرجوع للقيمة العامة"
                )
                break
        break
    return getattr(Config, key)
