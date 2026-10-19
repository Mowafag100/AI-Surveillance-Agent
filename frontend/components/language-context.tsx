"use client";

// LanguageContext — مصدر اللغة t(key)/locale/setLocale لكل الصفحات.
// الحالة عبر useSyncExternalStore (localStorage هو المصدر): الخادم يرسم "ar"
// (يطابق layout اتجاه RTL تماماً)، والمتصفح يقرأ اللغة المحفوظة بعد الترميز
// ثم يحدث document.documentElement.dir/lang في مؤثر (تحديث نظام خارجي).

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
} from "react";

import {
  defaultLocale,
  translate,
  type Locale,
} from "@/lib/dictionary";

const STORAGE_KEY = "surveillance.locale";

function isLocale(value: string | null): value is Locale {
  return value === "ar" || value === "en";
}

// ---------------- store خارجي (localStorage) ----------------

const listeners = new Set<() => void>();

function subscribe(callback: () => void): () => void {
  listeners.add(callback);
  window.addEventListener("storage", callback);
  return () => {
    listeners.delete(callback);
    window.removeEventListener("storage", callback);
  };
}

function getLocaleSnapshot(): Locale {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isLocale(stored)) return stored;
  } catch {
    // التخزين غير متاح — الافتراضي
  }
  return defaultLocale;
}

// خادم يرسم العربية دائماً — لكن حتى لا تتعار (#hydration) مع الإعدادات الافتراضية للصفحات
function getLocaleServerSnapshot(): Locale {
  return defaultLocale;
}

function setStoredLocale(next: Locale) {
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // التخزين غير متاح — التبديل يزال إعادة التحميل
  }
  for (const listener of listeners) listener();
}

// ---------------- Context ----------------

interface LanguageContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  /** الترجمة بمفتاح مفطّع — يعيد المفتاح نفسه إن لم يوجد */
  t: (key: string) => string;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

function applyLocaleDocument(locale: Locale) {
  if (typeof document === "undefined") return;
  document.documentElement.lang = locale;
  document.documentElement.dir = locale === "ar" ? "rtl" : "ltr";
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const locale = useSyncExternalStore(
    subscribe,
    getLocaleSnapshot,
    getLocaleServerSnapshot
  );

  // مزامنة نظام خارجي (اتجاه/لسان المستند) مع اللغة الحالية
  useEffect(() => {
    applyLocaleDocument(locale);
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setStoredLocale(next);
  }, []);

  const t = useCallback(
    (key: string) => translate(locale, key),
    [locale]
  );

  const value = useMemo(
    () => ({ locale, setLocale, t }),
    [locale, setLocale, t]
  );

  return (
    <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
  );
}

export function useLanguage(): LanguageContextValue {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useLanguage must be used within LanguageProvider");
  }
  return context;
}
