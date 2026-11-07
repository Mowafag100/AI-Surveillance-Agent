"""مساعد المراقبة الذكي (Natural Language Chat) — يجيب من بيانات الأحداث الحقيقية.

ضمانات أمنية صارمة (شرط المهمة):
- يقرأ حصراً logs/events.jsonl — لا يلمس config.json ولا .env ولا أي توكن
  أو كلمة مرور أو إعدادات.
- السياق الممرر للنموذج يمر عبر «قائمة بيضاء» ثابتة لحقول الأحداث
  (_ALLOWED_*) — أي حقل غريب يُقذف (فشل صامت ذكيّ ضد تسرّب مستقبلي).
- مفتاح OPENAI_API_KEY يُقرأ من متغيرات البيئة فقط وليس من ملفات الإعدادات،
  ولا يظهر في GET /api/settings ولا يُكتب أبداً في config.json.
- النموذج يُلزَم في الـ prompt بـ: «لا تختلق، أجب من السجل فقط، وإن
  عدمت البيانات قل ذلك» — وردّه لا يتجاوز سياق الأحداث.

سلسلة المزودين (أول ما يعمل):
1) OPENAI_API_KEY → langchain-openai (استيراد متأخر — غياب الحزمة لا يكسر)
2) OLLAMA_BASE_URL (افتراضي http://127.0.0.1:11434) + OLLAMA_MODEL
   (افتراضي llama3.2) → langchain-ollama
3) إجابة قاعدية محسوبة من البيانات نفسها (بلا نموذج) — إجابة دقيقة عددياً
   (التعبير، التفصيل، الأحدث) بحيث لا يقف المساعد أبداً.
"""

import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
EVENTS_FILE = BASE_DIR / "logs" / "events.jsonl"
MAX_EVENTS_READ = 4000          # أقصى سطور تُقرأ من السجل لكل طلب
MAX_EVENTS_IN_DIGEST = 40       # آخر الأحداث التي تظهر حرفياً في سياق النموذج
MAX_DIGEST_CHARS = 6000         # سقف حجم السياق المرسل للنموذج (prompt)

# --- قوائم بيضاء لحقول الأحداث (سياسة «فليسر» أمنية) ---
_ALLOWED_EVENT_FIELDS = ("timestamp", "event", "id")
_ALLOWED_DETAILS_FIELDS = (
    "camera_id",
    "camera_name",
    "employee_name",
    "role",
    "track_id",
    "speed_px_s",
    "duration_sec",
    "aspect_ratio",
    "prev_aspect_ratio",
)

# أسماء عربية للأنواع للاستخدام في الردود القاعدية
_TYPE_AR = {
    "intrusion": "تسلل",
    "employee_entry": "دخول موظف",
    "fall": "سقوط",
    "running": "جري",
    "loitering": "توقّف مشبوه",
}

# كلمات دلالية بالعربي/الإنجليزي لفلترة نوع الحدث من السؤال
_TYPE_KEYWORDS = {
    "intrusion": ("تسلل", "خطر", "intrusion"),
    "employee_entry": ("موظف", "employees", "employee"),
    "fall": ("سقوط", "سقط", "fall", "fell"),
    "running": ("جري", "يركض", "جرى", "running", "run"),
    "loitering": ("وقوف", "توقّف", "توقف مشبوه", "loitering"),
}

# كلمات «السجل كامل» — تتجاوز نافذة آخر 7 أيام وتقرأ كل الأحداث من البداية
_FULL_HISTORY_KEYWORDS = ("السجل كامل", "كل الأحداث", "جميع الأحداث", "كل السجل", "all time")


def _read_events(full_history: bool = False) -> list[dict[str, Any]]:
    """قراءة سطرية لـ events.jsonl (أسطر تالفة تتجاهل بشكل صامت)

    full_history=True (سؤال «السجل كامل») → قراءة من بداية الملف بلا سقف
    آخر 4000 سطر؛ الأحداث المرسلة للنموذج تبقى محدودة لأنها تحت سقوف الـ digest."""
    if not EVENTS_FILE.is_file():
        return []
    events: list[dict[str, Any]] = []
    try:
        with EVENTS_FILE.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
            if not full_history:
                lines = lines[-MAX_EVENTS_READ:]
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    except OSError as exc:
        logger.warning(f"⚠️ تعذّر قراءة سجل الأحداث: {exc}")
    return events


