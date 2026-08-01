import cv2
import asyncio
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from src.detector import Detector
from src.agent import build_agent
from src.database import log_event, update_camera_status
from src.config import Config

logger = logging.getLogger(__name__)

class CameraPool:
    def __init__(self, cameras: list):
        self.cameras = cameras
        self.detector = Detector()
        self.agent = build_agent()
        self.executor = ThreadPoolExecutor(max_workers=len(cameras))
        self.running = True

    async def process_camera(self, cam_info):
        cam_id = cam_info["id"]
        url = cam_info["url"]
        cap = cv2.VideoCapture(url)
        if not cap.isOpened():
            logger.error(f"❌ فشل فتح الكاميرا {cam_id}")
            await update_camera_status(cam_id, "error")
            return

        logger.info(f"✅ بدء معالجة الكاميرا {cam_id}")
        await update_camera_status(cam_id, "online")

        while self.running:
            ret, frame = cap.read()
            if not ret:
                logger.warning(f"⚠️ انقطاع البث للكاميرا {cam_id}")
                await update_camera_status(cam_id, "offline")
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
                "camera_id": cam_id
            }
            result = await loop.run_in_executor(self.executor, self.agent.invoke, state)

            if result.get("alert_sent"):
                await log_event(
                    camera_id=cam_id,
                    image_path=result["image_path"],
                    confidence=0.8,
                    description=f"Intrusion on {cam_info.get('name', cam_id)} at {result['timestamp']}"
                )
                logger.info(f"🔴 تسلل في الكاميرا {cam_id}")

            await asyncio.sleep(0.05)

        cap.release()
        logger.info(f"🛑 توقفت معالجة الكاميرا {cam_id}")

    async def run_all(self):
        tasks = [self.process_camera(cam) for cam in self.cameras]
        await asyncio.gather(*tasks)