import json
import os
import threading
from datetime import datetime
from src.config import Config

class EventLogger:
    def __init__(self):
        os.makedirs(Config.LOGS_DIR, exist_ok=True)
        os.makedirs(Config.ALERTS_DIR, exist_ok=True)
        self.log_file = os.path.join(Config.LOGS_DIR, "events.jsonl")
        # عدة ثريدات (كاميرات) تكتب نفس الملف — منع تكسّر الأسطر
        self._lock = threading.Lock()

    def log_event(self, event_type, details, image_path=None):
        """تسجيل حدث (تسلل، خطأ، بدء تشغيل) بصيغة JSON"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
            "details": details,
            "image": image_path
        }
        with self._lock:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
