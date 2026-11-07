// ثوابت وخدمة جلب API من جهة الخادم (نمط القالب: serverFetch مع تمرير الكوكي)
import { cookies } from "next/headers";

// اسم الكوكي (نفس قيمة AUTH_COOKIE في القالب)
export const AUTH_COOKIE = "auth_cookie";

/**
 * قاعدة الرابط حسب بيئة التنفيذ — السيرفر (SSR) يرفض الروابط النسبية (Invalid URL):
 * - typeof window === "undefined": مطلق دائماً — API_URL ثم NEXT_PUBLIC_API_URL
 *   ثم "http://localhost:18090" (المنفذ المعرّض لحاوية api في docker-compose: 18090:8090)
 * - المتصفح: نسبي (نفس النطاق عبر Route Handlers) — "" يعمل، وإلا مطلق (Cloudflare)
 */
export function resolveApiBaseUrl(): string {
  if (typeof window === "undefined") {
    return (
      process.env.API_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:18090"
    );
  }
  return process.env.NEXT_PUBLIC_API_URL || "";
}

// عنوان API من جهة الخادم — يتفرع حسب البيئة داخل resolveApiBaseUrl:
// السيرفر ← API_URL ثم NEXT_PUBLIC_API_URL ثم "http://localhost:18090"
// المتصفح ← NEXT_PUBLIC_API_URL ثم "" (نسبي؛ يعمل خلف Cloudflare)
// الشرط || بسلسلة ساقطة: ?? كان يمرر "" لو ضُبط متغير بحلقة فارغة، محوّلاً
// fetch إلى مسار نسبي "/api/..." — سبب Invalid URL في الإنتاج (SSR)
export const API_BASE = resolveApiBaseUrl();

/**
 * جلب من جهة الخادم مع إرفاق كوكي المصادقة (HttpOnly cookie auth).
 * ملاحظة: الكوكي مضبوط على نطاق الواجهة، لذا الاتصال بالـ API يتم
 * من خادم Next وليس المتصفح — هذا هو نمط القالب مع server actions.
 */
export async function serverFetch(
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  const cookieStore = await cookies();
  // من السيرفر (cookies()) دائماً — والمسار نسبي مثل "/api/auth/test-token"
  return fetch(`${resolveApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
      Cookie: cookieStore.toString(),
    },
    cache: "no-store",
  });
}
