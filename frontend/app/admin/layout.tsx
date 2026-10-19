// تخطيط لوحة الإدارة — الحماية الصارمة من جهة الخادم (نمط dashboard/layout.tsx بالقالب)
// التحقق الحقيقي: استدعاء POST /api/auth/test-token بالكوكي؛ الفشل → /login
import { redirect } from "next/navigation";

import AdminHeaderNav from "@/components/admin-header-nav";
import { SessionProvider, type Session } from "@/components/auth-context";
import { serverFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AdminLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const res = await serverFetch("/api/auth/test-token", { method: "POST" });

  // لا كوكي/كوكي غير صالح (الخادم يعيد 401/403) أو API غير متاح → حماية إجبارية
  if (!res.ok) redirect("/login");

  const currentUser = (await res.json()) as {
    email: string;
    is_superuser: boolean;
  };
  const session: Session = {
    email: currentUser.email,
    isSuperuser: currentUser.is_superuser,
  };

  return (
    <SessionProvider session={session}>
      <div className="min-h-screen bg-gray-900 text-white">
        <header className="border-b border-gray-800 bg-gray-800/60">
          <AdminHeaderNav email={session.email} isSuperuser={session.isSuperuser} />
        </header>
        <main className="max-w-6xl mx-auto px-6 py-8">{children}</main>
      </div>
    </SessionProvider>
  );
}
