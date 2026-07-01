import requests
import logging
from datetime import datetime
from src.config import Config

logger = logging.getLogger(__name__)

class Alert:
    def __init__(self):
        self.token = Config.TELEGRAM_BOT_TOKEN
        self.chat_id = Config.TELEGRAM_CHAT_ID
        self.last_alert_time = 0

    def send_telegram(self, image_path, message):
        """إرسال تنبيه عبر Telegram مع صورة"""
        if not self.token or not self.chat_id:
            logger.error("❌ Telegram credentials missing")
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
        try:
            with open(image_path, "rb") as f:
                files = {"photo": f}
                data = {"chat_id": self.chat_id, "caption": message}
                resp = requests.post(url, files=files, data=data, timeout=10)
                if resp.status_code == 200:
                    logger.info("✅ تم إرسال التنبيه إلى Telegram")
                    return True
                else:
                    logger.error(f"❌ فشل الإرسال: {resp.text}")
        except Exception as e:
            logger.error(f"❌ خطأ في الإرسال: {e}")
        return False

    def is_cooldown_over(self):
        """تأكد من مرور وقت كافٍ بين التنبيهات"""
        from time import time
        if time() - self.last_alert_time > Config.ALERT_COOLDOWN:
            self.last_alert_time = time()
            return True
        return False
