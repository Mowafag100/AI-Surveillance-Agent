import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    CAMERA_URL = os.getenv("CAMERA_URL", "http://172.35.33.208:8080/video")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
    ALERT_COOLDOWN = int(os.getenv("ALERT_COOLDOWN", 30))
    MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", 0.5))
    MODEL_PATH = "models/yolov8n.pt"
    ALERTS_DIR = "alerts"
    LOGS_DIR = "logs"
    ZONE_DWELL_TIME = int(os.getenv("ZONE_DWELL_TIME", 2))
    
    # إعدادات المنطقة الحساسة
    ZONE_TOP_LEFT_X = int(os.getenv("ZONE_TOP_LEFT_X", 100))
    ZONE_TOP_LEFT_Y = int(os.getenv("ZONE_TOP_LEFT_Y", 100))
    ZONE_BOTTOM_RIGHT_X = int(os.getenv("ZONE_BOTTOM_RIGHT_X", 400))
    ZONE_BOTTOM_RIGHT_Y = int(os.getenv("ZONE_BOTTOM_RIGHT_Y", 300))

    # إعدادات التوقيت (Time-based Alerts)
    ALERT_START_HOUR = int(os.getenv("ALERT_START_HOUR", 0))
    ALERT_END_HOUR = int(os.getenv("ALERT_END_HOUR", 23))   # ← أضف هذا السطر