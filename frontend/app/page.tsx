"use client";

import { useEffect, useState, useTransition } from "react";

import { acknowledgeEventAction, type AcknowledgeResult } from "@/actions/events";
import LanguageToggle from "@/components/language-toggle";
import { useLanguage } from "@/components/language-context";
import { localeDateTimeTag } from "@/lib/dictionary";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8090";

type EventType = "fall" | "fight" | "intrusion";

interface CameraDetails {
  camera_id?: string | number;
  camera_name?: string;
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

const EVENT_META: Record<EventType, { badge: string; key: string }> = {
  fall: { badge: "bg-red-900/50 text-red-300", key: "fall" },
  fight: { badge: "bg-yellow-900/50 text-yellow-300", key: "fight" },
  intrusion: { badge: "bg-blue-900/50 text-blue-300", key: "intrusion" },
};

async function fetchEvents(
  signal: AbortSignal,
  hideAcknowledged: boolean
): Promise<SurveillanceEvent[]> {
  const url = hideAcknowledged
    ? `${API_BASE}/api/events?acknowledged=false`
    : `${API_BASE}/api/events`;
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
  const res = await fetch(`${API_BASE}/api/stats/daily`, { signal });
  if (!res.ok) {
    throw new Error(`HTTP error! status: ${res.status}`);
  }
  const data: unknown = await res.json();
  return data && typeof data === "object" ? (data as DailyStats) : null;
}

async function fetchCameraHealth(
  signal: AbortSignal
): Promise<CameraHealth[]> {
  const res = await fetch(`${API_BASE}/api/cameras/health`, { signal });
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
  const [, startTransition] = useTransition();

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
      <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center">
        <p className="text-xl">{t("loading")}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-6 gap-2 flex-wrap">
          <h1 className="text-3xl font-bold">{t("dashboardTitle")}</h1>
          <div className="flex items-center gap-2">
            <LanguageToggle />
            <a
              href="/admin"
              className="rounded-md bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-700 transition"
            >
              {t("adminPanel")}
            </a>
          </div>
        </div>

        {/* الإحصائيات */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
              <p className="text-gray-400 text-sm">{t("dailyTotal")}</p>
              <p className="text-2xl font-bold">{stats.total || 0}</p>
            </div>
            <div className="bg-red-900/30 p-4 rounded-lg border border-red-800">
              <p className="text-gray-400 text-sm">{t("fall")}</p>
              <p className="text-2xl font-bold text-red-400">{stats.fall || 0}</p>
            </div>
            <div className="bg-yellow-900/30 p-4 rounded-lg border border-yellow-800">
              <p className="text-gray-400 text-sm">{t("fight")}</p>
              <p className="text-2xl font-bold text-yellow-400">{stats.fight || 0}</p>
            </div>
            <div className="bg-blue-900/30 p-4 rounded-lg border border-blue-800">
              <p className="text-gray-400 text-sm">{t("intrusion")}</p>
              <p className="text-2xl font-bold text-blue-400">{stats.intrusion || 0}</p>
            </div>
          </div>
        )}

        {/* قائمة الأحدث */}
        <div className="flex items-center justify-between mb-4 gap-2 flex-wrap">
          <h2 className="text-xl font-semibold">{t("recentEvents")}</h2>
          <div className="flex items-center gap-3 flex-wrap">
            <label className="inline-flex items-center gap-2 text-sm text-gray-300 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={hideAcknowledged}
                onChange={(e) => setHideAcknowledged(e.target.checked)}
                className="h-4 w-4 rounded border-gray-600 bg-gray-800 accent-teal-500"
              />
              {t("hideAcknowledged")}
            </label>
            {/* التحميل عبر Route Handler (نفس النطاق يُرسل كوكي الـ session تلقائياً) */}
            <a
              href="/api/reports/export"
              className="h-9 inline-flex items-center rounded-md bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-700"
              download
            >
              {t("exportCsv")}
            </a>
          </div>
        </div>
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          {events.length === 0 ? (
            <p className="text-gray-400 p-4 text-center">{t("noEvents")}</p>
          ) : (
            <div className="divide-y divide-gray-700">
              {events.map((event, index) => {
                const meta = EVENT_META[event.event as EventType] ?? EVENT_META.intrusion;
                const key = `${event.timestamp}-${index}`;
                return (
                  <div
                    key={key}
                    className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-2 hover:bg-gray-700/50 transition"
                  >
                    <div className="flex items-center gap-3 flex-wrap">
                      <span className={`text-xs px-2 py-1 rounded ${meta.badge}`}>
                        {t(meta.key)}
                      </span>
                      <span className="text-sm text-gray-300">
                        {event.details?.camera_name
                          ? event.details.camera_name
                          : event.details?.camera_id
                            ? `${t("cameraUnknownName")} ${event.details.camera_id}`
                            : t("unknownCamera")}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 flex-wrap">
                      <span className="text-xs text-gray-500">
                        {formatEventTime(event.timestamp)}
                      </span>
                      {event.acknowledged ? (
                        <span
                          className="text-xs px-2 py-1 rounded bg-green-900/50 text-green-300 whitespace-nowrap"
                          title={event.ack_time}
                        >
                          {t("acknowledgedBy")} {event.ack_by ?? t("superuserBadge")}
                        </span>
                      ) : (
                        <button
                          type="button"
                          // التأكيد يتطلب JWT مشرف — يعرض للجميع والخطأ يظهر عند الضغط
                          title={
                            isSuperuser
                              ? undefined
                              : t("loginRequiredAck")
                          }
                          disabled={pendingEventId === event.id}
                          onClick={() => event.id && handleAcknowledge(event.id)}
                          className="text-xs px-3 py-1.5 rounded bg-teal-700/70 text-white hover:bg-teal-600 disabled:opacity-50 transition"
                        >
                          {pendingEventId === event.id
                            ? t("acknowledging")
                            : isSuperuser
                              ? t("acknowledgeButton")
                              : `🔐 ${t("acknowledgeButton")}`}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
        {ackError && (
          <p className="mt-2 rounded-md border border-red-800 bg-red-900/40 px-3 py-2 text-sm text-red-300">
            {ackError}
          </p>
        )}

        {/* حالة الكاميرات (الحقيقية من /api/cameras/health) */}
        <div className="mt-6">
          <h2 className="text-xl font-semibold mb-4">{t("cameraStatusSection")}</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {cameras.length === 0 ? (
              <p className="text-gray-400 text-sm col-span-full">
                {t("noCameras")}
              </p>
            ) : (
              cameras.map((camera) => (
                <div
                  key={camera.id}
                  className="bg-gray-800 p-4 rounded-lg border border-gray-700 text-center"
                  title={camera.url}
                >
                  <p className="text-sm text-gray-400">{camera.name}</p>
                  <span
                    className={`text-xs px-2 py-1 rounded inline-block mt-1 ${
                      camera.status === "online"
                        ? "bg-green-900/50 text-green-400"
                        : "bg-red-900/50 text-red-400"
                    }`}
                  >
                    {camera.status === "online"
                      ? t("cameraOnline")
                      : t("cameraOffline")}
                  </span>
                  <p className="text-xs text-gray-500 mt-2">
                    {t("lastSeen")}: {formatLastSeen(camera.last_seen)}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
