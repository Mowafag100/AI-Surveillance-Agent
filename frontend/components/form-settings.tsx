"use client";

// نموذج إعدادات النظام — جدول كاميرات ديناميكي (بدل حقل CAMERA_URL الفردي)
// + حقول: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ZONE_DWELL_TIME
// + مهلة انقطاع الكاميرا (CAMERA_TIMEOUT_SEC) + قسم البريد الإلكتروني SMTP
import { useActionState, useState } from "react";
import {
  AlarmClock,
  BrainCircuit,
  Cctv,
  LocateFixed,
  Mail,
  Plus,
  Save,
  Send,
  Trash2,
  type LucideIcon,
} from "lucide-react";

import { saveSettingsAction, type SettingsActionState } from "@/actions/settings";
import { useLanguage } from "@/components/language-context";

const initialState: SettingsActionState = {};

interface CameraRow {
  id: number;
  name: string;
  url: string;
}

const INPUT_CLASS =
  "w-full rounded-md border border-slate-700 bg-slate-800/80 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-teal-400 focus:outline-none focus:ring-1 focus:ring-teal-400/40 disabled:opacity-50";

/** حقل رقمي موحّد (إحداثيات المنطقة/التوقيت/زمن البقاء/المهلة) */
function ZoneField({
  fieldKey,
  label,
  defaultValue,
  step,
  min,
  max,
}: {
  fieldKey: string;
  label: string;
  defaultValue: number;
  step?: string;
  min?: number;
  max?: number;
}) {
  return (
    <div>
      <label
        htmlFor={fieldKey}
        className="mb-1.5 block text-xs font-medium text-slate-300"
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
        className={INPUT_CLASS}
      />
    </div>
  );
}

