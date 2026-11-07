// صفحة الموظفين — server component يجلب القائمة ثم يمررها لنموذج العميل
import EmployeesManager from "@/components/employees-manager";
import { serverFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AdminEmployeesPage() {
  const res = await serverFetch("/api/employees");
  const employees = res.ok ? ((await res.json()) as unknown) : [];

  // التحقق الأساسي من الشكل — البصمة لا تصل للواجهة أصلاً (id/name/role فقط)
  const rows = Array.isArray(employees)
    ? (employees as Record<string, unknown>[])
        .filter((e) => typeof e?.id === "number")
        .map((e) => ({
          id: e.id as number,
          name: typeof e.name === "string" ? e.name : "",
          role: typeof e.role === "string" ? e.role : "",
        }))
    : [];

  return (
    <div className="max-w-2xl">
      <EmployeesManager employees={rows} />
    </div>
  );
}
