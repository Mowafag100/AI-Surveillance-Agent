"use client";

// AuthContext — جلسة المستخدم موزعة للخادم إلى مكونات العميل (نمط provider)
// ملاحظة: المصادقة نفسها HttpOnly cookie + server actions، والـ context
// يوفّر قراءة هوية المستخدم المحققة server-side داخل مكونات العميل.
import { createContext, useContext } from "react";

export interface Session {
  email: string;
  isSuperuser: boolean;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({
  session,
  children,
}: {
  session: Session;
  children: React.ReactNode;
}) {
  return (
    <SessionContext.Provider value={session}>{children}</SessionContext.Provider>
  );
}

export function useSession(): Session | null {
  return useContext(SessionContext);
}
