"""التعرف على الوجوه للموظفين — Offline حتمي دون تنزيل نماذج خارجية.

كاشف الوجوه: YuNet (FaceDetectorYN — نموذج onnx ~230KB مضمَّن في
src/assets، الترخيص Apache-2.0 من opencv_zoo) — متين مع زوايا/إضاءات
كاميرات المراقبة، عكس Haar (فشل في 14/15 لقطة حقيقية هنا). عند غياب
النموذج تتراجع إلى Haar Cascade، وعند فشل الاثنين يبقى البرنامج ماشياً
(كل الناس "Unknown" — تنبيه التسلل يعمل دائماً fail-closed).

خط أنابيب البصمة (نفس القصّ في التسجيل والتشغيل — مقارنة منصّقة):
  رماديات 128×128 → equalizeHist (مقاومة الإضاءة) → خريطة LBP (النمط
  المحلي الثنائي الثماني الطور) → هيستوغرام مقسمة 4×4 خلايا (16×256 = متجه
  4096) → تطبيع L2 وتخزينها JSON في عمود employees.face_encoding.

المطابقة: تشابه كوسين ≥ FACE_MATCH_THRESHOLD (افتراضي 0.85 — قابل للضبط
ديناميكياً من config.json؛ خفّضه لزيادة التسامح مع زوايا/إضاءات مختلفة).

الموظفون يُجلبون من PostgreSQL عبر psycopg2 (متزامن — يعمل داخل ثريد
الكاميرا؛ psycopg2 آمن مشاككة الاتصال بين الثريدات مستوى 2). الكاش يُحدَّث
كل EMPLOYEE_CACHE_TTL ثوانٍ أيضاً عند فشل الاستعلام. تعطل قاعدة البيانات أو
غياب DATABASE_URL = تعطيل التعرف بأمان (كل الناس "Unknown") مع بقاء خط
الكشف/التنبيه يعمل كما كان — لا يكسر العمل إطلاقاً.
"""

import json
import logging
import os
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from src.config import Config

logger = logging.getLogger(__name__)

DET_SIZE = 128   # مقاس وجه التسجيل/المطابقة الموحد (رماديات)
CELLS = 4        # 4×4 خلايا → 16 هيستوغرام × 256 خانة = متجه 4096
EMBED_DIM = CELLS * CELLS * 256
EMPLOYEE_CACHE_TTL = 5.0  # ثوانٍ — أقصى تأخير لرصد إضافة/حذف موظف

# YuNet: عتبة ثقة منخفضة (كاميرات المراقبة تعطي ثقة منخفضة 0.2-0.5؛
# الوجوه الكاذبة لا تضر — تُرفض عند المطابقة بلا تجاوز للعتبة)
_YUNET_SCORE = 0.2
_YUNET_MODEL = Path(__file__).resolve().parent / "assets" / "face_detection_yunet_2023mar.onnx"

_cascade = None
_cascade_failed = False
_yunet = None
_yunet_failed = False
_yunet_size: tuple[int, int] = (0, 0)


def _get_yunet(size: tuple[int, int]):
    """كاشف YuNet المشترك — يتحمل تغيّر مقاس الإطار (setInputSize)"""
    global _yunet, _yunet_failed, _yunet_size
    if _yunet_failed:
        return None
    if _yunet is None:
        if not _YUNET_MODEL.is_file():
            logger.debug(f"ℹ️ نموذج YuNet غائب ({_YUNET_MODEL}) — التراجع إلى Haar")
            _yunet_failed = True
            return None
        _yunet = cv2.FaceDetectorYN_create(
            str(_YUNET_MODEL), "", size, score_threshold=_YUNET_SCORE
        )
        _yunet_size = size
    if size != _yunet_size:
        try:
            _yunet.setInputSize(size)
        except cv2.error as exc:
            logger.warning(f"⚠️ فشل ضبط مقاس الكاشف: {exc}")
            _yunet_failed = True
            return None
        _yunet_size = size
    return _yunet


