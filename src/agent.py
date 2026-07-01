import time
_last_alert_time = 0
from langgraph.graph import StateGraph, END
from typing import TypedDict, List
import logging
from src.config import Config
from src.detector import Detector
from src.alert import Alert
from src.logger import EventLogger

logger = logging.getLogger(__name__)

class SurveillanceState(TypedDict):
    frame: any
    persons: List[dict]
    alert_sent: bool
    image_path: str
    timestamp: str

def detect_node(state: SurveillanceState) -> SurveillanceState:
    """عقدة الكشف: تحليل الإطار لكشف الأشخاص"""
    detector = Detector()
    persons = detector.detect_persons(state["frame"])
    state["persons"] = persons
    return state

def is_inside_zone(bbox, zone):
    """
    تتحقق مما إذا كان مركز الجسم داخل المنطقة المحددة.
    bbox: [x1, y1, x2, y2] (إحداثيات المستطيل المحيط بالشخص)
    zone: (x1, y1, x2, y2) (إحداثيات المنطقة)
    """
    x1, y1, x2, y2 = bbox
    zx1, zy1, zx2, zy2 = zone
    cx = (x1 + x2) / 2  # مركز x
    cy = (y1 + y2) / 2  # مركز y
    return zx1 <= cx <= zx2 and zy1 <= cy <= zy2

def decision_node(state: SurveillanceState) -> SurveillanceState:
    global _last_alert_time
    if not state["persons"]:
        state["alert_sent"] = False
        return state

    zone = (
        Config.ZONE_TOP_LEFT_X,
        Config.ZONE_TOP_LEFT_Y,
        Config.ZONE_BOTTOM_RIGHT_X,
        Config.ZONE_BOTTOM_RIGHT_Y
    )

    now = time.time()
    for person in state["persons"]:
        if is_inside_zone(person["bbox"], zone):
            # تحقق من المهلة (Cooldown)
            if now - _last_alert_time >= Config.ALERT_COOLDOWN:
                import cv2
                from datetime import datetime
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = f"alerts/alert_{ts}.jpg"
                cv2.imwrite(path, state["frame"])
                state["image_path"] = path
                state["timestamp"] = ts
                state["alert_sent"] = True
                _last_alert_time = now
                break
            else:
                state["alert_sent"] = False
                break
    else:
        state["alert_sent"] = False

    return state
    
def alert_node(state: SurveillanceState) -> SurveillanceState:
    """عقدة التنبيه: إرسال التنبيه عبر Telegram"""
    if state["alert_sent"] and state["image_path"]:
        alert = Alert()
        if alert.is_cooldown_over():
            alert.send_telegram(
                state["image_path"],
                f"🚨 تسلل محتمل الساعة {state['timestamp']}"
            )
            logger_obj = EventLogger()
            logger_obj.log_event("intrusion", {"timestamp": state["timestamp"]}, state["image_path"])
    return state

def build_agent():
    """بناء وكيل LangGraph للتسلل"""
    builder = StateGraph(SurveillanceState)
    builder.add_node("detect", detect_node)
    builder.add_node("decision", decision_node)
    builder.add_node("alert", alert_node)

    builder.set_entry_point("detect")
    builder.add_edge("detect", "decision")
    builder.add_edge("decision", "alert")
    builder.add_edge("alert", END)

    return builder.compile()
