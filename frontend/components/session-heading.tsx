"use client";

// رأس شاشات الدخول/التسجيل — يترجم العنوان والوصف بحسب اللغة المختارة
import { useLanguage } from "@/components/language-context";

export default function SessionHeading({
  titleKey,
  subtitleKey,
}: {
  titleKey: string;
  subtitleKey: string;
}) {
  const { t } = useLanguage();

  return (
    <div className="text-center">
      <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-teal-600 text-2xl">
        📷
      </div>
      <h1 className="text-2xl font-bold text-white">{t(titleKey)}</h1>
      <p className="mt-1 text-sm text-gray-400">{t(subtitleKey)}</p>
    </div>
  );
}
