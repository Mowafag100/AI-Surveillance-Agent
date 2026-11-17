#!/usr/bin/env python
"""محاكاة سيناريوهات الإعدادات المنفردة لكل كاميرا (Per-Camera Settings).

يجري على خط معالجة الوكيل الحقيقي (عقد agent.py: decision/alert/color_zone)
مع config.json مؤقت كامل، وبيانات محاكاة (Mock Data) بلا كاميرات/شبكة/قاعدة:

  س1 (تعارض التوقيت)   : كاميرا 1 نافذتها 18-06، جري الساعة 12:00
                          → بلا تنبيه + قرار alert_suppressed "Outside alert hours".
  س2 (لون ممنوع خارج الوقت): كاميرا 2 نافذتها 08-17 ولونها أحمر، مجهول بأحمر 20:00
                          → بلا تنبيه (خارج نافذة الكاميرا 2).
  س3 (تداخل ناجح)      : نفس الكاميرا 2 الساعة 10:00
                          → تنبيه forbidden_color_intrusion + قرار alert_sent.
  س4 (الرجوع للعام)    : كاميرا 3 بلا إعدادات منفردة والعام يمنع الأزرق
                          → النظام يستخدم إعدادات الـ Global ويُرسل التنبيه.

ملاحظات المحاكاة:
- الوقت مثبّت لكل سيناريو (عقدة agent.datetime) بدل ساعة النظام.
- التسجيل في agent_decisions يُلتقط في الذاكرة (بديل record_agent_decision_sync —
  بلا DATABASE_URL في بيئة الاختبار؛ نفس التوقيع والمنطق).
- Alert/EventLogger بدائل بلا شبكة/ملفات، وcv2.imwrite مُبدَّل (لا لقطات).
- التشغيل: venv/bin/python tests/test_camera_logic.py (من جذر المشروع).
"""

import json
import sys
import tempfile
import types
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import src.agent as agent  # noqa: E402
import src.config as config_module  # noqa: E402
from src.config import get_camera_setting  # noqa: E402

# ---------- عناصر المحاكاة (Mock) ----------

# الساعة المثبّتة للسيناريو الحالي [ساعة، دقيقة]
_NOW = [12, 0]


class _FixedDateTime(datetime):
    """بديل datetime داخل src.agent — يردّ دائماً وقت السيناريو"""

    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return cls(2026, 11, 17, _NOW[0], _NOW[1], 0)


class FakeAlert:
    """بديل Alert — يلتقط التيليجرام/البريد في الذاكرة بلا شبكة"""

    telegram: list[tuple[str, str]] = []
    emails: list[tuple[str, str]] = []

    def send_telegram(self, path, message):
        FakeAlert.telegram.append((str(path), str(message)))

    def send_email_alert(self, path, message):
        FakeAlert.emails.append((str(path), str(message)))

    def is_cooldown_over(self):
        return True


class FakeEventLogger:
    """بديل EventLogger — يلتقط سجل الأحداث في الذاكرة بلا ملفات"""

    events: list[tuple[str, dict, str]] = []

    def log_event(self, event_type, details, path):
        FakeEventLogger.events.append((str(event_type), dict(details or {}), str(path)))


# سجل قرارات الوكيل الملتقط (بديل agent_decisions في قاعدة البيانات)
_decisions: list[dict] = []


def _record_decision(camera_id, decision_type, reasoning, confidence=None):
    """بديل _log_agent_decision الحقيقي — نفس التوقيع، يلتقط في الذاكرة"""
    _decisions.append(
        {
            "camera_id": camera_id,
            "decision_type": str(decision_type),
            "reasoning": str(reasoning),
            "confidence": confidence,
        }
    )


# ---------- إعداد config.json المؤقت (3 كاميرات) ----------

