// صفحة التسجيل (signup) — تستعمل FormRegister نفسه المستعمل في /register
import { redirect } from "next/navigation";

import FormRegister from "@/components/form-register";
import LanguageToggle from "@/components/language-toggle";
import SessionHeading from "@/components/session-heading";
import { AUTH_COOKIE, serverFetch } from "@/lib/api";

import { cookies } from "next/headers";

export const dynamic = "force-dynamic";

export default async function SignupPage() {
  const cookieStore = await cookies();
  if (cookieStore.has(AUTH_COOKIE)) {
    try {
      const res = await serverFetch("/api/auth/test-token", { method: "POST" });
      if (res.ok) redirect("/admin");
    } catch {
      // الخادم غير متاح — نُظهر صفحة التسجيل عادي
    }
  }

  return (
    <div className="relative min-h-screen flex items-center justify-center bg-gray-900 px-4">
      <div className="w-full max-w-md space-y-8 rounded-xl border border-gray-800 bg-gray-800/60 p-8 shadow-xl">
        <div className="absolute top-4 ltr:right-4 rtl:left-4">
          <LanguageToggle />
        </div>
        <SessionHeading titleKey="signupTitle" subtitleKey="signupSubtitle" />
        <FormRegister />
      </div>
    </div>
  );
}
