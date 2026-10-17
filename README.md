<div dir="rtl" align="center">

# 🎯 AI Surveillance Agent — وكيل المراقبة الذكي

**نظام مراقبة فيديو متكامل بالذكاء الاصطناعي: كشف التسلل لحظياً وتنبيهات فورية عبر تيليجرام مع لوحة تحكم ويب.**

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.14+-009688?logo=fastapi&logoColor=white)
![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-FFCE00)
![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=next.js&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-Alpine-DC382D?logo=redis&logoColor=white)

</div>

---

<div dir="rtl">

## 📖 نظرة عامة

نظام مراقبة فيديو متكامل يعتمد على الذكاء الاصطناعي (**YOLOv8**) لاكتشاف التسلل،
مع إرسال تنبيهات فورية عبر **تيليجرام** (بصورة اللقطة)، ولوحة تحكم ويب
(**Next.js**) محمية بمصادقة JWT لإدارة الكاميرات والمناطق الحساسة والتقارير —
كل ذلك ببنية Docker جاهزة للنشر الفوري.

لُبّ النظام خط أنابيب ذكي (LangGraph-style): **الكشف → منطقة التسلل → زمن
البقاء → التنبيه**، ويعمل على **عدة كاميرات بالتوازي** مع تحديث حيّ للإعدادات
(Hot-Reload) دون إيقاف الخدمة.

---

## ✨ الميزات

| | الميزة | الوصف |
|:---:|---|---|
| 🤖 | **اكتشاف الأشخاص (YOLO)** | نموذج YOLOv8 مع إمكانية اختيار الحجم (`n` / `s` / `m`) من اللوحة — التبديل حيّ دون إعادة تشغيل |
| 📹 | **كاميرات متعددة (Multi-Camera)** | إدارة قائمة الكاميرات ديناميكياً من الواجهة، ثريد معالجة مستقل لكل كاميرا، و**Hot-Reload**: حذف/إضافة/تبديل رابط دون إيقاف |
| 📍 | **مناطق حساسة (Zones)** | تحديد مستطيل المراقبة (4 إحداثيات) + زمن البقاء المطلوب (`ZONE_DWELL_TIME`) قبل إطلاق التنبيه |
| ⏰ | **جدولة التنبيهات (Schedules)** | نافذة زمنية للحساسية (من/إلى) — تدعم النوافذ العابرة لمنتصف الليل |
| 📨 | **تنبيهات فورية (Telegram)** | رسالة + لقطة الحدث مباشرة، مع **اسم الكاميرا** ومهلة تبريد (Cooldown) تمنع الغرق بالرسائل |
| 🔐 | **لوحة تحكم ويب محمية** | Next.js مع تسجيل دخول **JWT** (كوكي HttpOnly) وحماية مستوى الخادم + Middleware |
| 📊 | **تقارير CSV** | تصدير سجل الأحداث بضغطة زر (متوافق Excel مع العربية utf-8-sig) — للمشرفين فقط |
| 🔄 | **إعدادات ديناميكية** | كل الإعدادات في `config.json` قابلة للتعديل عبر الـ API/اللوحة وتُطبَّق حيّاً |

---

## 🛠️ البنية التقنية

| الطبقة | التقنية |
|---|---|
| الوكيل (Agent) | Python، OpenCV، **YOLOv8 (Ultralytics)**، PyTorch، threading متوازٍ |
| الذكاء | LangGraph-style pipeline: `detect → decision → alert` |
| الـ API | **FastAPI** + مصادقة **JWT** (python-jose) + SQLite-ready/PostgreSQL (SQLAlchemy async) |
| قاعدة البيانات | **PostgreSQL 15** (المستخدمون + الأحداث) |
| الذاكرة المؤقتة | **Redis** |
| اللوحة | **Next.js 16** (Server Actions + Route Handlers + Middleware proxy) |
| النشر | **Docker Compose** — postgres + redis + api + agent |

### مسارات الـ API الرئيسية

| المسار | الصلاحية | الوظيفة |
|---|---|---|
| `GET /api/health` | عام | فحوصات الخدمة |
| `GET /api/events` | عام | آخر الأحداث (مع فلاتر كاميرا/نوع) |
| `GET /api/cameras` | عام | الكاميرات الفعّالة من config.json |
| `POST /api/login` + `GET /api/me` | عام | دخول JWT (OAuth2 form) |
| `POST /api/auth/register` | عام | التسجيل — **أول مستخدم يصبح مشرفاً تلقائياً** |
| `GET/POST /api/settings` | مشرف للتعديل | الإعدادات الحية (المنطقة، التوقيت، النموذج، الكاميرات) |
| `GET /api/reports/export` | مشرف | تصدير CSV |

