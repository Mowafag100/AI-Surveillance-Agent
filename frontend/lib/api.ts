// ثوابت وخدمة جلب API من جهة الخادم (نمط القالب: serverFetch مع تمرير الكوكي)
import { cookies } from "next/headers";

// اسم الكوكي (نفس قيمة AUTH_COOKIE في القالب)
export const AUTH_COOKIE = "auth_cookie";

// عنوان API من جهة الخادم (داخل Docker نفس الشبكة: http://api:8090)
export const API_BASE =
  process.env.API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8090";

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
  return fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
      Cookie: cookieStore.toString(),
    },
    cache: "no-store",
  });
}