def _detect_faces(bgr: np.ndarray) -> list:
    """مستطيلات الوجوه (x, y, w, h) بإحداثيات الإطار الأصلي

    YuNet المرجع — لقطات المراقبة الحقيقية هنا: وجوهاً في 10/16 إطار
    (عتبة 0.2 على مقاس 640×480 الأصلي) عكس Haar (1/15)؛ ثم سقوط Haar
    مرتخٍ فقط للإطار الذي يفشل فيه YuNet"""
    height, width = bgr.shape[:2]
    detector = _get_yunet((width, height))
    if detector is not None:
        try:
            _, faces = detector.detect(bgr)
            if faces is not None:
                return [
                    (int(f[0]), int(f[1]), int(f[2]), int(f[3]))
                    for f in faces if float(f[14]) >= _YUNET_SCORE
                ]
            # faces None = لا وجوه — نكمل إلى Haar كطبقة سقوط أخيرة
        except cv2.error as exc:
            logger.warning(f"⚠️ خطأ YuNet — التراجع إلى Haar: {exc}")
    # --- سقوط: Haar Cascade بمعاملات مرتخية (لقطات معتمة/زاوية) ---
    global _cascade, _cascade_failed
    if _cascade_failed:
        return []
    if _cascade is None:
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _cascade = cv2.CascadeClassifier(path)
        if _cascade.empty():
            logger.warning(f"⚠️ فشل تحميل كاشف الوجوه ({path}) — التعرف معطّل")
            _cascade_failed = True
            return []
    gray = bgr if bgr.ndim == 2 else cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # detectMultiScale يعيد () عند نتيجة فارغة وndarray عند الوجوه — التوحيد هنا
    return [
        (int(x), int(y), int(w), int(h))
        for (x, y, w, h) in _cascade.detectMultiScale(
            gray, scaleFactor=1.05, minNeighbors=3, minSize=(24, 24)
        )
    ]


def _lbp_encoding(patch: np.ndarray) -> np.ndarray:
    """بصمة الوجه: LBP ثم 4×4 هيستوغرام مقسمة مع تطبيع L2 (متجه 4096)"""
    if patch.ndim == 3:  # BGR قادمة من التسجيل — الرماديات إن كانت ملوّنة
        patch = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(cv2.resize(patch, (DET_SIZE, DET_SIZE)))
    g = np.asarray(gray, dtype=np.int32)
    center = g[1:-1, 1:-1]
    lbp = np.zeros_like(center)
    for bit, (dy, dx) in enumerate((
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1),           (0, 1),
        (1, -1),  (1, 0),  (1, 1),
    )):
        neighbor = np.roll(np.roll(g, dy, axis=0), dx, axis=1)[1:-1, 1:-1]
        lbp |= ((center <= neighbor).astype(np.uint8) << bit)
    cell = DET_SIZE // CELLS
    hists = [
        np.bincount(
            lbp[r * cell:(r + 1) * cell, c * cell:(c + 1) * cell].ravel(),
            minlength=256,
        )
        for r in range(CELLS) for c in range(CELLS)
    ]
    vec = np.concatenate(hists).astype(np.float32)
    return vec / max(np.linalg.norm(vec), 1e-9)


def extract_face_encoding(image_bgr: np.ndarray) -> list[float] | None:
    """بصمة أكبر وجه في الصورة كقائمة floats (لرفع الموظفين عبر API)"""
    if image_bgr is None:
        return None
    faces = _detect_faces(image_bgr)
    if not faces:
        return None
    x, y, w, h = max(faces, key=lambda f: int(f[2]) * int(f[3]))
    face = image_bgr[y:y + h, x:x + w]
    if face.size == 0:
        return None
    return [round(float(v), 6) for v in _lbp_encoding(face)]


# ------------------------- تحميل الموظفين (psycopg2) -------------------------

_cache: list[tuple[int, np.ndarray, str, str]] = []
_cache_ts = 0.0
_db_conn = None
_load_lock = threading.Lock()


