// Route Handler يمرر قائمة الأحداث من الـ API على النطاق نفسه (نمط api/me) —
// المتصفح لا يصل للـ API مباشرة؛ الكوكي HttpOnly يُعاد تمريره يدوياً للتحقق
import { cookies } from "next/headers";

import { resolveApiBaseUrl } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  // تمرير باراميترات الفلترة كما هي (مثل acknowledged=false)
  const query = new URL(request.url).search;
  const res = await fetch(`${resolveApiBaseUrl()}/api/events${query}`, {
    headers: { Cookie: (await cookies()).toString() },
    cache: "no-store",
  });
  return new Response(res.body, {
    status: res.status,
    headers: {
      "Content-Type":
        res.headers.get("content-type") ?? "application/json; charset=utf-8",
    },
  });
}
