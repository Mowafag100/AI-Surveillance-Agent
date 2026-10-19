// Route Handler يمرر البث MJPEG من الـ API على النطاق نفسه: كوكي الجلسة
// HttpOnly يُرسل تلقائياً فينجمد حماية JWT، والجسم يمرر تدفقيًا (res.body)
// دون تخزين — فيصل المتصفح تيار MJPEG مباشرة.
import { serverFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
): Promise<Response> {
  const { id } = await params;
  const streamUrl = `/api/cameras/${Number(id)}/stream`;

  // request.signal: عند إغلاق نافذة البث يُقطع المصدر — فيستقبل الـ API
  // GeneratorExit ويحرر الكاميرا (cap.release)
  const res = await serverFetch(streamUrl, { signal: request.signal });

  if (res.status === 401 || res.status === 403) {
    return new Response("Unauthorized", { status: res.status });
  }
  if (!res.ok || !res.body) {
    return new Response("Stream unavailable", { status: res.ok ? 500 : res.status });
  }

  return new Response(res.body, {
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
