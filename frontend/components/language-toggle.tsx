"use client";

import { useLanguage } from "@/components/language-context";

export default function LanguageToggle() {
  const { locale, setLocale } = useLanguage();

  return (
    <button
      type="button"
      onClick={() => setLocale(locale === "ar" ? "en" : "ar")}
      suppressHydrationWarning
      className="rounded-md border border-gray-700 px-3 py-1.5 text-sm text-gray-300 hover:bg-gray-700 hover:text-white transition"
      title={locale === "ar" ? "Switch to English" : "التبديل إلى العربية"}
    >
      {locale === "ar" ? "🌐 English" : "🌐 عربي"}
    </button>
  );
}
