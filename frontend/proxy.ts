// Middleware لحماية المسارات — بعكس القالب الذي يعتمد على layouts فقط.
// ملاحظة: في Next.js 16 أصبحت طريقة middleware.ts متجاوزة رسمياًtyped
// استبدلها بصيغة proxy.ts (نفس المسار المطابق matcher).
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const AUTH_COOKIE = "auth_cookie";

// مفحوص UX-level: وجود/غياب كوكي فقط (التحقق الحقيقي في admin/layout + API)
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // /admin/** تتطلب كوكي جلسة — وإلا التحويل لصفحة الدخول
  if (pathname.startsWith("/admin") && !request.cookies.has(AUTH_COOKIE)) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  // مستخدم لديه كوكي (حتى لو منتهي) لا يلزمه الدخول/التسجيل مرة أخرى
  if (
    (pathname === "/login" || pathname === "/register") &&
    request.cookies.has(AUTH_COOKIE)
  ) {
    return NextResponse.redirect(new URL("/admin", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/admin/:path*", "/login", "/register", "/signup"],
};
