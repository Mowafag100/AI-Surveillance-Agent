// فهرس لوحة الإدارة — تحويل مباشر لصفحة الإعدادات
import { redirect } from "next/navigation";

export default function AdminIndexPage() {
  redirect("/admin/settings");
}
