// تخطيط لوحة الإدارة — الحماية الصارمة من جهة الخادم (نمط dashboard/layout.tsx بالقالب)
// التحقق الحقيقي: استدعاء POST /api/auth/test-token بالكوكي؛ الفشل → /login
import { redirect } from "next/navigation";

import FormLogout from "@/components/form-logout";
import { SessionProvider, type Session } from "@/components/auth-context";
import { serverFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AdminLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const res = await serverFetch("/api/auth/test-token", { method: "POST" });

  // لا كوكي/كوكي غير صالح (الخادم يعيد 401/403) أو API غير متاح → защитا إجبارية
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
          <div className="max-w-6xl mx-auto flex items-center justify-between px-6 py-4">
            <div className="flex items-center gap-6">
              <a
                href="/"
                className="text-sm text-gray-300 hover:text-white transition"
              >
                📊 لوحة المراقبة
              </a>
              <a
                href="/admin/settings"
                className="text-sm text-teal-400 hover:text-teal-300 transition"
              >
                ⚙️ الإعدادات
              </a>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-sm text-gray-400" suppressHydrationWarning>
                {session.email}
                {session.isSuperuser && (
                  <span className="ml-2 rounded bg-teal-900/60 px-2 py-0.5 text-xs text-teal-300">
                    مشرف
                  </span>
                )}
              </span>
              <FormLogout />
            </div>
          </div>
        </header>
        <main className="max-w-6xl mx-auto px-6 py-8">{children}</main>
      </div>
    </SessionProvider>
  );
}
