// Route Handler يمرر إحصائيات اليوم من الـ API على النطاق نفسه (نمط api/me)
import { cookies } from "next/headers";

import { resolveApiBaseUrl } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  const res = await fetch(`${resolveApiBaseUrl()}/api/stats/daily`, {
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
