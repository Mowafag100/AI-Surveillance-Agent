"use client";

// نموذج إعدادات النظام — جدول كاميرات ديناميكي (بدل حقل CAMERA_URL الفردي)
// + حقول: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ZONE_DWELL_TIME
// + مهلة انقطاع الكاميرا (CAMERA_TIMEOUT_SEC) + قسم البريد الإلكتروني SMTP
import { useActionState, useState } from "react";

import { saveSettingsAction, type SettingsActionState } from "@/actions/settings";
import { useLanguage } from "@/components/language-context";

const initialState: SettingsActionState = {};

interface CameraRow {
  id: number;
  name: string;
  url: string;
}

/** حقل رقمي موحّد (إحداثيات المنطقة/التوقيت/زمن البقاء/المهلة) */
function ZoneField({
  fieldKey,
  label,
  defaultValue,
  step,
  min,
  max,
  wide,
}: {
  fieldKey: string;
  label: string;
  defaultValue: number;
  step?: string;
  min?: number;
  max?: number;
  wide?: boolean;
}) {
  return (
    <div className={wide ? "col-span-2" : undefined}>
      <label
        htmlFor={fieldKey}
        className="block text-xs font-medium text-gray-300 mb-1"
      >
        {label}
      </label>
      <input
        id={fieldKey}
        name={fieldKey}
        type="number"
        step={step}
        min={min}
        max={max}
        autoComplete="off"
        defaultValue={defaultValue}
        dir="ltr"
        className={`rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-white focus:border-teal-500 focus:outline-none ${
          wide ? "w-full" : "w-full"
        }`}
      />
    </div>
  );
}

interface FormSettingsProps {
  /** القيم الحقيقية المقروءة من GET /api/settings (التوكنات السرية تُستثنى مقنّعة) */
  initial: {
    cameras: CameraRow[];
    telegramChatId: string;
    zoneDwellTime: number;
    cameraTimeoutSec: number;
    zone: { tlx: number; tly: number; brx: number; bry: number };
    alerts: { startHour: number; endHour: number };
    modelSize: string;
    minConfidence: number;
    email: {
      enabled: boolean;
      host: string;
      port: number;
      user: string;
      passwordSet: boolean;
      emailTo: string;
    };
  };
}

