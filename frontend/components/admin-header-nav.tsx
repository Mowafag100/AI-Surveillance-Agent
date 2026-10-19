"use client";

// رأس لوحة الإدارة (عميل) — ترجم الروابط وشارة المشرف وزر اللغة
// الجلسة تُمرّر من التخطيط الخادمي (session محقَّقة سلفاً بـ JWT)
import Link from "next/link";

import FormLogout from "@/components/form-logout";
import LanguageToggle from "@/components/language-toggle";
import { useLanguage } from "@/components/language-context";

export default function AdminHeaderNav({
  email,
  isSuperuser,
}: {
  email: string;
  isSuperuser: boolean;
}) {
  const { t } = useLanguage();

  return (
    <div className="max-w-6xl mx-auto flex items-center justify-between px-6 py-4 gap-2 flex-wrap">
      <div className="flex items-center gap-6">
        <Link
          href="/"
          className="text-sm text-gray-300 hover:text-white transition"
        >
          {t("dashboardLink")}
        </Link>
        <a
          href="/admin/settings"
          className="text-sm text-teal-400 hover:text-teal-300 transition"
        >
          {t("settingsLink")}
        </a>
      </div>
      <div className="flex items-center gap-3 flex-wrap">
        <LanguageToggle />
        <span className="text-sm text-gray-400" suppressHydrationWarning>
          {email}
          {isSuperuser && (
            <span className="mx-2 rounded bg-teal-900/60 px-2 py-0.5 text-xs text-teal-300">
              {t("superuserBadge")}
            </span>
          )}
        </span>
        <FormLogout />
      </div>
    </div>
  );
}
