"use client";

// نموذج إعدادات النظام — جدول كاميرات ديناميكي (بدل حقل CAMERA_URL الفردي)
// + حقول: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ZONE_DWELL_TIME + زر حفظ
import { useActionState, useState } from "react";

import { saveSettingsAction, type SettingsActionState } from "@/actions/settings";

const initialState: SettingsActionState = {};

interface CameraRow {
  id: number;
  name: string;
  url: string;
}

interface FormSettingsProps {
  /** القيم الحقيقية المقروءة من GET /api/settings (توكن بوت التلغرام يستثنى مقنّعاً) */
  initial: {
    cameras: CameraRow[];
    telegramChatId: string;
    zoneDwellTime: number;
  };
}

export default function FormSettings({ initial }: FormSettingsProps) {
  const [state, formAction, isPending] = useActionState(
    saveSettingsAction,
    initialState
  );
  // صفوف الكاميرات — الحفظ يرسل المصفوفة كاملة؛ فراغ = صف تحرير واحد للمساعدة
  // (يمكن حذفه بالزر، والحفظ بلا صفوف يترك النظام بـ CAMERA_URL القديم)
  const [cameras, setCameras] = useState<CameraRow[]>(
    initial.cameras.length > 0 ? initial.cameras : [{ id: 1, name: "", url: "" }]
  );

  const updateRow = (camId: number, patch: Partial<CameraRow>) => {
    setCameras((rows) =>
      rows.map((row) => (row.id === camId ? { ...row, ...patch } : row))
    );
  };
  const addRow = () => {
    setCameras((rows) => [
      ...rows,
      { id: Math.max(0, ...rows.map((r) => r.id)) + 1, name: "", url: "" },
    ]);
  };
  const removeRow = (camId: number) => {
    setCameras((rows) => rows.filter((row) => row.id !== camId));
  };

  return (
    // autoComplete="off" على النموذج كلياً: التعبئ في حقل TELEGRAM_CHAT_ID كان
    // ناتجاً من تخمين Chrome لنموذج الدخول (بوجود type=password)+ بيانات مصادفة
    <form action={formAction} autoComplete="off" className="space-y-5">
      {/* عدّاد الصفوف يحمل عدد الكاميرات النهائي عند الحفظ (بعد الحذف/الإضافة) */}
      <input type="hidden" name="CAMERAS_COUNT" value={cameras.length} />

      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="block text-sm font-medium text-gray-300">
            الكاميرات (CAMERAS)
          </span>
          <button
            type="button"
            onClick={addRow}
            disabled={isPending}
            className="h-8 rounded-md bg-gray-700 px-3 text-xs text-white hover:bg-gray-600 disabled:opacity-50"
          >
            + إضافة كاميرا
          </button>
        </div>

        <div className="rounded-lg border border-gray-700 overflow-hidden">
          {/* رأس الجدول */}
          <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)_auto] gap-3 bg-gray-900/80 px-4 py-2 text-xs text-gray-400">
            <span>اسم الكاميرا</span>
            <span>رابط الكاميرا</span>
            <span className="text-right">حذف</span>
          </div>

          {/* شرائط الكاميرات */}
          {cameras.length === 0 ? (
            <p className="px-4 py-4 text-xs text-gray-500">
              لا توجد كاميرات — النظام سيعمل بـ CAMERA_URL القديم (توافق خلفي)
            </p>
          ) : (
            <div className="divide-y divide-gray-700/60">
              {cameras.map((camera, index) => (
                <div
                  key={camera.id}
                  className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)_auto] gap-3 px-4 py-3 items-center"
                  dir="ltr"
                >
                  <input
                    name={`CAMERAS_${index}_NAME`}
                    type="text"
                    defaultValue={camera.name}
                    onChange={(event) =>
                      updateRow(camera.id, { name: event.target.value })
                    }
                    disabled={isPending}
                    autoComplete="off"
                    className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white text-right focus:border-teal-500 focus:outline-none"
                  />
                  <input
                    name={`CAMERAS_${index}_URL`}
                    type="text"
                    defaultValue={camera.url}
                    onChange={(event) =>
                      updateRow(camera.id, { url: event.target.value })
                    }
                    disabled={isPending}
                    autoComplete="off"
                    placeholder="http://CAMERA_IP:PORT/video"
                    className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:border-teal-500 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => removeRow(camera.id)}
                    disabled={isPending}
                    aria-label={`حذف ${camera.name || "الكاميرا"}`}
                    className="h-9 rounded-md bg-red-900/50 px-3 text-sm text-red-300 hover:bg-red-900/80 disabled:opacity-50 whitespace-nowrap"
                  >
                    ✕ حذف
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
        <p className="mt-1 text-xs text-gray-500">
          الفارغة كلياً تتجاهل — تغيير الروابط يعيد اتصال الكاميرات حياً
          (Hot Reload) دون إعادة تشغيل.
        </p>
      </div>

      <div>
        <label
          htmlFor="TELEGRAM_BOT_TOKEN"
          className="block text-sm font-medium text-gray-300 mb-1"
        >
          توكن بوت التلغرام (TELEGRAM_BOT_TOKEN)
        </label>
        <input
          id="TELEGRAM_BOT_TOKEN"
          name="TELEGRAM_BOT_TOKEN"
          type="password"
          // new-password يوقف تخمين Chrome بأن هذا "نموذج تسجيل دخول" —
          // ما كان يعبّئ اسم المستخدم المحفوظ في الحقول النصية المجاورة
          autoComplete="new-password"
          placeholder="اتركه فارغاً للإبقاء على القيمة الحالية"
          disabled={isPending}
          className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-white placeholder:text-gray-500 focus:border-teal-500 focus:outline-none"
        />
      </div>

      <div>
        <label
          htmlFor="TELEGRAM_CHAT_ID"
          className="block text-sm font-medium text-gray-300 mb-1"
        >
          معرّف محادثة التلغرام (TELEGRAM_CHAT_ID)
        </label>
        <input
          id="TELEGRAM_CHAT_ID"
          name="TELEGRAM_CHAT_ID"
          type="text"
          autoComplete="off"
          // القيمة الحقيقية من الـ API (غير سرية — تُعرض كما هي)
          defaultValue={initial.telegramChatId}
          placeholder={initial.telegramChatId ? "" : "اتركه فارغاً للإبقاء على القيمة الحالية"}
          disabled={isPending}
          className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-white placeholder:text-gray-500 focus:border-teal-500 focus:outline-none"
        />
      </div>

      <div>
        <label
          htmlFor="ZONE_DWELL_TIME"
          className="block text-sm font-medium text-gray-300 mb-1"
        >
          زمن البقاء في المنطقة الحساسة بالثواني (ZONE_DWELL_TIME)
        </label>
        <input
          id="ZONE_DWELL_TIME"
          name="ZONE_DWELL_TIME"
          type="number"
          step="0.5"
          min="0"
          autoComplete="off"
          defaultValue={initial.zoneDwellTime}
          disabled={isPending}
          className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-white focus:border-teal-500 focus:outline-none"
        />
      </div>

      {state.ok && (
        <p className="rounded-md border border-green-800 bg-green-900/40 px-3 py-2 text-sm text-green-300">
          ✓ تم الحفظ بنجاح — سيطبّق الوكيل الإعدادات خلال بضع ثوانٍ (Hot Reload).
        </p>
      )}

      {state.error && (
        <p className="rounded-md border border-red-800 bg-red-900/40 px-3 py-2 text-sm text-red-300">
          {state.error}
        </p>
      )}

      <button
        type="submit"
        disabled={isPending}
        className="h-11 rounded-md bg-teal-600 px-6 font-medium text-white hover:bg-teal-700 disabled:opacity-50"
      >
        {isPending ? "جارٍ الحفظ..." : "حفظ"}
      </button>
    </form>
  );
}
