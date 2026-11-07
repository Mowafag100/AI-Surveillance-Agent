// Route Handler يمرر البث MJPEG من الـ API على النطاق نفسه: كوكي الجلسة
// HttpOnly يُستخرج صراحةً ويُمرَّر في ترويسة الطلب، والجسم يُضَخّ تدفقيًا
// (pump عبر ReadableStream مستقل) دون تخزين.
//
// لماذا pump يدوي بدل إرجاع res.body مباشرة؟ إرجاع جسم fetch (undici)
// مباشرة في Route Handler يكسر الـ pipe في الإنتاج خلف Cloudflare
// ("failed to pipe response" / "terminated") فيصل خطأ فارغ للمتصفح
// ولا تعمل النافذة إطلاقًا؛ الضخ اليدوي يعزل تيار الوسيط عن socket undici.
//
// لماذا لا نمرر request.signal إلى fetch؟ إلغاء الطلب عبر signal يفسد
// مصفوفة sockets في undici (UND_ERR_SOCKET بعد أول قطع عميل) فيفشل كل
// طلب لاحق في العملية؛ الإلغاء هنا عبر reader.cancel() عند قطع العميل.
// request.signal: إغلاق نافذة البث يقتل الضخ — فيستقبل الـ API
// GeneratorExit ويحرر الكاميرا (cap.release).
import { cookies } from "next/headers";

import { resolveApiBaseUrl } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
): Promise<Response> {
  const { id } = await params;
  const streamUrl = `/api/cameras/${Number(id)}/stream`;

  // استخراج الكوكي صراحةً وتمريره في ترويسة الطلب إلى الـ API
  const cookieStore = await cookies();

  let res: Response;
  try {
    res = await fetch(`${resolveApiBaseUrl()}${streamUrl}`, {
      headers: {
        Cookie: cookieStore.toString(),
      },
      cache: "no-store",
    });
  } catch {
    // فشل فتح المصدر (تعذر الاتصال بالـ API) — لا وجهة أخرى لها
    return new Response("Stream unavailable", { status: 502 });
  }

  if (res.status === 401 || res.status === 403) {
    return new Response("Unauthorized", { status: res.status });
  }
  if (!res.ok || !res.body) {
    return new Response("Stream unavailable", { status: res.ok ? 500 : res.status });
  }

  const upstreamBody = res.body;
  const reader = upstreamBody.getReader();

  const releaseUpstream = () => {
    reader.cancel().catch(() => {});
  };

  // قطع العميل (إغلاق نافذة البث) → إلغاء القارئ → انتهاء upstream فيُلغى
  // المولد في الـ API بالتزامن مع فحص is_disconnected في كل دورة
  if (request.signal.aborted) {
    releaseUpstream();
    return new Response(null, { status: 204 });
  }
  request.signal.addEventListener("abort", releaseUpstream, { once: true });

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
        // انقطاع المصدر/العميل أثناء النقل — إنهاء تيار العميل بسلام
        try {
          controller.close();
        } catch {}
      }
    },
    cancel() {
      releaseUpstream();
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      "Content-Type":
        res.headers.get("content-type") ??
        "multipart/x-mixed-replace; boundary=frame",
      "Cache-Control": "no-store, no-transform",
      "X-Accel-Buffering": "no",
    },
  });
}
