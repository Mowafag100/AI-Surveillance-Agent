// TEMP diagnostic route — مُخصّص لعزل فشل بروكسي البث في Production. يُحذف بعد التشخيص.
import { cookies } from "next/headers";

import { serverFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

const UP = "/api/cameras/1/stream";

export async function GET(request: Request): Promise<Response> {
  const mode = new URL(request.url).searchParams.get("mode") ?? "raw";
  const ac = new AbortController();
  const cookieStore = await cookies();
  const cookieHeader = { Cookie: cookieStore.toString() };
  const base = process.env.API_URL || "http://localhost:18090";

  let res: Response;
  try {
    switch (mode) {
      case "raw": // fetch عادي بلا signal
        res = await fetch(base + UP, {
          headers: cookieHeader,
          cache: "no-store",
        });
        break;
      case "sig": // signal حيّ (AbortController) — ليس request.signal
        res = await fetch(base + UP, {
          headers: cookieHeader,
          signal: ac.signal,
          cache: "no-store",
        });
        break;
      case "rsig": // signal الخاص بالطلب الوارد
        res = await fetch(base + UP, {
          headers: cookieHeader,
          signal: request.signal,
          cache: "no-store",
        });
        break;
      case "serverfetch": // المسار الحالي
        res = await serverFetch(UP, { signal: request.signal });
        break;
      case "cookies": {
        const s = await cookies();
        return new Response(`cookies-ok:${s.get("auth_cookie") ? "has" : "none"}`);
      }
      case "meta": {
        // لقياس المرحلة المعلّقة: fetch نفسه أم قراءة الجسم أم رجوع الرد
        const t0 = Date.now();
        const r = await fetch(base + UP, {
          headers: cookieHeader,
          cache: "no-store",
        });
        const t1 = Date.now();
        try {
          const reader = r.body!.getReader();
          const readP = reader.read().then((d) => ({
            done: d.done,
            n: d.value?.byteLength ?? 0,
          }));
          const chunk = await Promise.race([
            readP,
            new Promise<null>(re => setTimeout(() => re(null), 1500)),
          ]);
          const t2 = Date.now();
          reader.cancel().catch(() => {});
          r.body?.cancel?.().catch?.(() => {});
          return new Response(
            JSON.stringify({
              status: r.status,
              ct: r.headers.get("content-type"),
              chunkWorked: chunk !== null,
              bytes: (chunk as { n?: number } | null)?.n ?? 0,
              ms: { fetch: t1 - t0, firstRead: t2 - t1 },
            })
          );
        } catch (e) {
          return new Response(`read-fail:${String(e)}`);
        }
      }
      case "pdfping": {
        // عكس المرجع: نفس التمرير مع نقطة PDF في نفس الـ route — يجب أن ينجح
        const r3 = await fetch(base + "/api/reports/pdf", {
          headers: cookieHeader,
          cache: "no-store",
        });
        const ab = await r3.arrayBuffer();
        return new Response(`pdfping=${r3.status} bytes=${ab.byteLength}`);
      }
      case "pump": {
        // نفس المفاهيم لكن pump يدوي عبر ReadableStream مستقل عن socket undici
        const r4 = await fetch(base + UP, {
          headers: cookieHeader,
          cache: "no-store",
        });
        if (!r4.ok) return new Response(`pump-upstream-${r4.status}`, { status: 502 });
        const up = r4;
        const stream = new ReadableStream({
          async start(controller) {
            const reader = up.body!.getReader();
            try {
              for (;;) {
                const { done, value } = await reader.read();
                if (done) break;
                controller.enqueue(value);
              }
              controller.close();
            } catch {
              try { controller.close(); } catch {}
            }
          },
          cancel() {
            up.body?.cancel().catch(() => {});
          },
        });
        return new Response(stream, {
          status: 200,
          headers: {
            "Content-Type":
              r4.headers.get("content-type") ??
              "multipart/x-mixed-replace; boundary=frame",
            "Cache-Control": "no-store, no-transform",
          },
        });
      }
      case "pumpcan": {
        // ضخّ يدوي مع إلغاء المصدر عبر reader.cancel عند قطع العميل
        // (بلا تمرير request.signal إلى fetch نفسه)
        const rc = await fetch(base + UP, {
          headers: cookieHeader,
          cache: "no-store",
        });
        if (!rc.ok) {
          return new Response(`pumpcan-upstream-${rc.status}`, { status: 502 });
        }
        const upB = rc.body!;
        const upReader = upB.getReader();
        request.signal.addEventListener(
          "abort",
          () => {
            upReader.cancel().catch(() => {});
          },
          { once: true }
        );
        const pumpStream = new ReadableStream({
          async start(controller) {
            try {
              for (;;) {
                const { done, value } = await upReader.read();
                if (done) break;
                controller.enqueue(value);
              }
              controller.close();
            } catch {
              try {
                controller.close();
              } catch {}
            }
          },
          cancel() {
            upReader.cancel().catch(() => {});
          },
        });
        return new Response(pumpStream, {
          status: 200,
          headers: {
            "Content-Type":
              rc.headers.get("content-type") ??
              "multipart/x-mixed-replace; boundary=frame",
            "Cache-Control": "no-store, no-transform",
          },
        });
      }
      case "echo": // ما يستخرجه الـ route فعلاً من الكوكي
        return new Response(`cookie=[${cookieStore.toString()}]`);
      case "tokenecho": {
        const r2 = await fetch(base + "/api/auth/test-token", {
          headers: cookieHeader,
          cache: "no-store",
        });
        return new Response(`tokenecho=${r2.status}`);
      }
      default:
        return new Response("bad mode", { status: 400 });
    }
  } catch (e) {
    return new Response(`fetch-throw:${String(e)}`, { status: 502 });
  }

  if (!res.ok) {
    return new Response(`upstream-${res.status}`, { status: 502 });
  }
  return new Response(res.body, {
    status: 200,
    headers: {
      "Content-Type":
        res.headers.get("content-type") ??
        "multipart/x-mixed-replace; boundary=frame",
      "Cache-Control": "no-store, no-transform",
    },
  });
}
