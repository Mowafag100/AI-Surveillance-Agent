"use client";

import { useEffect, useState, useTransition } from "react";
import {
  Activity,
  CheckCircle,
  ClipboardList,
  FileText,
  Footprints,
  Hourglass,
  LayoutDashboard,
  PersonStanding,
  Swords,
  UserRound,
  Video,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";

import { acknowledgeEventAction, type AcknowledgeResult } from "@/actions/events";
import ChatWidget from "@/components/chat-widget";
import LanguageToggle from "@/components/language-toggle";
import { useLanguage } from "@/components/language-context";
import { localeDateTimeTag } from "@/lib/dictionary";

// المتصفح لا يصل للـ API مباشرة — كل الجلبات نسبية عبر وسائط Route Handlers
// على النطاق نفسه (تمرر كوكي الجلسة تلقائياً):
// /api/events · /api/stats/daily · /api/cameras/health · /api/me

type EventType =
  | "fall"
  | "fight"
  | "intrusion"
  | "running"
  | "loitering"
  | "employee_entry";

interface CameraDetails {
  camera_id?: string | number;
  camera_name?: string;
  employee_name?: string;
  role?: string;
  speed_px_s?: number;
  duration_sec?: number;
}

interface SurveillanceEvent {
  id?: number;
  event: string;
  timestamp: string;
  details?: CameraDetails;
  acknowledged?: boolean;
  ack_by?: string;
  ack_time?: string;
}

interface DailyStats {
  total?: number;
  fall?: number;
  fight?: number;
  intrusion?: number;
  running?: number;
  loitering?: number;
}

// قرأتها من /api/cameras/health — حالة الحقيقية المكتوبة من حاوية agent
// (online/offline حسب CAMERA_TIMEOUT_SEC وآخر إطار = last_seen)
interface CameraHealth {
  id: number;
  name: string;
  status: string;
  url: string;
  last_seen?: string | null;
}

interface CameraHealthResponse {
  timestamp?: string | null;
  timeout_sec?: number | null;
  cameras?: CameraHealth[];
}

interface SessionInfo {
  email?: string;
  is_superuser?: boolean;
}

// نافذة البث المباشر: الكاميرا المفتوحة في Modal (فاتورة img = MJPEG عبر وكيل الدخول)
interface LiveViewTarget {
  id: number;
  name: string;
}

const EVENT_META: Record<EventType, { badge: string; key: string; icon: LucideIcon }> = {
  fall: {
    badge: "bg-red-500/10 text-red-400 ring-1 ring-inset ring-red-500/30",
    key: "fall",
    icon: PersonStanding,
  },
  running: {
    badge: "bg-yellow-500/10 text-yellow-400 ring-1 ring-inset ring-yellow-500/30",
    key: "running",
    icon: Zap,
  },
  loitering: {
    badge: "bg-orange-500/10 text-orange-400 ring-1 ring-inset ring-orange-500/30",
    key: "loitering",
    icon: Hourglass,
  },
  fight: {
    badge: "bg-amber-500/10 text-amber-400 ring-1 ring-inset ring-amber-500/30",
    key: "fight",
    icon: Swords,
  },
  intrusion: {
    badge: "bg-sky-500/10 text-sky-400 ring-1 ring-inset ring-sky-500/30",
    key: "intrusion",
    icon: Footprints,
  },
  employee_entry: {
    badge: "bg-emerald-500/10 text-emerald-400 ring-1 ring-inset ring-emerald-500/30",
    key: "employeeEntry",
    icon: UserRound,
  },
};

async function fetchEvents(
  signal: AbortSignal,
  hideAcknowledged: boolean
): Promise<SurveillanceEvent[]> {
  const url = hideAcknowledged
    ? "/api/events?acknowledged=false"
    : "/api/events";
  const res = await fetch(url, { signal });
  if (!res.ok) {
    throw new Error(`HTTP error! status: ${res.status}`);
  }
  const data: unknown = await res.json();
  if (!Array.isArray(data)) {
    throw new Error("Expected an array of events");
  }
  return data as SurveillanceEvent[];
}

async function fetchDailyStats(signal: AbortSignal): Promise<DailyStats | null> {
  const res = await fetch("/api/stats/daily", { signal });
  if (!res.ok) {
    throw new Error(`HTTP error! status: ${res.status}`);
  }
  const data: unknown = await res.json();
  return data && typeof data === "object" ? (data as DailyStats) : null;
}

async function fetchCameraHealth(
  signal: AbortSignal
): Promise<CameraHealth[]> {
  const res = await fetch("/api/cameras/health", { signal });
  if (!res.ok) {
    throw new Error(`HTTP error! status: ${res.status}`);
  }
  const data: unknown = await res.json();
  const payload = data as CameraHealthResponse;
  return Array.isArray(payload.cameras) ? payload.cameras : [];
}

async function fetchSession(signal: AbortSignal): Promise<SessionInfo | null> {
  // عبر Route Handler بنفس النطاق — يمرر كوكي session تلقائياً للـ API
  const res = await fetch("/api/me", { signal });
  if (!res.ok) return null;
  try {
    const data = (await res.json()) as SessionInfo;
    return data && typeof data === "object" ? data : null;
  } catch {
    return null;
  }
}

/** بطاقة إحصائية موحّدة — رقم بخط Monospace + أيقونة بلون كتلة الحدث */
function StatCard({
  label,
  value,
  icon: Icon,
  iconClass,
}: {
  label: string;
  value: number;
  icon: LucideIcon;
  iconClass: string;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-lg shadow-black/20">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm text-slate-400">{label}</p>
          <p className="mt-2 text-3xl font-bold font-mono tabular-nums text-white">
            {value}
          </p>
        </div>
        <span
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${iconClass}`}
        >
          <Icon className="h-5 w-5" />
        </span>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { t, locale } = useLanguage();
  const [events, setEvents] = useState<SurveillanceEvent[]>([]);
  const [stats, setStats] = useState<DailyStats | null>(null);
  const [cameras, setCameras] = useState<CameraHealth[]>([]);
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [hideAcknowledged, setHideAcknowledged] = useState(false);
  const [pendingEventId, setPendingEventId] = useState<number | null>(null);
  const [ackError, setAckError] = useState<string | null>(null);
  const [liveView, setLiveView] = useState<LiveViewTarget | null>(null);
  const [streamError, setStreamError] = useState(false);
  const [, startTransition] = useTransition();

  // ESC يغلق نافذة البث (بجانب زر الإغلاق والنقر خارج الصندوق)
  useEffect(() => {
    if (!liveView) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setLiveView(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [liveView]);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    (async () => {
      const [eventsResult, statsResult, camerasResult, sessionResult] =
        await Promise.allSettled([
          fetchEvents(controller.signal, hideAcknowledged),
          fetchDailyStats(controller.signal),
          fetchCameraHealth(controller.signal),
          fetchSession(controller.signal),
        ]);

      if (!active) return;

      if (eventsResult.status === "fulfilled") {
        setEvents(eventsResult.value);
      } else {
        console.error("Error fetching events:", eventsResult.reason);
        setEvents([]);
      }

      if (statsResult.status === "fulfilled") {
        setStats(statsResult.value);
      } else {
        console.error("Error fetching stats:", statsResult.reason);
        setStats(null);
      }

      if (camerasResult.status === "fulfilled") {
        setCameras(camerasResult.value);
      } else {
        console.error("Error fetching cameras health:", camerasResult.reason);
        setCameras([]);
      }

      if (sessionResult.status === "fulfilled") {
        setSession(sessionResult.value ?? null);
      } else {
        setSession(null);
      }

      setLoading(false);
    })();

    return () => {
      active = false;
      controller.abort();
    };
  }, [hideAcknowledged]);

  const isSuperuser = session?.is_superuser === true;

  const handleAcknowledge = (eventId: number) => {
    if (pendingEventId !== null) return;
    setAckError(null);
    setPendingEventId(eventId);
    startTransition(async () => {
      const result: AcknowledgeResult = await acknowledgeEventAction(eventId);
      if (result.ok) {
        setEvents((current) =>
          current.map((event) =>
            event.id === eventId
              ? {
                  ...event,
                  acknowledged: true,
                  ack_by: result.ackBy,
                  ack_time: result.ackTime,
                }
              : event
          )
        );
      } else {
        setAckError(result.error || t("errorFetching"));
      }
      setPendingEventId(null);
    });
  };

  const formatLastSeen = (lastSeen?: string | null) => {
    if (!lastSeen) return t("neverSeen");
    try {
      return new Date(lastSeen).toLocaleString(localeDateTimeTag(locale));
    } catch {
      return lastSeen;
    }
  };

  const formatEventTime = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleString(localeDateTimeTag(locale));
    } catch {
      return timestamp;
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-200 flex items-center justify-center">
        <div className="flex items-center gap-3 text-slate-400">
          <span className="h-2.5 w-2.5 animate-ping rounded-full bg-teal-400" />
          <p className="text-lg">{t("loading")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      <div className="mx-auto max-w-7xl px-6 py-8">
        {/* الرأس: هوية النظام + إجراءات عامة */}
        <header className="mb-8 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-teal-500/10 ring-1 ring-inset ring-teal-500/25">
              <Activity className="h-6 w-6 text-teal-400" />
            </span>
            <div>
              <h1 className="text-2xl font-bold text-white">
                {t("dashboardTitle")}
              </h1>
              <p className="text-xs text-slate-500">{t("appDescription")}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <LanguageToggle />
            <a
              href="/admin"
              className="inline-flex h-9 items-center gap-2 rounded-md bg-teal-600 px-4 text-sm font-medium text-white transition-colors hover:bg-teal-500"
            >
              <LayoutDashboard className="h-4 w-4" />
              {t("adminPanel")}
            </a>
          </div>
        </header>

        {/* الإحصائيات — بطاقات بأيقونات وأرقام Monospace */}
        {stats && (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6 mb-8">
            <StatCard
              label={t("dailyTotal")}
              value={stats.total || 0}
              icon={Activity}
              iconClass="bg-teal-500/10 text-teal-400"
            />
            <StatCard
              label={t("fall")}
              value={stats.fall || 0}
              icon={PersonStanding}
              iconClass="bg-red-500/10 text-red-400"
            />
            <StatCard
              label={t("running")}
              value={stats.running || 0}
              icon={Zap}
              iconClass="bg-yellow-500/10 text-yellow-400"
            />
            <StatCard
              label={t("loitering")}
              value={stats.loitering || 0}
              icon={Hourglass}
              iconClass="bg-orange-500/10 text-orange-400"
            />
            <StatCard
              label={t("fight")}
              value={stats.fight || 0}
              icon={Swords}
              iconClass="bg-amber-500/10 text-amber-400"
            />
            <StatCard
              label={t("intrusion")}
              value={stats.intrusion || 0}
              icon={Footprints}
              iconClass="bg-sky-500/10 text-sky-400"
            />
          </div>
        )}

        {/* قسم الأحداث: جدول بيانات فعلية بفواصل رفيعة وأعمدة واضحة */}
        <section className="flex flex-wrap items-center justify-between gap-2 mb-4">
          <h2 className="flex items-center gap-2 text-lg font-semibold text-white">
            <ClipboardList className="h-5 w-5 text-teal-400" />
            {t("recentEvents")}
          </h2>
          <div className="flex flex-wrap items-center gap-3">
            <label className="inline-flex cursor-pointer select-none items-center gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={hideAcknowledged}
                onChange={(e) => setHideAcknowledged(e.target.checked)}
                className="h-4 w-4 rounded border-slate-600 bg-slate-800 accent-teal-500"
              />
              {t("hideAcknowledged")}
            </label>
            {/* التحميل عبر Route Handler (نفس النطاق يُرسل كوكي الـ session تلقائياً) */}
            {/* lang من localStorage عبر الزر — التقرير يتصرف بممثولة نفس لغة اللوحة */}
            <a
              href={`/api/reports/pdf?lang=${locale}`}
              className="inline-flex h-9 items-center gap-2 rounded-md bg-emerald-600 px-4 text-sm font-medium text-white transition-colors hover:bg-emerald-500"
              download
            >
              <FileText className="h-4 w-4" />
              {t("exportPdf")}
            </a>
          </div>
        </section>

        <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900 shadow-lg shadow-black/20">
          {events.length === 0 ? (
            <p className="py-10 text-center text-sm text-slate-500">
              {t("noEvents")}
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-xs text-slate-500">
                  <th className="px-4 py-3 text-start font-medium">
                    {t("timeColumn")}
                  </th>
                  <th className="px-4 py-3 text-start font-medium">
                    {t("typeColumn")}
                  </th>
                  <th className="px-4 py-3 text-start font-medium">
                    {t("cameraColumn")}
                  </th>
                  <th className="px-4 py-3 text-end font-medium">
                    {t("actionColumn")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {events.map((event, index) => {
                  const meta =
                    EVENT_META[event.event as EventType] ?? EVENT_META.intrusion;
                  const MetaIcon = meta.icon;
                  const key = `${event.timestamp}-${index}`;
                  return (
                    <tr
                      key={key}
                      className="transition-colors hover:bg-slate-800/50"
                    >
                      <td className="whitespace-nowrap px-4 py-3 align-middle font-mono text-xs text-slate-400">
                        {formatEventTime(event.timestamp)}
                      </td>
                      <td className="px-4 py-3 align-middle">
                        <span
                          className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium ${meta.badge}`}
                        >
                          <MetaIcon className="h-3.5 w-3.5" />
                          {t(meta.key)}
                        </span>
                      </td>
                      <td className="px-4 py-3 align-middle text-slate-300">
                        <span className="inline-flex flex-wrap items-center gap-2">
                          {event.details?.camera_name
                            ? event.details.camera_name
                            : event.details?.camera_id
                              ? `${t("cameraUnknownName")} ${event.details.camera_id}`
                              : t("unknownCamera")}
                          {event.details?.employee_name && (
                            <span className="inline-flex items-center gap-1 whitespace-nowrap rounded bg-emerald-500/10 px-1.5 py-0.5 text-xs text-emerald-300">
                              <UserRound className="h-3 w-3" />
                              {event.details.employee_name}
                            </span>
                          )}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-end align-middle">
                        {event.acknowledged ? (
                          <span
                            className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-emerald-400/90"
                            title={event.ack_time}
                          >
                            <CheckCircle className="h-3.5 w-3.5" />
                            {t("acknowledgedBy")} {event.ack_by ?? t("superuserBadge")}
                          </span>
                        ) : (
                          <button
                            type="button"
                            // التأكيد يتطلب JWT مشرف — يعرض للجميع والخطأ يظهر عند الضغط
                            title={
                              isSuperuser ? undefined : t("loginRequiredAck")
                            }
                            disabled={pendingEventId === event.id}
                            onClick={() => event.id && handleAcknowledge(event.id)}
                            className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-md bg-teal-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-teal-500 disabled:opacity-50"
                          >
                            <CheckCircle className="h-3.5 w-3.5" />
                            {pendingEventId === event.id
                              ? t("acknowledging")
                              : t("acknowledgeButton")}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
        {ackError && (
          <p className="mt-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {ackError}
          </p>
        )}

        {/* حالة الكاميرات (الحقيقية من /api/cameras/health) */}
        <section className="mt-8">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-white">
            <Video className="h-5 w-5 text-teal-400" />
            {t("cameraStatusSection")}
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-4">
            {cameras.length === 0 ? (
              <p className="col-span-full py-8 text-center text-sm text-slate-500">
                {t("noCameras")}
              </p>
            ) : (
              cameras.map((camera) => (
                <div
                  key={camera.id}
                  className="rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-lg shadow-black/20"
                  title={camera.url}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium text-white">
                      {camera.name}
                    </span>
                    <Video className="h-4 w-4 shrink-0 text-slate-600" />
                  </div>
                  <span className="mt-4 flex items-center gap-2 text-xs">
                    {/* نقطة مضيئة (Glowing Dot) — إيقاع ping حول النقطة الأساسية */}
                    <span className="relative flex h-2.5 w-2.5 shrink-0">
                      <span
                        className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${
                          camera.status === "online"
                            ? "bg-emerald-400"
                            : "bg-red-400"
                        }`}
                      />
                      <span
                        className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
                          camera.status === "online"
                            ? "bg-emerald-500"
                            : "bg-red-500"
                        }`}
                      />
                    </span>
                    <span
                      className={
                        camera.status === "online"
                          ? "text-emerald-400"
                          : "text-red-400"
                      }
                    >
                      {camera.status === "online"
                        ? t("cameraOnline")
                        : t("cameraOffline")}
                    </span>
                  </span>
                  <p className="mt-2 truncate text-xs text-slate-500">
                    {t("lastSeen")}: {formatLastSeen(camera.last_seen)}
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      setStreamError(false);
                      setLiveView({ id: camera.id, name: camera.name });
                    }}
                    className="mt-4 flex w-full items-center justify-center gap-2 rounded-md bg-slate-800 px-3 py-1.5 text-sm text-slate-200 ring-1 ring-inset ring-slate-700 transition-colors hover:bg-slate-700"
                  >
                    {t("liveView")}
                  </button>
                </div>
              ))
            )}
          </div>
        </section>
      </div>

      {/* نافذة البث المباشر (MJPEG عبر وكيل /api/cameras/[id]/stream بنفس نطاق الجلسة) */}
      {liveView && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          onClick={() => setLiveView(null)}
        >
          <div
            className="w-full max-w-3xl overflow-hidden rounded-xl border border-slate-800 bg-slate-900 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 px-4 py-3">
              <span className="flex items-center gap-2 text-sm font-medium text-white">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-60" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-red-500" />
                </span>
                {liveView.name} — {t("liveViewTitle")}
              </span>
              <span className="flex flex-wrap items-center gap-3">
                {streamError && (
                  <span className="text-xs text-red-300">{t("streamError")}</span>
                )}
                <button
                  type="button"
                  onClick={() => setLiveView(null)}
                  className="inline-flex items-center gap-1.5 rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 transition-colors hover:bg-slate-800 hover:text-white"
                >
                  <X className="h-3.5 w-3.5" />
                  {t("closeModal")}
                </button>
              </span>
            </div>
            {/* بإزالة الـ img (unmount) يُقطع الطلب ويُحرر VideoCapture في الخادم */}
            <div className="p-3">
              {/* eslint-disable-next-line @next/next/no-img-element -- <Image/> لا يدعم تيار multipart/x-mixed-replace المتواصل */}
              <img
                key={liveView.id}
                src={`/api/cameras/${liveView.id}/stream`}
                alt={liveView.name}
                onError={() => setStreamError(true)}
                className="w-full rounded-md bg-black shadow-lg"
              />
            </div>
          </div>
        </div>
      )}

      {/* المساعد الذكي — أيقونة عائمة أسفل الشاشة تفتح دردشة (POST /api/chat) */}
      <ChatWidget />
    </div>
  );
}