_TEST_CONFIG = {
    # عام: تنبيه 0-23، لون ممنوع أزرق (زيّ الطلاب)، منطقة تغطي الإطار كله
    "ALERT_START_HOUR": 0,
    "ALERT_END_HOUR": 23,
    "ZONE_TOP_LEFT_X": 0,
    "ZONE_TOP_LEFT_Y": 0,
    "ZONE_BOTTOM_RIGHT_X": 1280,
    "ZONE_BOTTOM_RIGHT_Y": 720,
    "ZONE_DWELL_TIME": 1,
    "ALERT_COOLDOWN": 30,
    "TRACK_COOLDOWN_SEC": 60,
    "ANOMALY_EVENT_COOLDOWN": 20,
    "MIN_CONFIDENCE": 0.3,
    "ENABLE_COLOR_DETECTION": True,
    "FORBIDDEN_COLOR_HEX": "#0000FF",
    "COLOR_TOLERANCE": 40,
    "COLOR_MIN_PERCENTAGE": 30,
    "ENABLE_FIGHT_DETECTION": True,
    "FIGHT_IOU_THRESHOLD": 0.2,
    "FIGHT_MOTION_THRESHOLD": 50,
    "FIGHT_MIN_FRAMES": 5,
    "CROWD_MIN_PERSONS": 3,
    "CROWD_CONVERGENCE_THRESHOLD": 80,
    "CROWD_CONVERGENCE_RADIUS_PX": 150,
    "TELEGRAM_BOT_TOKEN": "mock-token",
    "TELEGRAM_CHAT_ID": "mock-chat",
    "ENABLE_EMAIL_ALERTS": False,
    "CAMERAS": [
        {
            "id": 1,
            "name": "Cam Gate",
            "url": "http://mock-cam-1/video",
            # س1/س3 نافذة تنبيه منفردة تعبر منتصف الليل
            "settings": {"ALERT_START_HOUR": 18, "ALERT_END_HOUR": 6},
        },
        {
            "id": 2,
            "name": "Cam Yard",
            "url": "http://mock-cam-2/video",
            # س2/س3: نافذة نهارية + لون ممنوع أحمر (منفردة عن العام الأزرق)
            "settings": {
                "ALERT_START_HOUR": 8,
                "ALERT_END_HOUR": 17,
                "FORBIDDEN_COLOR_HEX": "#FF0000",
            },
        },
        # س4: كاميرا 3 بلا settings إطلاقاً → الرجوع للـ Global
        {"id": 3, "name": "Cam Back", "url": "http://mock-cam-3/video"},
    ],
}


def base_state(camera_id: int, camera_name: str) -> dict:
    """حالة SurveillanceState نظيفة (كل مفاتيح TypedDict)"""
    return {
        "frame": None,
        "persons": [],
        "alert_sent": False,
        "image_path": "",
        "timestamp": "",
        "camera_id": camera_id,
        "camera_name": camera_name,
        "track_id": None,
        "event_type": "",
        "employee_name": "",
        "employee_role": "",
        "anomalies": [],
        "fights": [],
        "color_events": [],
    }


def _reset_runtime() -> None:
    """تصفير المؤقتات المشتركة بين السيناريوهات (عزل تام)"""
    _decisions.clear()
    FakeAlert.telegram.clear()
    FakeAlert.emails.clear()
    FakeEventLogger.events.clear()
    agent._last_alert_time.clear()
    agent._zone_entry_time.clear()
    agent._last_track_alert.clear()
    agent._last_color_decision.clear()


def _unknown_person(track_id: int) -> dict:
    return {
        "bbox": [100.0, 200.0, 200.0, 400.0],  # مركزه داخل المنطقة (0,0,1280,720)
        "track_id": track_id,
        "employee_id": None,
        "name": "Unknown",
        "confidence": 0.9,
        "match_score": None,
    }


# ---------- السيناريوهات ----------


