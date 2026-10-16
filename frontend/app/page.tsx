"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8090";

type EventType = "fall" | "fight" | "intrusion";

interface CameraDetails {
  camera_id?: string | number;
}

interface SurveillanceEvent {
  event: string;
  timestamp: string;
  details?: CameraDetails;
}

interface DailyStats {
  total?: number;
  fall?: number;
  fight?: number;
  intrusion?: number;
}

const EVENT_META: Record<EventType, { label: string; badge: string }> = {
  fall: { label: "🚨 سقوط", badge: "bg-red-900/50 text-red-300" },
  fight: { label: "⚔️ شجار", badge: "bg-yellow-900/50 text-yellow-300" },
  intrusion: { label: "🚶 تسلل", badge: "bg-blue-900/50 text-blue-300" },
};

function getEventMeta(eventType: string) {
  return EVENT_META[eventType as EventType] ?? EVENT_META.intrusion;
}

async function fetchEvents(signal: AbortSignal): Promise<SurveillanceEvent[]> {
  const res = await fetch(`${API_BASE}/api/events`, { signal });
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

export default function Dashboard() {
  const [events, setEvents] = useState<SurveillanceEvent[]>([]);
  const [stats, setStats] = useState<DailyStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    (async () => {
      const [eventsResult, statsResult] = await Promise.allSettled([
        fetchEvents(controller.signal),
        fetchDailyStats(controller.signal),
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

      setLoading(false);
    })();

    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center">
        <p className="text-xl">⏳ جاري التحميل...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-3xl font-bold mb-6">📊 لوحة تحكم المراقبة</h1>

        {/* الإحصائيات */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
              <p className="text-gray-400 text-sm">الإجمالي اليومي</p>
              <p className="text-2xl font-bold">{stats.total || 0}</p>
            </div>
            <div className="bg-red-900/30 p-4 rounded-lg border border-red-800">
              <p className="text-gray-400 text-sm">🚨 سقوط</p>
              <p className="text-2xl font-bold text-red-400">{stats.fall || 0}</p>
            </div>
            <div className="bg-yellow-900/30 p-4 rounded-lg border border-yellow-800">
              <p className="text-gray-400 text-sm">⚔️ شجار</p>
              <p className="text-2xl font-bold text-yellow-400">{stats.fight || 0}</p>
            </div>
            <div className="bg-blue-900/30 p-4 rounded-lg border border-blue-800">
              <p className="text-gray-400 text-sm">🚶 تسلل</p>
              <p className="text-2xl font-bold text-blue-400">{stats.intrusion || 0}</p>
            </div>
          </div>
        )}

        {/* قائمة الأحداث */}
        <h2 className="text-xl font-semibold mb-4">📋 آخر الأحداث</h2>
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          {events.length === 0 ? (
            <p className="text-gray-400 p-4 text-center">لا توجد أحداث بعد</p>
          ) : (
            <div className="divide-y divide-gray-700">
              {events.map((event, index) => {
                const meta = getEventMeta(event.event);
                return (
                  <div
                    key={`${event.timestamp}-${index}`}
                    className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-2 hover:bg-gray-700/50 transition"
                  >
                    <div className="flex items-center gap-3">
                      <span className={`text-xs px-2 py-1 rounded ${meta.badge}`}>
                        {meta.label}
                      </span>
                      <span className="text-sm text-gray-300">
                        {event.details?.camera_id
                          ? `كاميرا ${event.details.camera_id}`
                          : "كاميرا غير معروفة"}
                      </span>
                    </div>
                    <span className="text-xs text-gray-500">
                      {new Date(event.timestamp).toLocaleString("ar-SA")}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* حالة الكاميرات (سريعة) */}
        <div className="mt-6">
          <h2 className="text-xl font-semibold mb-4">📹 حالة الكاميرات</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((id) => (
              <div
                key={id}
                className="bg-gray-800 p-4 rounded-lg border border-gray-700 text-center"
              >
                <p className="text-sm text-gray-400">كاميرا {id}</p>
                <span className="text-xs px-2 py-1 rounded bg-green-900/50 text-green-400 inline-block mt-1">
                  🟢 متصلة
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
