"use client";

// المساعد الذكي للمحادثة (Natural Language Chat) — أيقونة عائمة أسفل الشاشة
// تفتح نافذة دردشة تعمل عبر Route Handler بنفس النطاق (/api/chat) الذي يمرر
// كوكي الجلسة للـ API. الردود من بيانات الأحداث الحقيقية (سجل events.jsonl).

import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Send, X } from "lucide-react";

import { useLanguage } from "@/components/language-context";

interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
}

let nextMessageId = 1;

export default function ChatWidget() {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // رسالة ترحيب عند أول فتح — على ملاحظة أنّ الردود من بيانات الأحداث
  useEffect(() => {
    if (open && messages.length === 0) {
      setMessages([
        {
          id: nextMessageId++,
          role: "assistant",
          content: t("chatWelcome"),
        },
      ]);
    }
  }, [open, messages.length, t]);

  // تمرير آخر الرسائل حيًّا (نمط ChatGPT)
  useEffect(() => {
    if (!open) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, open]);

  const sendMessage = useCallback(async () => {
    const message = input.trim();
    if (!message || sending) return;

    setInput("");
    setError(null);
    setSending(true);
    setMessages((current) => [
      ...current,
      { id: nextMessageId++, role: "user", content: message },
    ]);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ message }),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = (await res.json()) as { reply?: string };
      setMessages((current) => [
        ...current,
        {
          id: nextMessageId++,
          role: "assistant",
          content: (data.reply || t("chatEmptyReply")).trim(),
        },
      ]);
    } catch {
      setError(t("chatError"));
    } finally {
      setSending(false);
    }
  }, [input, sending, t]);

  // Escape يغلق النافذة (نفس نمط نافذة البث في لوحة التحكم)
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      {/* نافذة الدردشة — dialog أسفل الزاوية العائمة */}
      {open && (
        <div
          className="fixed bottom-24 left-6 z-50 flex h-[min(32rem,70vh)] w-full max-w-sm flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-900 shadow-2xl shadow-black/50"
          role="dialog"
          aria-modal="false"
          aria-label={t("chatTitle")}
        >
          <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
            <span className="flex items-center gap-2 text-sm font-semibold text-white">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-500/10 ring-1 ring-inset ring-teal-500/25">
                <Bot className="h-4.5 w-4.5 text-teal-400" />
              </span>
              {t("chatTitle")}
            </span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label={t("chatClose")}
              className="rounded-md p-1 text-slate-400 transition-colors hover:bg-slate-800 hover:text-white"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div
            ref={scrollRef}
            className="flex-1 space-y-3 overflow-y-auto px-4 py-4"
          >
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${
                  message.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <p
                  className={`max-w-[85%] whitespace-pre-wrap rounded-xl px-3 py-2 text-sm leading-relaxed ${
                    message.role === "user"
                      ? "rounded-br-sm bg-teal-600 text-white"
                      : "rounded-bl-sm bg-slate-800 text-slate-200"
                  }`}
                >
                  {message.content}
                </p>
              </div>
            ))}
            {sending && (
              <div className="flex justify-start">
                <p className="inline-flex items-center gap-1.5 rounded-xl rounded-bl-sm bg-slate-800 px-3 py-2 text-sm text-slate-400">
                  <span className="h-1.5 w-1.5 animate-ping rounded-full bg-teal-400" />
                  {t("chatThinking")}
                </p>
              </div>
            )}
            {error && (
              <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
                {error}
              </p>
            )}
          </div>

          <form
            className="flex items-center gap-2 border-t border-slate-800 p-3"
            onSubmit={(event) => {
              event.preventDefault();
              sendMessage();
            }}
          >
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={t("chatPlaceholder")}
              disabled={sending}
              className="h-9 min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-950 px-3 text-sm text-slate-200 placeholder:text-slate-500 focus:border-teal-500 focus:outline-none disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={sending || input.trim().length === 0}
              aria-label={t("chatSend")}
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-teal-600 text-white transition-colors hover:bg-teal-500 disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
        </div>
      )}

      {/* الأيقونة العائمة أسفل الشاشة — تفتح/تغلق الدردشة */}
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label={open ? t("chatClose") : t("chatOpen")}
        className="fixed bottom-6 left-6 z-50 flex h-13 w-13 items-center justify-center rounded-full bg-teal-600 text-white shadow-xl shadow-black/40 ring-1 ring-inset ring-teal-400/40 transition-all hover:scale-105 hover:bg-teal-500 md:h-14 md:w-14"
      >
        {open ? (
          <X className="h-6 w-6" />
        ) : (
          <>
            <Bot className="h-6.5 w-6.5" />
            <span className="absolute -right-0.5 -top-0.5 flex h-3.5 w-3.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-teal-400 opacity-60" />
              <span className="relative inline-flex h-3.5 w-3.5 rounded-full border-2 border-slate-950 bg-emerald-500" />
            </span>
          </>
        )}
      </button>
    </>
  );
}
