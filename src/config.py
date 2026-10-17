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
        cameras.append({
            "id": int(item.get("id", index)),
            "name": str(item.get("name") or f"الكاميرا {index}"),
            "url": str(item["url"]).strip(),
        })
    return cameras


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
    "MIN_CONFIDENCE": ("MIN_CONFIDENCE", float, 0.5),
    "FALL_ASPECT_RATIO_THRESHOLD": ("FALL_ASPECT_RATIO_THRESHOLD", float, 1.2),
    "FIGHT_SPEED_THRESHOLD": ("FIGHT_SPEED_THRESHOLD", int, 100),
    "FIGHT_DISTANCE_THRESHOLD": ("FIGHT_DISTANCE_THRESHOLD", int, 50),
    "ZONE_DWELL_TIME": ("ZONE_DWELL_TIME", float, 2.0),
    # المنطقة الحساسة
    "ZONE_TOP_LEFT_X": ("ZONE_TOP_LEFT_X", int, 100),
    "ZONE_TOP_LEFT_Y": ("ZONE_TOP_LEFT_Y", int, 100),
    "ZONE_BOTTOM_RIGHT_X": ("ZONE_BOTTOM_RIGHT_X", int, 400),
    "ZONE_BOTTOM_RIGHT_Y": ("ZONE_BOTTOM_RIGHT_Y", int, 300),
    # التوقيت
    "ALERT_START_HOUR": ("ALERT_START_HOUR", int, 0),
    "ALERT_END_HOUR": ("ALERT_END_HOUR", int, 23),
    # عرض نافذة الفيديو (false في Docker/الخوادم)
    "SHOW_PREVIEW": ("SHOW_PREVIEW", lambda v: str(v).lower() in ("1", "true", "yes"), False),
}


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

    @classmethod
    def reload(cls) -> None:
        """إعادة تحميل كل الإعدادات ديناميكياً دون إعادة تشغيل العملية"""
        cls._apply()
        logger.info("🔄 تمت إعادة تحميل الإعدادات من المعاد تعديلها")


# التهيئة الأولية عند الاستيراد (تحاكي السلوك القديم تماماً مع config.json فارغ)
Config._apply()
