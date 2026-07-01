import cv2
import time
import logging
import sys
import os
import torch

# إعداد التسجيل
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/system.log")
    ]
)
logger = logging.getLogger(__name__)

# إضافة مجلد src إلى المسار
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.camera import Camera
from src.agent import build_agent

# تقليل عدد خيوط المعالجة لتخفيف الضغط
torch.set_num_threads(1)

def main():
    logger.info("🚀 بدء تشغيل نظام المراقبة الذكي")

    camera = Camera()
    camera.connect()

    agent = build_agent()
    show_video = True

    while True:
        frame = camera.read_frame()
        if frame is None:
            continue

        # تقليل حجم الإطار لتخفيف الضغط على المعالج
        if frame.shape[0] > 480:
            frame = cv2.resize(frame, (640, 480))

        state = {
            "frame": frame,
            "persons": [],
            "alert_sent": False,
            "image_path": "",
            "timestamp": ""
        }
        result = agent.invoke(state)

        if result.get("alert_sent"):
            logger.info("🔴 تم اكتشاف تسلل!")

        if show_video:
            cv2.imshow("AI Surveillance", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        time.sleep(0.05)  # تقليل الحمل

    camera.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()