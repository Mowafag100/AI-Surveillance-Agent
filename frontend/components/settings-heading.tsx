"use client";

// رأس صفحة الإعدادات — عميل ليتزامن مع اللغة (t)
import { useLanguage } from "@/components/language-context";

export default function SettingsHeading() {
  const { t } = useLanguage();

  return (
    <div className="mb-6">
      <h1 className="text-2xl font-bold mb-2">{t("settingsTitle")}</h1>
      <p className="text-sm text-gray-400">
        {t("settingsSubtitle")}{" "}
        <code className="text-gray-300">{t("settingsSubtitleCode")}</code>{" "}
        {t("settingsSubtitleSuffix")}
      </p>
    </div>
  );
}
