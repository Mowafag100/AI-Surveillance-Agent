"use client";

// نموذج التسجيل — مقدّم من القالب components/auth/form-register.tsx (مكيّف)
import { useActionState } from "react";
import Link from "next/link";

import { registerAction, type AuthActionState } from "@/actions/auth";
import { useLanguage } from "@/components/language-context";

const initialState: AuthActionState = {};

export default function FormRegister() {
  const { t } = useLanguage();
  const [state, formAction, isPending] = useActionState(
    registerAction,
    initialState
  );

  return (
    <form action={formAction} className="space-y-4 w-full">
      <div>
        <label
          htmlFor="email"
          className="block text-sm font-medium text-gray-300 mb-1"
        >
          {t("emailLabel")}
        </label>
        <input
          id="email"
          name="email"
          type="email"
          required
          autoComplete="email"
          placeholder="admin@example.com"
          disabled={isPending}
          className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-white placeholder:text-gray-500 focus:border-teal-500 focus:outline-none"
        />
      </div>

      <div>
        <label
          htmlFor="password"
          className="block text-sm font-medium text-gray-300 mb-1"
        >
          {t("passwordHint")}
        </label>
        <input
          id="password"
          name="password"
          type="password"
          required
          minLength={6}
          maxLength={40}
          autoComplete="new-password"
          disabled={isPending}
          className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-white focus:border-teal-500 focus:outline-none"
        />
      </div>

      <div>
        <label
          htmlFor="password_confirm"
          className="block text-sm font-medium text-gray-300 mb-1"
        >
          {t("confirmPasswordLabel")}
        </label>
        <input
          id="password_confirm"
          name="password_confirm"
          type="password"
          required
          minLength={6}
          maxLength={40}
          autoComplete="new-password"
          disabled={isPending}
          className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-white focus:border-teal-500 focus:outline-none"
        />
      </div>

      {state.ok && (
        <p className="rounded-md border border-green-800 bg-green-900/40 px-3 py-2 text-sm text-green-300">
          {t("registerSuccess")}{" "}
          <Link
            href="/login"
            className="font-medium text-green-200 hover:underline"
          >
            {t("registerSuccessLink")}
          </Link>
        </p>
      )}

      {state.error && (
        <p className="rounded-md border border-red-800 bg-red-900/40 px-3 py-2 text-sm text-red-300">
          {state.error}
        </p>
      )}

      <button
        type="submit"
        disabled={isPending}
        className="w-full h-11 rounded-md bg-teal-600 font-medium text-white hover:bg-teal-700 disabled:opacity-50"
      >
        {isPending ? t("signingUp") : t("signupButton")}
      </button>

      <p className="text-sm text-gray-400 text-center">
        {t("haveAccount")}{" "}
        <Link
          href="/login"
          className="text-teal-400 hover:text-teal-300 hover:underline"
        >
          {t("loginLink")}
        </Link>
      </p>
    </form>
  );
}