def _sync_db_url() -> str | None:
    """DATABASE_URL بصيغة psycopg2 (postgresql:// بدل postgresql+asyncpg://)"""
    url = str(os.getenv("DATABASE_URL") or "").strip()
    if not url:
        return None
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _load_employees() -> list[tuple[int, np.ndarray, str, str]]:
    """[(id, بصمة numpy, الاسم, الوظيفة)] — كاش يُحدَّث كل TTL وعند الفشل"""

    global _cache, _cache_ts, _db_conn
    with _load_lock:
        now = time.time()
        if now - _cache_ts < EMPLOYEE_CACHE_TTL:
            return _cache
        _cache_ts = now  # أعد المحاولة بعد TTL حتى عند الفشل (لا طوفان استعلامات)
        url = _sync_db_url()
        if not url:
            logger.warning("⚠️ DATABASE_URL غير معرّف — التعرف على الوجوه معطّل")
            return _cache
        try:
            import psycopg2
            if _db_conn is None or _db_conn.closed:
                _db_conn = psycopg2.connect(url, connect_timeout=3)
            with _db_conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, COALESCE(role, ''), face_encoding "
                    "FROM employees ORDER BY id"
                )
                rows = cur.fetchall()
            loaded = []
            for r in rows:
                vec = np.asarray(json.loads(r[3]), dtype=np.float32)
                if vec.size != EMBED_DIM:
                    logger.warning(f"⚠️ بصمة موظف {r[0]} بأبعاد خاطئة — تجاهل")
                    continue
                norm = np.linalg.norm(vec)
                if norm < 1e-9:
                    continue
                loaded.append((int(r[0]), vec / norm, str(r[1]), str(r[2])))
            # نجاح فقط يستبدل الكاش — عطل مؤقت في القاعدة يحفظ آخر معلومة
            _cache = loaded
            logger.debug(f"👥 حُمّل {len(loaded)} موظفاً للتعرف على الوجوه")
        except Exception as exc:
            logger.warning(f"⚠️ تعذّر تحميل الموظفين (التعرف يتأخر فقط): {exc}")
        return _cache


class FaceRecognizer:
    """واجهة عديمة الحالة — لكل شخص قصّ وجهه ومطابقته مع قاعدة الموظفين"""

    def recognize(self, frame: np.ndarray | None, persons: list) -> list:
        """إثراء كل شخص في القائمة (in-place): name/role/employee_id
        — "Unknown" عند لا مطابقة أو تعطل التعرف (fail-closed: التنبيه يعمل)"""
        for p in persons:
            p["name"], p["role"], p["employee_id"] = "Unknown", "", None
        if frame is None or not persons:
            return persons
        employees = _load_employees()
        if not employees:
            return persons
        threshold = float(getattr(Config, "FACE_MATCH_THRESHOLD", 0.85) or 0.85)
        faces = _detect_faces(frame)
        for person in persons:
            x1, y1, x2, y2 = [float(v) for v in person["bbox"]]
            best: tuple[float, dict, np.ndarray] | None = None
            for (fx, fy, fw, fh) in faces:
                cx, cy = fx + fw / 2, fy + fh / 2
                if not (x1 <= cx <= x2 and y1 <= cy <= y2):
                    continue  # وجه خارج صندوق الشخص الحالي
                patch = None
                if 0 <= fy and fy + fh <= frame.shape[0] and 0 <= fx and fx + fw <= frame.shape[1]:
                    patch = frame[fy:fy + fh, fx:fx + fw]
                if patch is None or patch.size == 0:
                    continue
                vec = _lbp_encoding(patch)
                matched = max(employees, key=lambda e: float(np.dot(e[1], vec)))
                score = float(np.dot(matched[1], vec))
                if score >= threshold and (best is None or score > best[0]):
                    best = (score, matched, vec)
            if best is not None:
                person["employee_id"] = best[1][0]
                person["name"] = best[1][2]
                person["role"] = best[1][3]
        return persons


_recognizer_instance: FaceRecognizer | None = None


def get_face_recognizer() -> FaceRecognizer:
    """النموذج المشترك لكل ثريدات الكاميرات (خالٍ من الحالة ما عدا الكاش)"""
    global _recognizer_instance
    if _recognizer_instance is None:
        _recognizer_instance = FaceRecognizer()
    return _recognizer_instance
