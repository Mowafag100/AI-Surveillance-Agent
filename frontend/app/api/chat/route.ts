// Route Handler يمرر أسئلة المساعد الذكي إلى POST /api/chat على النطاق نفسه —
// المتصفح لا يصل للـ API مباشرة؛ الكوكي HttpOnly يُعاد تمريره يدوياً
// (النقط مكفولة محمية JWT في الخادم: CurrentUser في src/api.py)
import { cookies } from "next/headers";

import { resolveApiBaseUrl } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  let body: string;
  try {
    body = await request.text();
  } catch {
    return Response.json(
      { reply: null, error: "جسد الطلب غير صالح" },
      { status: 400 }
    );
  }

  const res = await fetch(`${resolveApiBaseUrl()}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Cookie: (await cookies()).toString(),
    },
    body,
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