def scenario_1_time_conflict():
    """س1: كاميرا 1 (18-06)، جري الساعة 12:00 → كبت "Outside alert hours"."""
    _NOW[0], _NOW[1] = 12, 0
    _reset_runtime()

    # بديل: أحداث anomaly تمر عبر alert_node حصراً (مستقلة عن باب التوقيت
    # في decision_node) — الحدث يُسجَّل والتنبيه يُكبت بسبب نافذة الكاميرا
    state = base_state(1, "Cam Gate")
    state["anomalies"] = [
        {
            "event_type": "running",
            "timestamp": "2026-11-17T12:00:00",
            "camera_id": 1,
            "camera_name": "Cam Gate",
            "track_id": 7,
            "speed_px_s": 300.0,
        }
    ]
    agent.alert_node(state)

    assert not FakeAlert.telegram, "أُرسل تيليجرام رغم كون الساعة خارج نافذة الكاميرا"
    assert not FakeAlert.emails, "أُرسل بريد رغم كون الساعة خارج نافذة الكاميرا"
    assert len(_decisions) == 1, f"قرار واحد متوقع، وجد {len(_decisions)}"
    assert _decisions[0]["camera_id"] == 1
    assert _decisions[0]["decision_type"] == "alert_suppressed", _decisions[0]
    reasoning = _decisions[0]["reasoning"]
    assert "Outside alert hours" in reasoning, reasoning
    assert "18:00" in reasoning and "06:00" in reasoning, reasoning
    # الحدث نفسه يبقى مسجلاً في سجل الأحداث (بلا إنذار)
    assert any(evt[0] == "running" for evt in FakeEventLogger.events)

    # باب التوقيت في decision_node لنفس الكاميرا: تسلل ظهراً → لا تنبيه ولا قرار
    state2 = base_state(1, "Cam Gate")
    state2["persons"] = [_unknown_person(5)]
    agent.decision_node(state2)
    assert state2["alert_sent"] is False
    assert len(_decisions) == 1, "باب التوقيت أطلق قراراً/تنبيهاً خارج النافذة"
    assert not FakeAlert.telegram


def scenario_2_color_outside_hours():
    """س2: كاميرا 2 (08-17، أحمر)، مجهول أحمر 20:00 → كبت بلا تنبيه."""
    _NOW[0], _NOW[1] = 20, 0
    _reset_runtime()

    frame = np.full((480, 640, 3), (0, 0, 255), dtype=np.uint8)  # BGR أحمر
    state = base_state(2, "Cam Yard")
    state["frame"] = frame
    state["persons"] = [_unknown_person(3)]

    agent.color_zone_node(state)

    assert state["color_events"] == [], "تولّد حدث لون رغم كون الوقت خارج نافذة الكاميرا"
    assert len(_decisions) == 1, f"قرار واحد متوقع، وجد {len(_decisions)}"
    assert _decisions[0]["decision_type"] == "alert_suppressed", _decisions[0]
    reasoning = _decisions[0]["reasoning"]
    assert "Outside alert hours" in reasoning, reasoning
    assert "08:00" in reasoning and "17:00" in reasoning, reasoning
    assert "#FF0000" in reasoning, reasoning

    agent.alert_node(state)  # بلا أحداث — لا إرسال
    assert not FakeAlert.telegram, "أُرسل تنبيه لون خارج نافذة الكاميرا"
    assert not FakeAlert.emails


def scenario_3_color_within_hours():
    """س3: كاميرا 2 (08-17، أحمر)، مجهول أحمر 10:00 → تنبيه + قرار alert_sent."""
    _NOW[0], _NOW[1] = 10, 0
    _reset_runtime()

    frame = np.full((480, 640, 3), (0, 0, 255), dtype=np.uint8)  # BGR أحمر
    state = base_state(2, "Cam Yard")
    state["frame"] = frame
    state["persons"] = [_unknown_person(3)]

    agent.color_zone_node(state)
    events = state["color_events"]
    assert len(events) == 1, f"حدث لون واحد متوقع، وجد {len(events)}"
    assert events[0]["event_type"] == "forbidden_color_intrusion"
    assert events[0]["color_hex"] == "#FF0000"  # الإعداد المنفرد للكاميرا 2

    agent.alert_node(state)
    assert len(FakeAlert.telegram) == 1, "تنبيه تيليجرام واحد متوقع للون الممنوع"
    assert "#FF0000" in FakeAlert.telegram[0][1]
    assert any(evt[0] == "forbidden_color_intrusion" for evt in FakeEventLogger.events)
    assert len(_decisions) == 1, f"قرار واحد متوقع، وجد {len(_decisions)}"
    assert _decisions[0]["decision_type"] == "alert_sent", _decisions[0]
    assert "forbidden color" in _decisions[0]["reasoning"].lower()
    assert _decisions[0]["camera_id"] == 2


