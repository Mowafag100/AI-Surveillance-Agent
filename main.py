import cv2
import time
import logging
import sys
import os
import threading
import signal
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
from src.config import Config, get_config_mtime

# تقليل عدد خيوط المعالجة لتخفيف الضغط
torch.set_num_threads(1)


_running = True


def _handle_stop(signum, _frame):
    """التقاط SIGTERM/SIGINT للإيقاف الرشيق داخل الحاويات."""
    global _running
    logger.info(f"🛑 استُلمت إشارة الإيقاف ({signum})، جارٍ الإنهاء...")
    _running = False


class _CameraWorker(threading.Thread):
    """دورة معالجة كاملة لكاميرا واحدة (YOLO → Zone → Dwell → Alert).

    لكل كاميرا ثريد مستقل وCamera خاصة به؛ الـ Agent المشترك بينها
    (الحالة تُمرّر لكل استدعاء، والمؤقتات داخل agent.py لكل كاميرا حسب
    camera_id). الإيقاف عبر حدث مستقل لكل كاميرا (حذف فردي من الواجهة).
    """

    def __init__(self, camera_id: int, camera_name: str, url: str, agent):
        super().__init__(daemon=True, name=f"camera-{camera_id}")
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.stop = threading.Event()
        self.agent = agent
        self.camera = Camera(url, stop_event=self.stop)

    def run(self):
        logger.info(f"▶️ بدء معالجة الكاميرا [{self.camera_name}] ({self.camera.url})")
        self.camera.connect()
        while _running and not self.stop.is_set():
            frame = self.camera.read_frame()
            if frame is None:
                self.stop.wait(0.05)
                continue

            # تقليل حجم الإطار لتخفيف الضغط على المعالج
            if frame.shape[0] > 480:
                frame = cv2.resize(frame, (640, 480))

            state = {
                "frame": frame,
                "persons": [],
                "alert_sent": False,
                "image_path": "",
                "timestamp": "",
                "camera_id": self.camera_id,
                "camera_name": self.camera_name,
            }
            try:
                result = self.agent.invoke(state)
                if result.get("alert_sent"):
                    logger.info(f"🔴 تم اكتشاف تسلل! [{self.camera_name}]")
            except Exception as exc:
                # عزل عطل كاميرا واحدة عن البقية (الشبكة، النموذج ...)
                logger.error(f"❌ عطل معالجة [{self.camera_name}]: {exc}")
                self.stop.wait(1)

            # FPS limit: مهلة بين الإطارات لكل كاميرا لتجنب 100% CPU
            self.stop.wait(0.05)

        self.camera.release()
        logger.info(f"⏹️ أُوقفت معالجة الكاميرا [{self.camera_name}]")


def _camera_key(spec: dict[str, object]) -> tuple[str, str]:
    """هوية ثابتة للكاميرا داخل workers: (id, name). تغيّر الرابط ضمن
    نفس الهوية يُطبَّق حياً عبر Camera.update_url دون إعادة تشغيل."""
    return (str(spec.get("id")), str(spec.get("name") or ""))


def main():
    logger.info("🚀 بدء تشغيل نظام المراقبة الذكي (متعدد الكاميرات)")
    if Config.SHOW_PREVIEW:
        logger.warning("⚠️ SHOW_PREVIEW غير مدعوم مع كاميرات متعددة — تجاهُله")

    agent = build_agent()

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    workers: dict[tuple[str, str], _CameraWorker] = {}
    last_config_mtime = get_config_mtime()

    def start_worker(spec: dict[str, object]) -> None:
        worker = _CameraWorker(
            camera_id=int(spec.get("id", 1)),
            camera_name=str(spec.get("name") or "كاميرا"),
            url=str(spec.get("url") or ""),
            agent=agent,
        )
        workers[_camera_key(spec)] = worker
        worker.start()

    def reconcile_cameras() -> None:
        """Hot Reload: مطابقة ثريدات الكاميرات مع قائمة Config.
        - الحذف: إغلاق الثريد (كاميرا غير موجودة في القائمة الجديدة)
        - الإضافة: ثريد جديد دون إيقاف الوكيل
        - تغيير الرابط لنفس الهوية: إعادة اتصال حية عبر update_url
        """
        specs = Config.get_cameras()
        current = {_camera_key(spec): spec for spec in specs}

        # 1) إغلاق المحذوف (المفتاح غير موجود بعد التعديل)
        for key in list(workers):
            if key not in current:
                worker = workers.pop(key)
                logger.info(f"🗑️ إغلاق الكاميرا [{worker.camera_name}]")
                worker.stop.set()
                worker.join(timeout=5)
                if worker.is_alive():
                    logger.warning(f"⚠️ الثريد [{worker.camera_name}] لم ينتهِ بعد")

        # 2) تغيير الرابط داخل نفس الهوية → تبديل حي دون حجب:
        #    تحرير القديم وضبط الرابط، وثريد الكاميرا يعيد الاتصال بنفسه
        #    (reconnect=False — وألا تسدّ reconcile على رابط ميت لانهائياً)
        fresh = {key: spec for key, spec in current.items() if key in workers}
        for key, spec in fresh.items():
            worker = workers[key]
            new_url = str(spec.get("url") or "")
            if new_url and new_url != worker.camera.url:
                worker.camera.update_url(new_url, reconnect=False)

        # 3) فتح الجديد
        for key, spec in current.items():
            if key in workers:
                continue
            logger.info(f"🆕 فتح الكاميرا [{spec.get('name')}] ({spec.get('url')})")
            start_worker(spec)

    # فتح الكاميرات الابتدائية ثم مراقبة config.json كل 5 ثوانٍ
    reconcile_cameras()
    if not workers:
        logger.warning("⚠️ لا توجد كاميرات مضبوطة — التقط التغييرات من config.json")

    try:
        while _running:
            current_mtime = get_config_mtime()
            if current_mtime != last_config_mtime:
                last_config_mtime = current_mtime
                logger.info("🔄 تغيّر config.json — مطابقة الكاميرات (Hot Reload)")
                Config.reload()
                reconcile_cameras()
            time.sleep(5)
    finally:
        for worker in list(workers.values()):
            worker.stop.set()
        for worker in list(workers.values()):
            worker.join(timeout=5)
        logger.info("👋 أُنهيت كل ثريدات الكاميرات")


if __name__ == "__main__":
    main()
