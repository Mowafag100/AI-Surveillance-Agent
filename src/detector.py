from ultralytics import YOLO
import logging
from src.config import Config

logger = logging.getLogger(__name__)

class Detector:
    def __init__(self):
        self.model = YOLO(Config.MODEL_PATH)
        self.person_class_id = 0  # COCO: person = 0

    def detect_persons(self, frame):
        """كشف الأشخاص في الإطار والعودة بقائمة الإطارات المحيطة بهم"""
        if frame is None:
            return []
        results = self.model(frame, verbose=False)
        persons = []
        for box in results[0].boxes:
            if box.cls == self.person_class_id and box.conf >= Config.MIN_CONFIDENCE:
                persons.append({
                    "bbox": box.xyxy[0].tolist(),
                    "confidence": float(box.conf)
                })
        return persons
