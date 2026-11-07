// Route Handler يمرّر تقرير PDF من الـ API على النطاق نفسه، بحيث يُستخرج
// كوكي الجلسة (HttpOnly) صراحةً ويُمرَّر في ترويسة الطلب ويُنجّز المصادقة.
// الجسم يمرّر عبر pump يدوي (ReadableStream مستقل) بدل res.body مباشرة —
// إرجاع جسم fetch (undici) مباشرة قد يكسر الـ pipe في الإنتاج خلف Cloudflare
// ("failed to pipe response") فلا يُحمَّل الملف؛ الضخ اليدوي يعزله عن socket
// undici ويحفظ Content-Length الأصلي (مهم لعابر Cloudflare/التخزين).
import { cookies } from "next/headers";

import { resolveApiBaseUrl } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  // يُمرَّر period و lang ضمن النطاق المعتمد — اللغة تأتي من زر التقرير
  // (localStorage في language-context؛ عدم موجودها = الافتراضي عربي في الـ API)
  const params = new URL(request.url).searchParams;
  const periodQuery = params.get("period") === "week" ? "period=week" : "";
  const langParam = ["ar", "en"].includes(params.get("lang") ?? "")
    ? `lang=${params.get("lang")}`
    : "";
  const query: string = [periodQuery, langParam].filter(Boolean).join("&");

  const cookieStore = await cookies();
  let res: Response;
  try {
    res = await fetch(
      `${resolveApiBaseUrl()}/api/reports/pdf${query ? `?${query}` : ""}`,
      {
        headers: { Cookie: cookieStore.toString() },
        cache: "no-store",
      }
    );
  } catch {
    return new Response("تعذر الوصول إلى خادم تقارير", { status: 502 });
  }

  if (res.status === 401 || res.status === 403) {
    return new Response(
      "توليد التقرير يتطلب الدخول بصلاحية مشرف (الجلسة غير صالحة)",
      { status: 403 }
    );
  }
  if (!res.ok || !res.body) {
    return new Response("فشل توليد التقرير من الخادم", { status: res.status });
  }

  const upstreamBody = res.body;
  const contentLength = res.headers.get("content-length");
  const reader = upstreamBody.getReader();

  // ضخّ محتوى PDF بايتًا بايتًا — يعزل الرد عن socket undici نفسه ويحفظ
  // أي تجزئات حرة؛ أي انقطاع مصدر يُغلق التيار قسرًا (المتصفح يفشل التحميل
  // بدل حفظ ملف تالف)
  const stream = new ReadableStream({
    async start(controller) {
      try {
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          controller.enqueue(value);
        }
        controller.close();
      } catch {
        try {
          controller.error(new Error("upstream terminated"));
        } catch {}
      }
    },
    cancel() {
      reader.cancel().catch(() => {});
    },
  });

  // تمرير الرد مع الاحتفاظ بمحتوى PDF واسم الملف وطوله الأصلي من الـ API
  const headers: Record<string, string> = {
    "Content-Type": res.headers.get("content-type") ?? "application/pdf",
    "Content-Disposition":
      res.headers.get("content-disposition") ??
      'attachment; filename="surveillance_report.pdf"',
    "Cache-Control": "no-store",
  };
  if (contentLength) headers["Content-Length"] = contentLength;

  return new Response(stream, { status: res.status, headers });
}