def _sanitize_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """قائمة بيضاء: حقول الأحداث المسموح بالوصول للسياق، فليس غيرها"""
    sanitized: list[dict[str, Any]] = []
    for event in events:
        details_raw = event.get("details") if isinstance(event.get("details"), dict) else {}
        sanitized.append({
            "timestamp": event.get("timestamp"),
            "event": event.get("event"),
            "id": event.get("id"),
            "details": {
                key: value
                for key, value in details_raw.items()
                if key in _ALLOWED_DETAILS_FIELDS
            },
        })
    return sanitized


def _event_time(event: dict[str, Any]) -> datetime | None:
    timestamp = event.get("timestamp")
    if not isinstance(timestamp, str):
        return None
    try:
        return datetime.fromisoformat(timestamp)
    except ValueError:
        return None


def _parse_camera_filter(question: str) -> int | None:
    """مطابقة «كاميرا 1» / «camera 2» (بعد كلمة الكاميرا فقط — صدقاً)"""
    match = re.search(r"(?:كاميرا|camera)\s*(?:رقم\s*|no\.?\s*)?(\d+)", question, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _parse_type_filter(question: str) -> set[str] | None:
    """كل أنواع الأحداث المذكورة في السؤال (أسئلة مركّبة: «سقوط أو جري»)"""
    lowered = question.lower()
    matched: set[str] = set()
    for event_type, keywords in _TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in lowered:
                matched.add(event_type)
                break
    return matched or None


def _asks_full_history(question: str) -> bool:
    """«السجل كامل/كل الأحداث...» → تجاوز فلتر آخر 7 أيام والقراءة من البداية"""
    lowered = question.lower()
    return any(keyword in lowered for keyword in _FULL_HISTORY_KEYWORDS)


def _parse_period(
    question: str,
    full_history: bool = False,
) -> tuple[datetime | None, datetime | None, str]:
    """نافذة زمنية من السؤال (بداية، نهاية اختيارية، تسمية) — نهاية None = حتى الآن

    التصنيف: أمس / اليوم / آخر 7 أيام — الافتراضي آخر 7 أيام (والتسمية تُظهر ذلك).
    full_history («السجل كامل») → (None, None): بلا فلترة زمنية إطلاقاً
    وتُقرأ كل الأحداث من بداية السجل."""
    if full_history:
        return (None, None, "كل السجل منذ التشغيل")
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    asked_yesterday = any(
        word in question
        for word in ("أمس", "يوم أمس", "yesterday")
    )
    asked_today = any(word in question for word in ("اليوم", "today"))
    asked_week = any(word in question for word in ("أسبوع", "week", "سبعة أيام"))

    if asked_yesterday:
        start = today_start - timedelta(days=1)
        return (start, today_start, "أمس")
    if asked_week:
        start = today_start - timedelta(days=6)
        return (start, None, "آخر 7 أيام")
    if asked_today:
        return (today_start, None, "اليوم")
    start = today_start - timedelta(days=6)
    return (start, None, "آخر 7 أيام")


def _apply_filters(
    events: list[dict[str, Any]],
    camera_id: int | None,
    event_types: set[str] | None,
    window: tuple[datetime | None, datetime | None],
) -> list[dict[str, Any]]:
    """طبق الفلاتر المستخرجة (الأنواع، الكاميرا، النافذة الزمنية)"""
    window_start, window_end = window
    filtered: list[dict[str, Any]] = []
    for event in events:
        event_time = _event_time(event)
        if event_time is None:
            continue
        if window_start is not None and event_time < window_start:
            continue
        if window_end is not None and event_time >= window_end:
            continue
        if event_types is not None and event.get("event") not in event_types:
            continue
        details = event.get("details") if isinstance(event.get("details"), dict) else {}
        if camera_id is not None and int(details.get("camera_id") or 0) != camera_id:
            continue
        filtered.append(event)
    return filtered


def _build_digest(
    all_events: list[dict[str, Any]],
    filtered_events: list[dict[str, Any]],
    window_label: str,
    camera_id: int | None,
    event_types: set[str] | None,
) -> str:
    """سياق نصي مختصر من الإحصاءات + آخر الأحداث — هذا كل ما يلمعه النموذج."""
    lines: list[str] = []
    filtered_count = len(filtered_events)
    counter: Counter[str] = Counter(str(e.get("event") or "؟") for e in filtered_events)
    camera_counter: Counter[str] = Counter(
        str((e.get("details") or {}).get("camera_id") or (e.get("details") or {}).get("camera_name") or "؟")
        for e in filtered_events
    )

    lines.append(f"[إجمالي الأحداث المطابقة للسؤال: {filtered_count}]")
    lines.append(f"[فترة السؤال: {window_label}]")
    if camera_id is not None:
        lines.append(f"[فلترة الكاميرا: {camera_id}]")
    if event_types is not None:
        labels = "، ".join(_TYPE_AR.get(t, t) for t in sorted(event_types))
        lines.append(f"[فلترة نوع الحدث: {labels}]")
    lines.append("[العداد حسب النوع: " + ", ".join(f"{k}={v}" for k, v in counter.items()) + "]")
    lines.append("[العداد حسب الكاميرا: " + ", ".join(f"كاميرا {k}={v}" for k, v in camera_counter.items()) + "]")

    if filtered_count == 0:
        lines.append("[لا يوجد أي حدث مطابق]")
    else:
        lines.append(f"[آخر {min(MAX_EVENTS_IN_DIGEST, filtered_count)} حدثاً مطابقاً (الأحدث أولاً)]")
        for event in list(reversed(filtered_events))[-MAX_EVENTS_IN_DIGEST:]:
            event_time = _event_time(event) or event.get("timestamp")
            details = event.get("details") or {}
            lines.append(
                f"- {event_time} | حدث: {event.get('event')} | "
                f"كاميرا: {details.get('camera_name') or details.get('camera_id')} | "
                f"موظف: {details.get('employee_name') or '—'}"
            )

    # قياس سقف ما يُرسل للجرس (size) — لـ prompt النموذج
    digest = "\n".join(lines)
    if len(digest) > MAX_DIGEST_CHARS:
        digest = digest[:MAX_DIGEST_CHARS] + "\n[…سياق مقطوع]"
    return digest


def _rule_based_answer(
    filtered_events: list[dict[str, Any]],
    window_label: str,
    camera_id: int | None,
    event_types: set[str] | None,
) -> str:
    """إجابة قاعدية من البيانات — تضمن ألا يقف المساعد بلا نموذج LLM."""
    if not filtered_events:
        scope = f"في الكاميرا {camera_id}" if camera_id is not None else "في جميع الكاميرات"
        kind = ""
        if event_types:
            kind = f"من نوع ({' أو '.join(_TYPE_AR.get(t, t) for t in sorted(event_types))})"
        sentence = (
            f"لا يوجد أي حدث {kind} خلال ({window_label}) {scope}".replace("  ", " ")
        )
        return sentence + "."

    counter: Counter[str] = Counter(str(e.get("event") or "؟") for e in filtered_events)
    count_lines = "\n".join(
        f"  - {_TYPE_AR.get(k, k)}: {v}" for k, v in counter.most_common()
    )
    scope = f"الكاميرا {camera_id}، " if camera_id is not None else ""
    latest = filtered_events[-1]
    latest_details = latest.get("details") or {}
    latest_time = _event_time(latest)

    lines = [
        f"خلال ({window_label}) في {scope}:",
        f"عدد الأحداث المُطابقة: {len(filtered_events)}",
        "تفصيل حسب النوع:",
        count_lines,
    ]
    # أسماء الموظفين إن وردت (أسئلة «من دخل؟»)
    employees = sorted({
        str((e.get("details") or {}).get("employee_name"))
        for e in filtered_events
        if (e.get("details") or {}).get("employee_name")
    })
    if employees:
        lines.append("الموظفون: " + "، ".join(employees))
    if latest_time:
        lines.append(
            f"أحدث حدث: {_TYPE_AR.get(str(latest.get('event')), str(latest.get('event')))} "
            f"على {latest_details.get('camera_name') or latest_details.get('camera_id')} "
            f"في {latest_time:%Y-%m-%d %H:%M}."
        )
    return "\n".join(lines)


def _llm_or_none(message: str, digest: str) -> tuple[str, str] | None:
    """سلسلة المزودين: OpenAI (مفتاح بيئة العمل) → Ollama محلي → None.

    الاستيرادات متأخرة — غياب الحزمة أو عدم توفر المزود لا يكسر النداء
    ويعاد (None) لاستخدام الإجابة القاعدية. يعيد (النص، المزوّد)."""
    system_prompt = (
        "أنت مساعد أمني ذكي. أجب باللغة العربية أو الإنجليزية حسب لغة السؤال.\n"
        "لا تقل (لا يمكنني الوصول للبيانات) — لديك حق الوصول إلى سجل الأحداث أدناه.\n"
        "إذا لم تجد أحداثاً، قل فقط (لا توجد أحداث مسجلة).\n"
        "لا تؤلف قصصاً: استخدم الأرقام والأوقات كما هي حرفياً ولا تضف بيانات من عندك.\n"
        "ليس لديك سوى بيانات الأحداث — لا إعدادات ولا توكنات."
    )
    prompt = f"{system_prompt}\n\n[سجل الأحداث]\n{digest}\n\n[سؤال المستخدم]\n{message}"

    # 1) OpenAI — فقط عندما يوفر المفتاح (متغير بيئة، لا يمر عبر config.json)
    if (os.getenv("OPENAI_API_KEY") or "").strip():
        try:
            from langchain_openai import ChatOpenAI  # استيراد متأخر
            llm = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL") or "gpt-4o-mini",
                temperature=0.2,
                max_tokens=500,
                timeout=25,
            )
            return str(llm.invoke(prompt).content).strip(), "openai"
        except Exception as exc:
            logger.warning(f"⚠️ فشل مزود OpenAI: {exc}")

    # 2) Ollama محلي — التفسير المستقل
    ollama_base = (os.getenv("OLLAMA_BASE_URL") or "").strip()
    if ollama_base:
        try:
            from langchain_ollama import OllamaLLM  # استيراد متأخر
            llm = OllamaLLM(
                base_url=ollama_base,
                model=os.getenv("OLLAMA_MODEL") or "llama3.2",
            )
            return str(llm.invoke(prompt)).strip(), "ollama"
        except Exception as exc:
            logger.warning(f"⚠️ فشل مزود Ollama ({ollama_base}): {exc}")

    return None


def answer_question(message: str) -> dict[str, str]:
    """مدخل POST /api/chat: سؤال المستخدم → رد نصي + اسم المزوّد المستخدم."""
    message = (message or "").strip()
    if not message:
        return {"reply": "اكتب سؤالك أولاً 🙂", "provider": "empty"}

    full_history = _asks_full_history(message)
    events = _sanitize_events(_read_events(full_history=full_history))
    camera_id = _parse_camera_filter(message)
    event_types = _parse_type_filter(message)
    window_start, window_end, window_label = _parse_period(message, full_history=full_history)
    filtered = _apply_filters(events, camera_id, event_types, (window_start, window_end))

    reply = None
    provider = "stats"
    langchain_answer = _llm_or_none(
        message,
        _build_digest(events, filtered, window_label, camera_id, event_types),
    )
    if langchain_answer and langchain_answer[0]:
        reply, provider = langchain_answer[0], langchain_answer[1]
    if not reply:
        reply = _rule_based_answer(filtered, window_label, camera_id, event_types)
        provider = "stats"

    return {"reply": reply, "provider": provider}
