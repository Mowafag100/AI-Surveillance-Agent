"use server";

// Server actions لإدارة الموظفين — تستدعي /api/employees محمياً بـ JWT
// (كوكي HttpOnly auth_cookie يُمرَّر يدوياً: الرفع multipart لا يمكنه serverFetch
// لأنه يفرض ترويسة Content-Type: application/json على كل الطلبات)
import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";

import { API_BASE } from "@/lib/api";

export interface EmployeeActionState {
  error?: string;
  ok?: boolean;
}

// نفس جوهر serverFetch لكن بلا Content-Type مفروض — FormData
// يحتاج multipart/form-data بحدود تلقائية ليقرأه FastAPI (Form/UploadFile)
async function authedFetch(path: string, init: RequestInit): Promise<Response> {
  const cookieStore = await cookies();
  return fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init.headers ?? {}),
      Cookie: cookieStore.toString(),
    },
    cache: "no-store",
  });
}

async function errorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    if (typeof data?.detail === "string") return data.detail;
  } catch {
    // تفاصيل غير JSON — نستخدم النص الافتراضي
  }
  if (res.status === 401) return "يجب تسجيل الدخول أولاً";
  if (res.status === 403) return "هذه العملية متاحة للمشرفين فقط";
  return fallback;
}

export async function createEmployeeAction(
  _prevState: EmployeeActionState,
  formData: FormData
): Promise<EmployeeActionState> {
  const name = String(formData.get("name") ?? "").trim();
  const role = String(formData.get("role") ?? "").trim();
  const file = formData.get("photo");

  if (!name) return { error: "الاسم مطلوب" };
  if (!(file instanceof File) || file.size === 0) {
    return { error: "صورة الوجه مطلوبة" };
  }
  if (!file.type.startsWith("image/")) {
    return { error: "الملف المرفوع ليس صورة" };
  }
  if (file.size > 10 * 1024 * 1024) {
    return { error: "حجم الصورة أكبر من 10 ميغابايت" };
  }

  const payload = new FormData();
  payload.set("name", name);
  payload.set("role", role);
  payload.set("photo", file, file.name);

  let res: Response;
  try {
    res = await authedFetch("/api/employees", {
      method: "POST",
      body: payload,
    });
  } catch {
    return { error: "تعذر الوصول إلى خادم API" };
  }

  if (!res.ok) {
    return { error: await errorDetail(res, `فشل الإضافة (${res.status})`) };
  }

  // إعادة توليد الصفحة ليظهر الموظف الجديد في الجدول فوراً
  revalidatePath("/admin/employees");
  return { ok: true };
}

export async function deleteEmployeeAction(
  employeeId: number
): Promise<{ ok?: boolean; error?: string }> {
  let res: Response;
  try {
    res = await authedFetch(`/api/employees/${employeeId}`, {
      method: "DELETE",
    });
  } catch {
    return { error: "تعذر الوصول إلى خادم API" };
  }

  if (!res.ok && res.status !== 204) {
    return { error: await errorDetail(res, `فشل الحذف (${res.status})`) };
  }

  revalidatePath("/admin/employees");
  return { ok: true };
}
