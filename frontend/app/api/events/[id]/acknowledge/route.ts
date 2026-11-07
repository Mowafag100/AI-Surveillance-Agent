// Route Handler يؤكد مراجعة حدث — POST /api/events/{id}/acknowledge محمي بـ JWT،
// والكوكي HttpOnly لمسار الجلسة يُعاد تمريره يدوياً للـ API (نمط api/me)
import { cookies } from "next/headers";

import { resolveApiBaseUrl } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
): Promise<Response> {
  const { id } = await params;
  const res = await fetch(
    `${resolveApiBaseUrl()}/api/events/${id}/acknowledge`,
    {
      method: "POST",
      headers: { Cookie: (await cookies()).toString() },
      cache: "no-store",
    }
  );
  return new Response(res.body, {
    status: res.status,
    headers: {
      "Content-Type":
        res.headers.get("content-type") ?? "application/json; charset=utf-8",
    },
  });
}
