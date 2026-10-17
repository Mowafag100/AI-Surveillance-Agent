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