export default function FormSettings({ initial }: FormSettingsProps) {
  const { t } = useLanguage();
  const [state, formAction, isPending] = useActionState(
    saveSettingsAction,
    initialState
  );
  // صفوف الكاميرات — الحفظ يرسل المصفوفة كاملة؛ فراغ = صف تحرير واحد للمساعدة
  // (يمكن حذفه بالزر، والحفظ بلا صفوف يترك النظام بـ CAMERA_URL القديم)
  const [cameras, setCameras] = useState<CameraRow[]>(
    initial.cameras.length > 0 ? initial.cameras : [{ id: 1, name: "", url: "" }]
  );
  // تفعيل تنبيهات البريد (checkbox مُدار — يرسل قيمته مع الحفظ دائماً)
  const [emailEnabled, setEmailEnabled] = useState(initial.email.enabled);

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
      {/* ===== الكاميرات ===== */}
      <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3">
        <h3 className="text-sm font-semibold text-teal-300">{t("camerasSection")}</h3>
        {/* عدّاد الصفوف يحمل عدد الكاميرات النهائي عند الحفظ (بعد الحذف/الإضافة) */}
        <input type="hidden" name="CAMERAS_COUNT" value={cameras.length} />

      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="block text-sm font-medium text-gray-300">
            {t("camerasLabel")}
          </span>
          <button
            type="button"
            onClick={addRow}
            disabled={isPending}
            className="h-8 rounded-md bg-gray-700 px-3 text-xs text-white hover:bg-gray-600 disabled:opacity-50"
          >
            {t("addCamera")}
          </button>
        </div>

        <div className="rounded-lg border border-gray-700 overflow-hidden">
          {/* رأس الجدول */}
          <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)_auto] gap-3 bg-gray-900/80 px-4 py-2 text-xs text-gray-400">
            <span>{t("cameraNameColumn")}</span>
            <span>{t("cameraUrlColumn")}</span>
            <span className="text-right">{t("deleteColumn")}</span>
          </div>

          {/* شرائط الكاميرات */}
          {cameras.length === 0 ? (
            <p className="px-4 py-4 text-xs text-gray-500">
              {t("noCamerasHint")}
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
                    aria-label={`${t("deleteCameraAria")} ${camera.name || t("cameraUnknownName")}`}
                    className="h-9 rounded-md bg-red-900/50 px-3 text-sm text-red-300 hover:bg-red-900/80 disabled:opacity-50 whitespace-nowrap"
                  >
                    ✕ {t("deleteCamera")}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
        <p className="mt-1 text-xs text-gray-500">
          {t("emptyRowsHint")}
        </p>
      </div>

        <ZoneField
          fieldKey="CAMERA_TIMEOUT_SEC"
          label={t("cameraTimeoutLabel")}
          defaultValue={initial.cameraTimeoutSec}
          step="1"
          min={5}
          wide
        />
      </div>

      {/* ===== المنطقة الحساسة ===== */}
      <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3">
        <h3 className="text-sm font-semibold text-teal-300">{t("zoneSection")}</h3>
        <p className="text-xs text-gray-500">
          {t("zoneHint")}
        </p>
        <div className="grid grid-cols-2 gap-3">
          <ZoneField fieldKey="ZONE_TOP_LEFT_X" label={t("zoneTopLeftX")} defaultValue={initial.zone.tlx} />
          <ZoneField fieldKey="ZONE_TOP_LEFT_Y" label={t("zoneTopLeftY")} defaultValue={initial.zone.tly} />
          <ZoneField fieldKey="ZONE_BOTTOM_RIGHT_X" label={t("zoneBottomRightX")} defaultValue={initial.zone.brx} />
          <ZoneField fieldKey="ZONE_BOTTOM_RIGHT_Y" label={t("zoneBottomRightY")} defaultValue={initial.zone.bry} />
        </div>
        <ZoneField
          fieldKey="ZONE_DWELL_TIME"
          label={t("zoneDwellLabel")}
          defaultValue={initial.zoneDwellTime}
          step="0.5"
          wide
        />
      </div>

      {/* ===== أوقات التنبيه ===== */}
      <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3">
        <h3 className="text-sm font-semibold text-teal-300">{t("scheduleSection")}</h3>
        <p className="text-xs text-gray-500">
          {t("scheduleHint")}
        </p>
        <div className="grid grid-cols-2 gap-3">
          <ZoneField
            fieldKey="ALERT_START_HOUR"
            label={t("startHourLabel")}
            defaultValue={initial.alerts.startHour}
            min={0}
            max={23}
          />
          <ZoneField
            fieldKey="ALERT_END_HOUR"
            label={t("endHourLabel")}
            defaultValue={initial.alerts.endHour}
            min={0}
            max={23}
          />
        </div>
      </div>

      {/* ===== الذكاء الاصطناعي ===== */}
      <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3">
        <h3 className="text-sm font-semibold text-teal-300">{t("aiSection")}</h3>
        <label
          htmlFor="MODEL_SIZE"
          className="block text-sm font-medium text-gray-300 mb-1"
        >
          {t("modelSizeLabel")}
        </label>
        <select
          id="MODEL_SIZE"
          name="MODEL_SIZE"
          defaultValue={initial.modelSize}
          disabled={isPending}
          className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-white focus:border-teal-500 focus:outline-none"
        >
          <option value="n">{t("modelN")}</option>
          <option value="s">{t("modelS")}</option>
          <option value="m">{t("modelM")}</option>
        </select>
        <p className="mt-1 text-xs text-gray-500">
          {t("modelHint")}
        </p>
        <ZoneField
          fieldKey="MIN_CONFIDENCE"
          label={t("minConfidenceLabel")}
          defaultValue={initial.minConfidence}
          step="0.05"
          min={0.1}
          max={0.9}
        />
        <p className="mt-1 text-xs text-gray-500">
          {t("minConfidenceHint")}
        </p>
      </div>

      {/* ===== التلغرام ===== */}
      <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3">
        <h3 className="text-sm font-semibold text-teal-300">{t("telegramSection")}</h3>
        <div>
          <label
            htmlFor="TELEGRAM_BOT_TOKEN"
            className="block text-sm font-medium text-gray-300 mb-1"
          >
            {t("botTokenLabel")}
          </label>
          <input
            id="TELEGRAM_BOT_TOKEN"
            name="TELEGRAM_BOT_TOKEN"
            type="password"
            // new-password يوقف تخمين Chrome بأن هذا "نموذج تسجيل دخول" —
            // ما كان يعبّئ اسم المستخدم المحفوظ في الحقول النصية المجاورة
            autoComplete="new-password"
            placeholder={t("keepCurrentPlaceholder")}
            disabled={isPending}
            className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-white placeholder:text-gray-500 focus:border-teal-500 focus:outline-none"
          />
        </div>
        <div>
          <label
            htmlFor="TELEGRAM_CHAT_ID"
            className="block text-sm font-medium text-gray-300 mb-1"
          >
            {t("chatIdLabel")}
          </label>
          <input
            id="TELEGRAM_CHAT_ID"
            name="TELEGRAM_CHAT_ID"
            type="text"
            autoComplete="off"
            // القيمة الحقيقية من الـ API (غير سرية — تُعرض كما هي)
            defaultValue={initial.telegramChatId}
            placeholder={initial.telegramChatId ? "" : t("keepCurrentPlaceholder")}
            disabled={isPending}
            className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-white placeholder:text-gray-500 focus:border-teal-500 focus:outline-none"
          />
        </div>
      </div>

      {/* ===== البريد الإلكتروني ===== */}
      <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3">
        <h3 className="text-sm font-semibold text-teal-300">{t("emailSection")}</h3>
        <label className="flex items-center gap-3 text-sm font-medium text-gray-300 cursor-pointer select-none">
          <input
            type="checkbox"
            name="ENABLE_EMAIL_ALERTS"
            checked={emailEnabled}
            onChange={(event) => setEmailEnabled(event.target.checked)}
            disabled={isPending}
            className="h-4 w-4 rounded border-gray-600 bg-gray-800 accent-teal-500"
          />
          {t("enableEmailAlerts")}
        </label>
        <div className="grid grid-cols-2 gap-3">
          <ZoneField
            fieldKey="SMTP_PORT"
            label={t("smtpPortLabel")}
            defaultValue={initial.email.port}
            step="1"
            min={1}
            max={65535}
          />
        </div>
        <div>
          <label
            htmlFor="SMTP_HOST"
            className="block text-sm font-medium text-gray-300 mb-1"
          >
            {t("smtpHostLabel")}
          </label>
          <input
            id="SMTP_HOST"
            name="SMTP_HOST"
            type="text"
            autoComplete="off"
            defaultValue={initial.email.host}
            placeholder="smtp.gmail.com"
            dir="ltr"
            disabled={isPending}
            className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-white placeholder:text-gray-500 focus:border-teal-500 focus:outline-none"
          />
        </div>
        <div>
          <label
            htmlFor="SMTP_USER"
            className="block text-sm font-medium text-gray-300 mb-1"
          >
            {t("smtpUserLabel")}
          </label>
          <input
            id="SMTP_USER"
            name="SMTP_USER"
            type="text"
            autoComplete="off"
            defaultValue={initial.email.user}
            placeholder="alerts@example.com"
            dir="ltr"
            disabled={isPending}
            className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-white placeholder:text-gray-500 focus:border-teal-500 focus:outline-none"
          />
        </div>
        <div>
          <label
            htmlFor="SMTP_PASSWORD"
            className="block text-sm font-medium text-gray-300 mb-1"
          >
            {t("smtpPasswordLabel")}
          </label>
          <input
            id="SMTP_PASSWORD"
            name="SMTP_PASSWORD"
            type="password"
            autoComplete="new-password"
            // القيمة الحقيقية مقنّعة من الباكند — رسلها فقط عند كتابة قيمة جديدة
            placeholder={
              initial.email.passwordSet
                ? t("keepCurrentPlaceholder")
                : ""
            }
            disabled={isPending}
            className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-white placeholder:text-gray-500 focus:border-teal-500 focus:outline-none"
          />
        </div>
        <div>
          <label
            htmlFor="ALERT_EMAIL_TO"
            className="block text-sm font-medium text-gray-300 mb-1"
          >
            {t("alertEmailToLabel")}
          </label>
          <input
            id="ALERT_EMAIL_TO"
            name="ALERT_EMAIL_TO"
            type="email"
            autoComplete="off"
            defaultValue={initial.email.emailTo}
            placeholder="security@example.com"
            dir="ltr"
            disabled={isPending}
            className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-white placeholder:text-gray-500 focus:border-teal-500 focus:outline-none"
          />
        </div>
        <p className="mt-1 text-xs text-gray-500">
          {t("smtpHint")}
        </p>
      </div>

      {state.ok && (
        <p className="rounded-md border border-green-800 bg-green-900/40 px-3 py-2 text-sm text-green-300">
          {t("saveSuccess")}
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
        {isPending ? t("saving") : t("save")}
      </button>
    </form>
  );
}
