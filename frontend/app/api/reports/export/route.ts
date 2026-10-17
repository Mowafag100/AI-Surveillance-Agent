// Route Handler يمرّر تنزيل CSV من الـ API على النطاق نفسه، بحيث يحمل
// المتصفح كوكي الجلسة (HttpOnly) تلقائياً مع الطلب ويُنجّز المصادقة
import { cookies } from "next/headers";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  const apiBase =
    process.env.API_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://localhost:8090";

  const res = await fetch(`${apiBase}/api/reports/export`, {
    headers: { Cookie: (await cookies()).toString() },
    cache: "no-store",
  });

  if (res.status === 401 || res.status === 403) {
    return new Response(
      "تحميل التقرير يتطلب الدخول بصلاحية مشرف (الجلسة غير صالحة)",
      { status: 403 }
    );
  }
  if (!res.ok) {
    return new Response("فشل توليد التقرير من الخادم", { status: res.status });
  }

  // تمرير الرد مع الاحتفاظ بمحتوى CSV واسم الملف من الـ API
  return new Response(res.body, {
    status: res.status,
    headers: {
      "Content-Type":
        res.headers.get("content-type") ?? "text/csv; charset=utf-8",
      "Content-Disposition":
        res.headers.get("content-disposition") ??
        'attachment; filename="events_report.csv"',
    },
  });
}
