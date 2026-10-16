import cv2
import asyncio
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from src.detector import Detector
from src.agent import build_agent
from src.alert import Alert
from src.logger import EventLogger
from src.config import Config

logger = logging.getLogger(__name__)

class CameraManager:
    def __init__(self, cameras: list):
        """
        cameras: list of dicts [{"id": 1, "name": "Gate", "url": "http://..."}, ...]
        """
        self.cameras = cameras
        self.detector = Detector()
        self.agent = build_agent()
        self.executor = ThreadPoolExecutor(max_workers=len(cameras))
        self.running = True
        self.alerts = Alert()
        # حفظ الحلقة الرئيسية للاستخدام في الخيوط
        self.main_loop = asyncio.get_event_loop()

    async def process_camera(self, cam_info):
        """معالجة كاميرا واحدة بشكل مستمر"""
        cam_id = cam_info["id"]
        name = cam_info.get("name", f"Camera {cam_id}")
        url = cam_info["url"]

        cap = cv2.VideoCapture(url)
        if not cap.isOpened():
            logger.error(f"❌ فشل فتح الكاميرا {cam_id} ({name})")
            return

        logger.info(f"✅ بدء معالجة الكاميرا {cam_id}: {name}")

        while self.running:
            ret, frame = cap.read()
            if not ret:
                logger.warning(f"⚠️ انقطاع البث للكاميرا {cam_id}")
                cap.release()
                time.sleep(5)
                cap = cv2.VideoCapture(url)
                continue

            if frame.shape[0] > 480:
                frame = cv2.resize(frame, (640, 480))

            loop = asyncio.get_event_loop()
            state = {
                "frame": frame,
                "persons": [],
                "alert_sent": False,
                "image_path": "",
                "timestamp": "",
                "camera_id": cam_id,
                "event_type": "intrusion",
                "description": "",
                "main_loop": self.main_loop  # ← تمرير الحلقة الرئيسية
            }
            result = await loop.run_in_executor(self.executor, self.agent.invoke, state)

            if result.get("alert_sent"):
                # إرسال تنبيه مع معرف الكاميرا
                message = f"🚨 {result.get('description', 'تسلل')} في {name} الساعة {result['timestamp']}"
                self.alerts.send_telegram(result["image_path"], message)
                logger.info(f"🔴 تنبيه من الكاميرا {cam_id}")

            await asyncio.sleep(0.05)

        cap.release()
        logger.info(f"🛑 توقفت معالجة الكاميرا {cam_id}")

    async def run_all(self):
        """تشغيل جميع الكاميرات بشكل متوازٍ"""
        tasks = [self.process_camera(cam) for cam in self.cameras]
        await asyncio.gather(*tasks)

    def stop(self):
        self.running = False