---

## 🚀 التشغيل السريع (Quick Start)

### 1. تجهيز المتغيرات

```bash
cp .env.example .env
# ثم عدّل: كلمة مرور PostgreSQL، رابط الكاميرا، توكن/معرّف تيليجرام، JWT_SECRET_KEY
```

> ⚠️ **مهم أمنياً:** غيّر `JWT_SECRET_KEY` و`POSTGRES_PASSWORD` إلى قيم قوية
> قبل الإنتاج. ملف `.env` مُستثنى من Git ولا يُرفَع أبداً.

### 2. تشغيل الخدمات (Docker)

```bash
docker compose up -d --build
```

يُشغّل: PostgreSQL + Redis + API (:18090) + وكيل المراقبة (ثريد لكل كاميرا).

### 3. لوحة التحكم

```bash
cd frontend
npm install
npm run build && npm start   # أو npm run dev للتطوير
```

ثم افتح **<http://localhost:3000>** — أول تسجيل دخول من صفحة
`/login` (أو التسجيل من `/signup`) يُنشئ حساب **المشرف** تلقائياً.

### 4. الضبط من اللوحة

`/admin/settings` أقسام: 📹 الكاميرات (جدول ديناميكي) — 📍 المنطقة الحساسة —
⏰ أوقات التنبيه — 🧠 نموذج الذكاء الاصطناعي — 📨 التلغرام.
الحفظ يُطبَّق حيّاً (Hot-Reload) دون إعادة تشغيل.

---

## 📂 هيكل المشروع

```
ai-surveillance-agent/
├── main.py                  # نقطة تشغيل الوكيل: ثريد لكل كاميرا + مطابقة Hot-Reload
├── src/
│   ├── agent.py             # خط الأنابيب الذكي: detect → decision → alert
│   ├── camera.py            # اتصال الكاميرا + إعادة المحاولة + إيقاف آمن
│   ├── detector.py          # YOLOv8 (نموذج مُشارك) + التبديل الحي n/s/m
│   ├── alert.py             # تنبيهات Telegram بالصور (توكن ديناميكي)
│   ├── api.py               # FastAPI: الأحداث/الكاميرات/الإعدادات/تقرير CSV
│   ├── auth.py              # JWT + المستخدمون (أول مستخدم = مشرف)
│   ├── config.py            # الإعدادات الديناميكية من config.json + Hot-Reload
│   ├── database.py          # SQLAlchemy async فوق PostgreSQL
│   └── logger.py            # سجل الأحداث events.jsonl (آمن لثريدات متعددة)
├── frontend/                # لوحة التحكم — Next.js 16
│   ├── app/                 # / (داشبورد) • /admin/settings • /login • /signup
│   ├── actions/             # Server Actions (دخول/حفظ) مع كوكي HttpOnly
│   ├── components/          # نماذج الدخول والتسجيل والإعدادات
│   └── lib/                 # serverFetch (تعبير الكوكي للـ API)
├── models/                  # أوزان YOLOv8
├── alerts/                  # صور الأحداث المحفوظة
├── logs/                    # events.jsonl + system.log
├── config.json              # الإعدادات الحية (ملف مُوحَّد مع الحاويات)
├── docker-compose.yml       # postgres + redis + api + agent
├── Dockerfile.api           # صورة الـ API (FastAPI)
├── Dockerfile.agent         # صورة الوكيل (YOLO + OpenCV)
└── .env.example             # نموذج متغيرات البيئة
```

---

## 🖼️ لقطة شاشة للوحة التحكم

<!-- ضع صورة اللوحة هنا: docs/screenshot-dashboard.png -->

<div align="center">
  <img src="docs/screenshot-dashboard.png" alt="لوحة تحكم نظام المراقبة الذكي" width="800" />
</div>

<div dir="rtl">

*(لقطة توضيحية: داشبورد الأحداث مع إحصائيات اليوم، حالة الكاميرات الحقيقية،
وزر تصدير CSV — تُضاف الصورة في `docs/screenshot-dashboard.png`)*

</div>

---

## 🔒 ملاحظات أمنية

- جميع مسارات التعديل (`POST /api/settings`) تتطلب **JWT بصلاحية مشرف**.
- كوكي الجلسة **HttpOnly** ولا تُقرأ من JavaScript في المتصفح.
- التوكن الحساس (Telegram) يُعرض **مقنّعاً** في واجهة الإعدادات فقط.
- مدقّقات الخادم تحقق من كل قيمة قبل الحفظ (نوع + نطاق) — القيم الخاطئة تُرفض بـ 400.

---

<div align="center">

**AI Surveillance Agent** — وثائق تفصيلية إضافية في مجلد `reports/`

</div>
