// صفحة سجل قرارات الوكيل — server component يجلب آخر القرارات من الـ API
// (GET /api/decisions محمي بـ JWT عبر الكوكي) ثم يمررها لجدول العميل
import DecisionsTable from "@/components/decisions-table";
import { serverFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AdminDecisionsPage() {
  const res = await serverFetch("/api/decisions");
  const data = res.ok ? ((await res.json()) as unknown) : [];

  // التحقق الأساسي من الشكل — جدول فارغ يبقى مصفوفة فارغة لا خطأ
  const rows = Array.isArray(data)
    ? (data as Record<string, unknown>[])
        .filter((d) => typeof d?.id === "number")
        .map((d) => ({
          id: d.id as number,
          timestamp: typeof d.timestamp === "string" ? d.timestamp : "",
          cameraId: typeof d.camera_id === "string" ? d.camera_id : "",
          decisionType:
            typeof d.decision_type === "string" ? d.decision_type : "",
          reasoning: typeof d.reasoning === "string" ? d.reasoning : "",
          confidence: typeof d.confidence === "number" ? d.confidence : null,
        }))
    : [];

  return <DecisionsTable decisions={rows} />;
}