def scenario_4_global_fallback():
    """س4: كاميرا 3 بلا settings → الرجوع للعام (أزرق) وإرسال التنبيه."""
    _NOW[0], _NOW[1] = 10, 0
    _reset_runtime()

    # Fallback: كاميرا بلا إعدادات منفردة ترجع لقيم الـ Global
    assert get_camera_setting(3, "FORBIDDEN_COLOR_HEX") == "#0000FF"
    assert get_camera_setting(3, "ALERT_START_HOUR") == 0
    assert get_camera_setting(3, "ALERT_END_HOUR") == 23

    frame = np.full((480, 640, 3), (255, 0, 0), dtype=np.uint8)  # BGR أزرق
    state = base_state(3, "Cam Back")
    state["frame"] = frame
    state["persons"] = [_unknown_person(9)]

    agent.color_zone_node(state)
    events = state["color_events"]
    assert len(events) == 1, f"حدث لون واحد متوقع، وجد {len(events)}"
    assert events[0]["color_hex"] == "#0000FF"  # اللون من الـ Global (Fallback)

    agent.alert_node(state)
    assert len(FakeAlert.telegram) == 1, "تنبيه واحد متوقع عبر إعدادات الـ Global"
    assert "#0000FF" in FakeAlert.telegram[0][1]
    assert len(_decisions) == 1
    assert _decisions[0]["decision_type"] == "alert_sent", _decisions[0]
    assert _decisions[0]["camera_id"] == 3


def extra_fallback_and_hot_reload():
    """إضافي: قراءة المنفردة/التراجع + Hot-Reload يحفظ settings وMulti-Camera."""
    # إعدادات منفردة لكل كاميرا (تُقرأ عبر نفس آلية الوكيل)
    assert get_camera_setting(1, "ALERT_START_HOUR") == 18
    assert get_camera_setting(1, "ALERT_END_HOUR") == 6
    assert get_camera_setting(2, "ALERT_END_HOUR") == 17
    assert get_camera_setting(2, "FORBIDDEN_COLOR_HEX") == "#FF0000"
    # ما لم يُخصص يتراجع للعام (حتى عتبات المشاجرات)
    assert get_camera_setting(2, "FIGHT_IOU_THRESHOLD") == 0.2
    assert get_camera_setting(1, "FORBIDDEN_COLOR_HEX") == "#0000FF"
    # كاميرا غير موجودة → عام
    assert get_camera_setting(99, "MIN_CONFIDENCE") == 0.3

    # settings محفوظة داخل كائن الكاميرا بعد التحميل (بنية config.json)
    cameras = config_module.Config.get_cameras()
    assert len(cameras) == 3, "Multi-Camera: 3 كاميرات متوقعة"
    assert cameras[0]["settings"] == {"ALERT_START_HOUR": 18, "ALERT_END_HOUR": 6}
    assert cameras[1]["settings"]["FORBIDDEN_COLOR_HEX"] == "#FF0000"
    assert "settings" not in cameras[2]

    # Hot-Reload: تعديل config.json خارجياً ثم Config.reload() يلتقط المنفرد
    cfg_path = config_module.CONFIG_JSON_PATH
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["CAMERAS"][2]["settings"] = {
        "FIGHT_IOU_THRESHOLD": "0.55",  # قيمة خام نصية — المضبّط يحوّلها
        "ALERT_END_HOUR": 21,
    }
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    config_module.Config.reload()

    assert get_camera_setting(3, "FIGHT_IOU_THRESHOLD") == 0.55
    assert get_camera_setting(3, "ALERT_END_HOUR") == 21
    # الكاميرات الأخرى لم تتأثر (عزل لكل كاميرا)
    assert get_camera_setting(1, "ALERT_START_HOUR") == 18
    assert get_camera_setting(2, "FORBIDDEN_COLOR_HEX") == "#FF0000"
    # إعادة config المؤقت لحالته الأصلية (بلا settings للكاميرا 3)
    cfg["CAMERAS"][2].pop("settings", None)
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    config_module.Config.reload()
    assert get_camera_setting(3, "FIGHT_IOU_THRESHOLD") == 0.2  # عام مجدداً


