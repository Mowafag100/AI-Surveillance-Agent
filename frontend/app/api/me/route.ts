// Route Handler يمرر بيانات المستخدم الحالي (GET /api/me) إلى المتصفح على
// النطاق نفسه — كوكي الجلسة HttpOnly يُرسل تلقائياً لعملية التحقق من الصلاحية
// (يستخدمه زر "تأكيد المراجعة" في لوحة التحكم لمعرفة إن كان المشرف مسجلاً)
import { cookies } from "next/headers";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  const apiBase =
    process.env.API_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://localhost:8090";

  const res = await fetch(`${apiBase}/api/me`, {
    headers: { Cookie: (await cookies()).toString() },
    cache: "no-store",
  });

  if (!res.ok) {
    return Response.json({ email: null, is_superuser: false }, { status: res.status });
  }

  const data = (await res.json()) as { email?: string; is_superuser?: boolean };
  return Response.json({
    email: data.email ?? null,
    is_superuser: data.is_superuser === true,
  });
}
