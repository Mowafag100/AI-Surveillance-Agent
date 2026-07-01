import cv2
import time
import logging
from src.config import Config

logger = logging.getLogger(__name__)

class Camera:
    def __init__(self, url=None):
        self.url = url or Config.CAMERA_URL
        self.cap = None

    def connect(self):
        """فتح الاتصال بالكاميرا مع إعادة محاولة"""
        while True:
            try:
                self.cap = cv2.VideoCapture(self.url)
                if self.cap.isOpened():
                    logger.info("✅ تم الاتصال بالكاميرا")
                    return True
            except Exception as e:
                logger.error(f"❌ فشل الاتصال: {e}")
            logger.warning("⏳ إعادة محاولة الاتصال خلال 5 ثوانٍ...")
            time.sleep(5)

    def read_frame(self):
        """قراءة إطار واحد مع إعادة محاولة عند الفشل"""
        if self.cap is None:
            self.connect()
        ret, frame = self.cap.read()
        if not ret:
            logger.warning("⚠️ فشل قراءة الإطار، إعادة الاتصال...")
            self.connect()
            ret, frame = self.cap.read()
        return frame if ret else None

    def release(self):
        if self.cap:
            self.cap.release()
            logger.info("📹 تم إغلاق الكاميرا")
