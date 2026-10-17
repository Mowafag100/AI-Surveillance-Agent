from ultralytics import YOLO
import logging
import threading
from src.config import Config

logger = logging.getLogger(__name__)

# تحميل النموذج مرة واحدة لكل العملية (كان يُحمّل عند كل إطار!) — أساسي
# لتشغيل كاميرات متعددة دون إعادة تحميل YOLO لكل كاميرا/إطار
_model = None
_inference_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        _model = YOLO(Config.MODEL_PATH)
    return _model


class Detector:
    def __init__(self):
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