/** قسم إعدادات موحّد — رأس بأيقونة ابشر + جسم شبكة عمودين */
function SettingsSection({
  titleKey,
  icon: Icon,
  hintKey,
  children,
  cols = 2,
}: {
  titleKey: string;
  icon: LucideIcon;
  hintKey?: string;
  children: React.ReactNode;
  cols?: 1 | 2;
}) {
  const { t } = useLanguage();
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-lg shadow-black/20">
      <h3 className="mb-4 flex items-center gap-2.5 text-sm font-semibold text-slate-200">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-teal-500/10 text-teal-400">
          <Icon className="h-4 w-4" />
        </span>
        {t(titleKey)}
      </h3>
      {hintKey && (
        <p className="mb-4 text-xs leading-relaxed text-slate-500">
          {t(hintKey)}
        </p>
      )}
      <div
        className={
          cols === 2 ? "grid grid-cols-1 gap-4 md:grid-cols-2" : "space-y-4"
        }
      >
        {children}
      </div>
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
    trackCooldownSec: number;
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
      <SettingsSection titleKey="camerasSection" icon={Cctv}>
        {/* عدّاد الصفوف يحمل عدد الكاميرات النهائي عند الحفظ (بعد الحذف/الإضافة) */}
        <input type="hidden" name="CAMERAS_COUNT" value={cameras.length} />
        <div className="md:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <span className="block text-sm font-medium text-slate-300">
              {t("camerasLabel")}
            </span>
            <button
              type="button"
              onClick={addRow}
              disabled={isPending}
              className="inline-flex h-8 items-center gap-1 rounded-md bg-slate-800 px-3 text-xs text-slate-200 ring-1 ring-inset ring-slate-700 transition-colors hover:bg-slate-700 disabled:opacity-50"
            >
              <Plus className="h-3.5 w-3.5" />
              {t("addCamera")}
            </button>
          </div>

          <div className="overflow-hidden rounded-lg border border-slate-800">
            {/* رأس الجدول */}
            <div className="grid grid-cols-1 gap-3 bg-slate-950/80 px-4 py-2.5 text-xs text-slate-500 md:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)_auto]">
              <span>{t("cameraNameColumn")}</span>
              <span>{t("cameraUrlColumn")}</span>
              <span className="text-end">{t("deleteColumn")}</span>
            </div>

            {/* شرائط الكاميرات */}
            {cameras.length === 0 ? (
              <p className="px-4 py-4 text-xs text-slate-500">
                {t("noCamerasHint")}
              </p>
            ) : (
              <div className="divide-y divide-slate-800/60">
                {cameras.map((camera, index) => (
                  <div
                    key={camera.id}
                    className="grid grid-cols-1 items-center gap-3 px-4 py-3 transition-colors hover:bg-slate-800/50 md:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)_auto]"
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
                      className={INPUT_CLASS}
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
                      className={INPUT_CLASS}
                    />
                    <button
                      type="button"
                      onClick={() => removeRow(camera.id)}
                      disabled={isPending}
                      aria-label={`${t("deleteCameraAria")} ${camera.name || t("cameraUnknownName")}`}
                      className="inline-flex h-9 items-center gap-1.5 whitespace-nowrap rounded-md bg-red-500/10 px-3 text-sm text-red-400 transition-colors hover:bg-red-500/20 disabled:opacity-50"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      {t("deleteCamera")}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
          <p className="mt-1.5 text-xs text-slate-500">{t("emptyRowsHint")}</p>
          <div className="mt-3">
            <ZoneField
              fieldKey="CAMERA_TIMEOUT_SEC"
              label={t("cameraTimeoutLabel")}
              defaultValue={initial.cameraTimeoutSec}
              step="1"
              min={5}
            />
          </div>
        </div>
      </SettingsSection>

      {/* ===== المنطقة الحساسة ===== */}
      <SettingsSection titleKey="zoneSection" icon={LocateFixed} hintKey="zoneHint">
        <ZoneField fieldKey="ZONE_TOP_LEFT_X" label={t("zoneTopLeftX")} defaultValue={initial.zone.tlx} />
        <ZoneField fieldKey="ZONE_TOP_LEFT_Y" label={t("zoneTopLeftY")} defaultValue={initial.zone.tly} />
        <ZoneField fieldKey="ZONE_BOTTOM_RIGHT_X" label={t("zoneBottomRightX")} defaultValue={initial.zone.brx} />
        <ZoneField fieldKey="ZONE_BOTTOM_RIGHT_Y" label={t("zoneBottomRightY")} defaultValue={initial.zone.bry} />
        <div className="md:col-span-2">
          <ZoneField
            fieldKey="ZONE_DWELL_TIME"
            label={t("zoneDwellLabel")}
            defaultValue={initial.zoneDwellTime}
            step="0.5"
          />
        </div>
      </SettingsSection>

      {/* ===== أوقات التنبيه ===== */}
      <SettingsSection
        titleKey="scheduleSection"
        icon={AlarmClock}
        hintKey="scheduleHint"
      >
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
      </SettingsSection>

      {/* ===== الذكاء الاصطناعي ===== */}
      <SettingsSection titleKey="aiSection" icon={BrainCircuit} cols={1}>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <label
              htmlFor="MODEL_SIZE"
              className="mb-1.5 block text-xs font-medium text-slate-300"
            >
              {t("modelSizeLabel")}
            </label>
            <select
              id="MODEL_SIZE"
              name="MODEL_SIZE"
              defaultValue={initial.modelSize}
              disabled={isPending}
              className={INPUT_CLASS}
            >
              <option value="n">{t("modelN")}</option>
              <option value="s">{t("modelS")}</option>
              <option value="m">{t("modelM")}</option>
            </select>
            <p className="mt-1.5 text-xs text-slate-500">{t("modelHint")}</p>
          </div>
          <div>
            <ZoneField
              fieldKey="MIN_CONFIDENCE"
              label={t("minConfidenceLabel")}
              defaultValue={initial.minConfidence}
              step="0.05"
              min={0.1}
              max={0.9}
            />
            <p className="mt-1.5 text-xs text-slate-500">
              {t("minConfidenceHint")}
            </p>
          </div>
        </div>
        <ZoneField
          fieldKey="TRACK_COOLDOWN_SEC"
          label={t("trackCooldownLabel")}
          defaultValue={initial.trackCooldownSec}
          step="1"
          min={1}
        />
        <p className="-mt-2.5 text-xs text-slate-500">
          {t("trackCooldownHint")}
        </p>
      </SettingsSection>

      {/* ===== التلغرام ===== */}
      <SettingsSection titleKey="telegramSection" icon={Send}>
        <div>
          <label
            htmlFor="TELEGRAM_BOT_TOKEN"
            className="mb-1.5 block text-xs font-medium text-slate-300"
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
            className={INPUT_CLASS}
          />
        </div>
        <div>
          <label
            htmlFor="TELEGRAM_CHAT_ID"
            className="mb-1.5 block text-xs font-medium text-slate-300"
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
            className={INPUT_CLASS}
          />
        </div>
      </SettingsSection>

      {/* ===== البريد الإلكتروني ===== */}
      <SettingsSection titleKey="emailSection" icon={Mail}>
        <label className="flex cursor-pointer select-none items-center gap-3 text-sm font-medium text-slate-300 md:col-span-2">
          <input
            type="checkbox"
            name="ENABLE_EMAIL_ALERTS"
            checked={emailEnabled}
            onChange={(event) => setEmailEnabled(event.target.checked)}
            disabled={isPending}
            className="h-4 w-4 rounded border-slate-600 bg-slate-800 accent-teal-500"
          />
          {t("enableEmailAlerts")}
        </label>
        <div>
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
            className="mb-1.5 block text-xs font-medium text-slate-300"
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
            className={INPUT_CLASS}
          />
        </div>
        <div>
          <label
            htmlFor="SMTP_USER"
            className="mb-1.5 block text-xs font-medium text-slate-300"
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
            className={INPUT_CLASS}
          />
        </div>
        <div>
          <label
            htmlFor="SMTP_PASSWORD"
            className="mb-1.5 block text-xs font-medium text-slate-300"
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
              initial.email.passwordSet ? t("keepCurrentPlaceholder") : ""
            }
            disabled={isPending}
            className={INPUT_CLASS}
          />
        </div>
        <div>
          <label
            htmlFor="ALERT_EMAIL_TO"
            className="mb-1.5 block text-xs font-medium text-slate-300"
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
            className={INPUT_CLASS}
          />
        </div>
        <p className="text-xs text-slate-500 md:col-span-2">{t("smtpHint")}</p>
      </SettingsSection>

      {state.ok && (
        <p className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">
          {t("saveSuccess")}
        </p>
      )}

      {state.error && (
        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {state.error}
        </p>
      )}

      {/* زر الحفظ الأساسي — Teal-600 بارز مع أيقونة */}
      <button
        type="submit"
        disabled={isPending}
        className="inline-flex h-11 items-center gap-2 rounded-lg bg-teal-600 px-8 font-semibold text-white shadow-lg shadow-teal-950/40 transition-colors hover:bg-teal-500 disabled:opacity-50"
      >
        <Save className="h-4 w-4" />
        {isPending ? t("saving") : t("save")}
      </button>
    </form>
  );
}
