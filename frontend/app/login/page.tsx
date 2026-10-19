// صفحة تسجيل الدخول — مقدّمة من القالب app/login/page.tsx (مكيّفة بلا ShadcnUI)
// Pattern القالب: إن كان المستخدم مصادقاً (كوكي صالح) نحوّله للوحة الإدارة
import { redirect } from "next/navigation";

import FormLogin from "@/components/form-login";
import LanguageToggle from "@/components/language-toggle";
import SessionHeading from "@/components/session-heading";
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
    <div className="relative min-h-screen flex items-center justify-center bg-gray-900 px-4">
      <div className="w-full max-w-md space-y-8 rounded-xl border border-gray-800 bg-gray-800/60 p-8 shadow-xl">
        <div className="absolute top-4 ltr:right-4 rtl:left-4">
          <LanguageToggle />
        </div>
        <SessionHeading titleKey="loginTitle" subtitleKey="loginSubtitle" />
        <FormLogin />
      </div>
    </div>
  );
}
