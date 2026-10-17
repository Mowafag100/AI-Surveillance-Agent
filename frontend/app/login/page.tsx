// صفحة تسجيل الدخول — مقدّمة من القالب app/login/page.tsx (مكيّفة بلا ShadcnUI)
// Pattern القالب: إن كان المستخدم مصادقاً (كوكي صالح) نحوّله للوحة الإدارة
import { redirect } from "next/navigation";

import FormLogin from "@/components/form-login";
import { AUTH_COOKIE, serverFetch } from "@/lib/api";

import { cookies } from "next/headers";

export const dynamic = "force-dynamic";

export default async function LoginPage() {
  // فحص JSON صامت: كوكي موجود وJWT سليم؟ → /admin
  const cookieStore = await cookies();
  if (cookieStore.has(AUTH_COOKIE)) {
    try {
      const res = await serverFetch("/api/auth/test-token", { method: "POST" });
      if (res.ok) redirect("/admin");
    } catch {
      // الخادم غير متاح — نُظهر صفحة الدخول عادي
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-900 px-4">
      <div className="w-full max-w-md space-y-8 rounded-xl border border-gray-800 bg-gray-800/60 p-8 shadow-xl">
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-teal-600 text-2xl">
            📷
          </div>
          <h1 className="text-2xl font-bold text-white">لوحة إدارة المراقبة</h1>
          <p className="mt-1 text-sm text-gray-400">
            سجّل دخولك للوصول إلى إعدادات النظام
          </p>
        </div>
        <FormLogin />
      </div>
    </div>
  );
}
