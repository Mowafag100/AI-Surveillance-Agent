import cv2
import time
import threading
import logging
from src.config import Config

logger = logging.getLogger(__name__)

class Camera:
    def __init__(self, url=None, stop_event=None):
        self.url = url or Config.CAMERA_URL
        self.cap = None
        # لتشغيل الوكيل متعدد الكاميرات: إيقاف الحلقات عند طلب الإغلاق
        # (بقيمة None يبقى السلوك القديم تماماً — إعادة محاولة لانهائية)
        self.stop_event = stop_event

    def connect(self):
        """فتح الاتصال بالكاميرا مع إعادة محاولة (تتوقف عند stop_event)"""
        while not (self.stop_event is not None and self.stop_event.is_set()):
            try:
                self.cap = cv2.VideoCapture(self.url)
                if self.cap.isOpened():
                    logger.info(f"✅ تم الاتصال بالكاميرا ({self.url})")
                    return True
            except Exception as e:
                logger.error(f"❌ فشل الاتصال: {e}")
            logger.warning("⏳ إعادة محاولة الاتصال خلال 5 ثوانٍ...")
            time.sleep(5)
        return False

    def read_frame(self):
        """قراءة إطار واحد مع إعادة محاولة عند الفشل"""
        if self.stop_event is not None and self.stop_event.is_set():
            return None
        if self.cap is None:
            self.connect()
            if self.cap is None or not self.cap.isOpened():
                return None
        ret, frame = self.cap.read()
        if not ret:
            logger.warning("⚠️ فشل قراءة الإطار، إعادة الاتصال...")
            self.connect()
            if self.cap is None or not self.cap.isOpened():
                return None
            ret, frame = self.cap.read()
        return frame if ret else None

    def update_url(self, new_url, reconnect=True):
        """تغيير رابط الكاميرا (Hot Reload).

        reconnect=True (السلوك القديم): إصدار فوري وإعادة اتصال متزامنة
        (قد تسدّ على روابط ميتة). reconnect=False: فقط تحرير القديم
        وضبط الرابط الجديد — خيط مالك الكاميرا يعيد الاتصال عبر حلقة
        القراءة التالية (آمن مع reconcile متعدد الكاميرات)."""
        if not new_url or new_url == self.url:
            return False
        logger.info(f"📷 تغيير رابط الكاميرا: {self.url} → {new_url}")
        self.release()
        self.url = new_url
        if reconnect and self.stop_event is None:
            # السلوك التاريخي (اتصال متزامن) يبقى كاميراً فردية بلا stop
            return self.connect()
        return True

    def release(self):
        if self.cap:
            self.cap.release()
            logger.info(f"📹 تم إغلاق الكاميرا ({self.url})")
            self.cap = None