# ---------- مشغّل الاختبارات (PASS/FAIL) ----------

TESTS = [
    ("سيناريو 1 — تعارض التوقيت (كاميرا1 18-06، جري 12:00)", scenario_1_time_conflict),
    ("سيناريو 2 — لون ممنوع خارج التوقيت (كاميرا2 08-17، أحمر 20:00)", scenario_2_color_outside_hours),
    ("سيناريو 3 — تداخل ناجح (كاميرا2 08-17، أحمر 10:00)", scenario_3_color_within_hours),
    ("سيناريو 4 — الرجوع للإعدادات العامة (كاميرا3 بلا settings، أزرق)", scenario_4_global_fallback),
    ("إضافي — Fallback + Hot-Reload + Multi-Camera", extra_fallback_and_hot_reload),
]


def main() -> int:
    # config.json مؤقت بدل الحقيقي (لا يُلمس ملف النظام إطلاقاً)
    tmp_dir = Path(tempfile.mkdtemp(prefix="per-camera-tests-"))
    cfg_path = tmp_dir / "config.json"
    cfg_path.write_text(
        json.dumps(_TEST_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    original_cfg_path = config_module.CONFIG_JSON_PATH
    config_module.CONFIG_JSON_PATH = cfg_path

    # بدائل الوحدات داخل src.agent فقط (المصادر الحقيقية غير ملموسة)
    original_agent_attrs = {
        "datetime": agent.datetime,
        "time": agent.time,
        "Alert": agent.Alert,
        "EventLogger": agent.EventLogger,
        "_log_agent_decision": agent._log_agent_decision,
    }
    original_imwrite = cv2.imwrite
    agent.datetime = _FixedDateTime
    agent.time = types.SimpleNamespace(time=lambda: 1000.0)
    agent.Alert = FakeAlert
    agent.EventLogger = FakeEventLogger
    agent._log_agent_decision = _record_decision
    cv2.imwrite = lambda *args, **kwargs: True  # لا لقطات على القرص

    config_module.Config.reload()

    results: list[tuple[str, bool, str]] = []
    try:
        for name, fn in TESTS:
            try:
                _reset_runtime()
                fn()
                results.append((name, True, ""))
            except AssertionError as exc:
                results.append((name, False, str(exc) or "فشل تأكيد"))
            except Exception as exc:  # noqa: BLE001
                results.append((name, False, f"{type(exc).__name__}: {exc}"))
    finally:
        # استعادة كل شيء حتى لو فشل اختبار
        agent.datetime = original_agent_attrs["datetime"]
        agent.time = original_agent_attrs["time"]
        agent.Alert = original_agent_attrs["Alert"]
        agent.EventLogger = original_agent_attrs["EventLogger"]
        agent._log_agent_decision = original_agent_attrs["_log_agent_decision"]
        cv2.imwrite = original_imwrite
        config_module.CONFIG_JSON_PATH = original_cfg_path
        config_module.Config.reload()

    # ---------- الطباعة ----------
    print("=" * 78)
    print("🧪 اختبارات محاكاة الإعدادات المنفردة لكل كاميرا (Per-Camera Settings)")
    print("=" * 78)
    passed = 0
    for name, ok, detail in results:
        status = "PASS ✅" if ok else "FAIL ❌"
        print(f"\n[{status}] {name}")
        if ok:
            passed += 1
        else:
            print(f"       السبب: {detail}")
    total = len(results)
    print("\n" + "-" * 78)
    print(f"النتيجة النهائية: {passed}/{total} ناجح" + (" — ALL PASS ✅" if passed == total else " — FAILURES ❌"))
    print("-" * 78)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
