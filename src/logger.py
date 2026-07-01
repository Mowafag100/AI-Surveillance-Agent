import json
import os
from datetime import datetime
from src.config import Config

class EventLogger:
    def __init__(self):
        os.makedirs(Config.LOGS_DIR, exist_ok=True)
        os.makedirs(Config.ALERTS_DIR, exist_ok=True)
        self.log_file = os.path.join(Config.LOGS_DIR, "events.jsonl")

    def log_event(self, event_type, details, image_path=None):
        """تسجيل حدث (تسلل، خطأ، بدء تشغيل) بصيغة JSON"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
            "details": details,
            "image": image_path
        }
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
