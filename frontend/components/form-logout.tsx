"use client";

// زر تسجيل الخروج — يستدعي logoutAction (server action) لحذف الكوكي HttpOnly
import { logoutAction } from "@/actions/auth";
import { useLanguage } from "@/components/language-context";

export default function FormLogout() {
  const { t } = useLanguage();

  return (
    <form action={logoutAction}>
      <button
        type="submit"
        className="rounded-md border border-gray-700 px-3 py-1.5 text-sm text-gray-300 hover:bg-gray-700 hover:text-white transition"
      >
        {t("logoutButton")}
      </button>
    </form>
  );
}
