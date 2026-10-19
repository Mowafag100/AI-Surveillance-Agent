"use server";

// Server Action لحفظ الإعدادات — يستدعي POST /api/settings محمياً بـ JWT
import { revalidatePath } from "next/cache";

import { serverFetch } from "@/lib/api";

export interface SettingsActionState {
  error?: string;
  ok?: boolean;
}

export async function saveSettingsAction(
  _prevState: SettingsActionState,
  formData: FormData
): Promise<SettingsActionState> {
  const payload: Record<string, unknown> = {};

  const zoneDwell = Number(formData.get("ZONE_DWELL_TIME") ?? "");

  if (Number.isNaN(zoneDwell)) {
    return { error: "ZONE_DWELL_TIME يجب أن يكون رقماً" };
  }
  if (formData.get("ZONE_DWELL_TIME") !== "") {
    payload.ZONE_DWELL_TIME = zoneDwell;
  }

  // ==== المنطقة الحساسة (إحداثيات على إطار 640×480) ====
  for (const fieldKey of ["ZONE_TOP_LEFT_X", "ZONE_TOP_LEFT_Y", "ZONE_BOTTOM_RIGHT_X", "ZONE_BOTTOM_RIGHT_Y"] as const) {
    const rawValue = String(formData.get(fieldKey) ?? "").trim();
    if (rawValue === "") continue; // يُترك الإعداد الحالي كما هو
    const parsedValue = Number(rawValue);
    if (!Number.isFinite(parsedValue) || parsedValue < 0) {
      return { error: `${fieldKey} يجب أن يكون رقماً موجباً` };
    }
    payload[fieldKey] = Math.round(parsedValue);
  }
  const tlx = Number(formData.get("ZONE_TOP_LEFT_X") ?? NaN);
  const brx = Number(formData.get("ZONE_BOTTOM_RIGHT_X") ?? NaN);
  const tly = Number(formData.get("ZONE_TOP_LEFT_Y") ?? NaN);
  const bry = Number(formData.get("ZONE_BOTTOM_RIGHT_Y") ?? NaN);
  if ([tlx, brx, tly, bry].every(Number.isFinite)) {
    if (tlx >= brx) return { error: "أعلى-يسار X يجب أن يكون أصغر من أسفل-يمين X" };
    if (tly >= bry) return { error: "أعلى-يسار Y يجب أن يكون أصغر من أسفل-يمين Y" };
  }

  // ==== أوقات التنبيه (0-23 — الفترة عبر منتصف الليل مسموحة في agent) ====
  for (const fieldKey of ["ALERT_START_HOUR", "ALERT_END_HOUR"] as const) {
    const rawValue = String(formData.get(fieldKey) ?? "").trim();
    if (rawValue === "") continue;
    const parsedValue = Number(rawValue);
    if (!Number.isInteger(parsedValue) || parsedValue < 0 || parsedValue > 23) {
      return { error: `${fieldKey} يجب أن يكون رقماً صحيحاً ضمن 0-23` };
    }
    payload[fieldKey] = parsedValue;
  }

  // ==== المهلة/CAMERA_TIMEOUT_SEC (ثواني — مهلة انقطاع الكاميرا) ====
  const cameraTimeoutRaw = String(formData.get("CAMERA_TIMEOUT_SEC") ?? "").trim();
  if (cameraTimeoutRaw !== "") {
    const cameraTimeout = Number(cameraTimeoutRaw);
    if (!Number.isFinite(cameraTimeout) || cameraTimeout < 5) {
      return { error: "CAMERA_TIMEOUT_SEC يجب أن يكون رقماً (5 ثوانٍ على الأقل)" };
    }
    payload.CAMERA_TIMEOUT_SEC = cameraTimeout;
  }

  // ==== تنبيهات البريد الإلكتروني ====
  // checkbox مُدار: قيمته تُرسل دائماً (موجود = true، غائب = false)
  payload.ENABLE_EMAIL_ALERTS = formData.get("ENABLE_EMAIL_ALERTS") === "on";

  const smtpPortRaw = String(formData.get("SMTP_PORT") ?? "").trim();
  if (smtpPortRaw !== "") {
    const smtpPort = Number(smtpPortRaw);
    if (!Number.isInteger(smtpPort) || smtpPort < 1 || smtpPort > 65535) {
      return { error: "SMTP_PORT يجب أن يكون رقماً صحيحاً ضمن 1-65535" };
    }
    payload.SMTP_PORT = smtpPort;
  }
  const smtpHost = String(formData.get("SMTP_HOST") ?? "").trim();
  const smtpUser = String(formData.get("SMTP_USER") ?? "").trim();
  const alertEmailTo = String(formData.get("ALERT_EMAIL_TO") ?? "").trim();
  // الحقول النصية غير السرية تُرسل دائماً (مسح الفراغ يفرّغها في config.json)
  payload.SMTP_HOST = smtpHost;
  payload.SMTP_USER = smtpUser;
  payload.ALERT_EMAIL_TO = alertEmailTo;
  // كلمة مرور SMTP تُعرض مقنّعة — تُرسل فقط عند كتابة قيمة جديدة
  const smtpPassword = String(formData.get("SMTP_PASSWORD") ?? "").trim();
  if (smtpPassword) payload.SMTP_PASSWORD = smtpPassword;

  // ==== حجم النموذج ====
  const modelSize = String(formData.get("MODEL_SIZE") ?? "").trim();
  if (["n", "s", "m"].includes(modelSize)) {
    payload.MODEL_SIZE = modelSize;
  } else if (modelSize !== "") {
    return { error: "MODEL_SIZE يجب أن يكون n أو s أو m" };
  }

  // مصفوفة الكاميرات (جدول ديناميكي) — ترسل كاملة حتى عند عدم التغيير
  const camerasCount = Number(formData.get("CAMERAS_COUNT") ?? "0");
  const cameras: { id: number; name: string; url: string }[] = [];
  for (let i = 0; i < camerasCount; i++) {
    const name = String(formData.get(`CAMERAS_${i}_NAME`) ?? "").trim();
    const url = String(formData.get(`CAMERAS_${i}_URL`) ?? "").trim();
    // الصفوف الفارغة تماماً تُترك؛ المسمى بلا رابط خطأ
    if (!name && !url) continue;
    if (!url) {
      return { error: `الكاميرا "${name || i + 1}" بلا رابط` };
    }
    cameras.push({ id: cameras.length + 1, name, url });
  }
  payload.CAMERAS = cameras;

  // الحقول السرية تُعرض مقنّعة، لذا نرسلها فقط عند كتابة قيمة جديدة
  const botToken = String(formData.get("TELEGRAM_BOT_TOKEN") ?? "").trim();
  const chatId = String(formData.get("TELEGRAM_CHAT_ID") ?? "").trim();
  if (botToken) payload.TELEGRAM_BOT_TOKEN = botToken;
  if (chatId) payload.TELEGRAM_CHAT_ID = chatId;

  if (Object.keys(payload).length === 0) {
    return { error: "لا توجد تغييرات للحفظ" };
  }

  let res: Response;
  try {
    res = await serverFetch("/api/settings", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  } catch {
    return { error: "تعذر الوصول إلى خادم API" };
  }

  if (!res.ok) {
    let detail = `فشل الحفظ (${res.status})`;
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      // تجاهل — رسالة منشورة أدناه
    }
    return { error: detail };
  }

  // إعادة توليد صفحة الإعدادات لتظهر القيم الجديدة فوراً
  revalidatePath("/admin/settings");
  return { ok: true };
}
