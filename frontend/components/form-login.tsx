"use client";

// نموذج الدخول — مقدّم من القالب components/auth/form-login.tsx (مكيّف: بدون ردوف)
import { useActionState } from "react";
import Link from "next/link";

import { loginAction, type AuthActionState } from "@/actions/auth";

const initialState: AuthActionState = {};

export default function FormLogin() {
  // useActionState (React 19): يعاد التوجيه من داخل الـ action عند النجاح
  const [state, formAction, isPending] = useActionState(
    loginAction,
    initialState
  );

  return (
    <form action={formAction} className="space-y-4 w-full">
      <div>
        <label
          htmlFor="username"
          className="block text-sm font-medium text-gray-300 mb-1"
        >
          البريد الإلكتروني
        </label>
        <input
          id="username"
          name="username"
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
          كلمة المرور
        </label>
        <input
          id="password"
          name="password"
          type="password"
          required
          minLength={6}
          autoComplete="current-password"
          placeholder="••••••••"
          disabled={isPending}
          className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-white placeholder:text-gray-500 focus:border-teal-500 focus:outline-none"
        />
      </div>

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
        {isPending ? "جارٍ تسجيل الدخول..." : "دخول"}
      </button>

      <p className="text-sm text-gray-400 text-center">
        ليس لديك حساب؟{" "}
        <Link
          href="/signup"
          className="text-teal-400 hover:text-teal-300 hover:underline"
        >
          سجّل الآن
        </Link>
      </p>
    </form>
  );
}
