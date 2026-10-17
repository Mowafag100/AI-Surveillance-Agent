"use server";

// Server Actions للمصادقة — مستوحاة حرفياً من src/actions/auth.ts في القالب
// (الدخول يعيد Token؛ التوكن يُخزَّن ككوكي HttpOnly من جهة الخادم)
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { API_BASE, AUTH_COOKIE } from "@/lib/api";

export interface AuthActionState {
  error?: string;
  ok?: boolean;
}

interface TokenResponse {
  access_token: string;
  expires: number;
}

async function readErrorDetail(res: Response): Promise<string | undefined> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    if (typeof data?.detail === "string") return data.detail;
  } catch {
    // تجاهل — سنوقف برسالة عامة أدناه
  }
  return undefined;
}

export async function loginAction(
  _prevState: AuthActionState,
  formData: FormData
): Promise<AuthActionState> {
  const username = String(formData.get("username") ?? "").trim();
  const password = String(formData.get("password") ?? "");

  // OAuth2PasswordRequestForm في الباكند: صيغة form-urlencoded
  const body = new URLSearchParams({ username, password });

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
      cache: "no-store",
    });
  } catch {
    return { error: "تعذر الوصول إلى خادم API" };
  }

  if (!res.ok) {
    return { error: (await readErrorDetail(res)) ?? "فشل تسجيل الدخول" };
  }

  const token = (await res.json()) as TokenResponse;

  // ضبط الكوكي — تطابق كود القالب (Cookie-Having server action)
  const cookieStore = await cookies();
  cookieStore.set({
    name: AUTH_COOKIE,
    value: token.access_token,
    expires: new Date(Number(token.expires) * 1000),
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    sameSite: "lax",
  });

  redirect("/admin");
}

export async function registerAction(
  _prevState: AuthActionState,
  formData: FormData
): Promise<AuthActionState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const passwordConfirm = String(formData.get("password_confirm") ?? "");

  if (password !== passwordConfirm) {
    return { error: "كلمتا المرور غير متطابقتين" };
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
      cache: "no-store",
    });
  } catch {
    return { error: "تعذر الوصول إلى خادم API" };
  }

  if (!res.ok) {
    return { error: (await readErrorDetail(res)) ?? "فشل التسجيل" };
  }

  // نمط القالب: التسجيل لا يدخل جلسة — المستخدم يسجل دخوله بعدها
  return { ok: true };
}

export async function logoutAction(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.delete(AUTH_COOKIE);
  redirect("/login");
}
