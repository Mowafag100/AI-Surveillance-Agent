"use server";

// Server Action لتأكيد مراجعة حدث — يستدعي POST /api/events/{id}/acknowledge
// محمياً بـ JWT (serverFetch يمرر كوكي HttpOnly تلقائياً)
import { serverFetch } from "@/lib/api";

export interface AcknowledgeResult {
  ok?: boolean;
  ackBy?: string;
  ackTime?: string;
  error?: string;
}

export async function acknowledgeEventAction(
  eventId: number
): Promise<AcknowledgeResult> {
  let res: Response;
  try {
    res = await serverFetch(`/api/events/${eventId}/acknowledge`, {
      method: "POST",
    });
  } catch {
    return { error: "تعذر الوصول إلى خادم API" };
  }

  if (!res.ok) {
    let detail = `فشل التأكيد (${res.status})`;
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      // تجاهل — رسالة عامة أدناه
    }
    if (res.status === 401) detail = "يجب تسجيل الدخول لتأكيد المراجعة";
    else if (res.status === 403) detail = "التأكيد متاح للمشرفين فقط";
    return { error: detail };
  }

  try {
    const data = (await res.json()) as {
      acknowledged?: boolean;
      ack_by?: string;
      ack_time?: string;
    };
    return { ok: true, ackBy: data.ack_by, ackTime: data.ack_time };
  } catch {
    return { ok: true };
  }
}
