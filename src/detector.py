from pathlib import Path

from ultralytics import YOLO
import logging
import threading
from src.config import Config

logger = logging.getLogger(__name__)

# تحميل النموذج مرة واحدة لكل العملية (كان يُحمّل عند كل إطار!) — أساسي
# لتشغيل كاميرات متعددة دون إعادة تحميل YOLO لكل كاميرا/إطار
_model = None
_model_size: str | None = None  # المقاس المحمّل حالياً (لاكتشاف التبديل الحي)
_inference_lock = threading.Lock()


def _resolve_model_path(size: str) -> str:
    """مسار أوزان الحجم المطلوب: تفضيل مجلد models/ المربوط أولاً،
    وإلا الاسم الرسمي (ultralytics يسحبه تلقائياً إلى مجلد العمل)."""
    local = Path(getattr(Config, "MODEL_PATH", "models/yolov8n.pt")).parent / f"yolov8{size}.pt"
    return str(local) if local.is_file() else f"yolov8{size}.pt"


def _get_model():
    """النموذج المشترك — يعيد التحميل تلقائياً إذا تغيّر Config.MODEL_SIZE
    (Hot Reload عبر الواجهة) دون إعادة تشغيل الوكيل."""
    global _model, _model_size
    size = str(getattr(Config, "MODEL_SIZE", "n"))
    if _model is None or _model_size != size:
        path = _resolve_model_path(size)
        logger.info(f"🧠 تحميل نموذج YOLO ({size}) من: {path}")
        _model = YOLO(path)
        _model_size = size
    return _model


class Detector:
    def __init__(self):
        # القفل نفسه يحمي التبديل الحي بين المقاسات من فحصـين متوازيين
        with _inference_lock:
            self.model = _get_model()
        self.person_class_id = 0  # COCO: person = 0

    def detect_persons(self, frame):
        """كشف الأشخاص في الإطار والعودة بقائمة الإطارات المحيطة بهم"""
        if frame is None:
            return []
        # YOLO ليس آمناً موثقاً للتنفيذ المتوازي من نفس الكائن — التسلسل هنا
        with _inference_lock:
            results = self.model(frame, verbose=False)
        persons = []
        for box in results[0].boxes:
            if box.cls == self.person_class_id and box.conf >= Config.MIN_CONFIDENCE:
                persons.append({
                    "bbox": box.xyxy[0].tolist(),
                    "confidence": float(box.conf)
                })
        return persons
