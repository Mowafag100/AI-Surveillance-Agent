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
  Palette,
  Plus,
  Save,
  Send,
  Swords,
  Target,
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
  /** الإعدادات المنفردة للكاميرا (Per-Camera Settings) إن وُجدت */
  settings?: Record<string, unknown>;
}

/** قيم النطاق: "all" = عام، رقم = معرّف كاميرا (إعدادات منفردة) */
type ApplyTo = "all" | number;

/** القيم المنفردة المخزنة لكل كاميرا — القيم الخام كما أدخلها المستخدم */
type CameraOverrides = Record<number, Record<string, string | number | boolean>>;

const INPUT_CLASS =
  "w-full rounded-md border border-slate-700 bg-slate-800/80 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-teal-400 focus:outline-none focus:ring-1 focus:ring-teal-400/40 disabled:opacity-50";

/** حقل رقمي موحّد (إحداثيات المنطقة/التوقيت/زمن البقاء/المهلة) —
 * name اختياري (CAM_<id>_<KEY> عند الحفظ المنفرد) وonChange اختياري
 * لالتقاط القيمة في overrides الكاميرا المختارة */
function ZoneField({
  fieldKey,
  name,
  label,
  defaultValue,
  step,
  min,
  max,
  onChange,
}: {
  fieldKey: string;
  name?: string;
  label: string;
  defaultValue: string | number;
  step?: string;
  min?: number;
  max?: number;
  onChange?: (event: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  return (
    <div>
      <label
        htmlFor={name ?? fieldKey}
        className="mb-1.5 block text-xs font-medium text-slate-300"
      >
        {label}
      </label>
      <input
        id={name ?? fieldKey}
        name={name ?? fieldKey}
        type="number"
        step={step}
        min={min}
        max={max}
        autoComplete="off"
        defaultValue={defaultValue}
        dir="ltr"
        onChange={onChange}
        className={INPUT_CLASS}
      />
    </div>
  );
}

/** قسم إعدادات موحّد — رأس بأيقونة ابشر + جسم شبكة عمودين (note اختياري
 * يظهر أعلى الجسم: ملاحظة نطاق الكاميرا المختارة) */
function SettingsSection({
  titleKey,
  icon: Icon,
  hintKey,
  note,
  children,
  cols = 2,
}: {
  titleKey: string;
  icon: LucideIcon;
  hintKey?: string;
  note?: React.ReactNode;
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
      {note}
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
    fight: {
      enabled: boolean;
      iouThreshold: number;
      motionThreshold: number;
      minFrames: number;
      convergenceThreshold: number;
      minPersons: number;
      convergenceRadius: number;
    };
    color: {
      enabled: boolean;
      forbiddenColorHex: string;
      tolerance: number;
      minPercentage: number;
    };
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
  // تفعيل كشف المشاجرات (checkbox مُدار — يرسل قيمته مع الحفظ دائماً)
  const [fightEnabled, setFightEnabled] = useState(initial.fight.enabled);
  // تفعيل كشف اللون الممنوع (checkbox مُدار — يرسل قيمته مع الحفظ دائماً)
  const [colorEnabled, setColorEnabled] = useState(initial.color.enabled);

  // ===== نطاق التطبيق (Per-Camera Settings) =====
  // "all" = الأقسام المخصصة تكتب الإعدادات العامة؛ رقم = تُكتب داخل
  // كائن settings الخاص بالكاميرا في config.json (مع الرجوع للعام لما لم يُخصص)
  const [applyTo, setApplyTo] = useState<ApplyTo>("all");
  // الإعدادات المنفردة لكل كاميرا (المخزنة + الجديدة أثناء التحرير) —
  // تُرسل مع الحفظ دائماً في CAMERAS_i_SETTINGS حتي تُحفظ لكل الكاميرات
  const [camOverrides, setCamOverrides] = useState<CameraOverrides>(() => {
    const overrides: CameraOverrides = {};
    for (const camera of initial.cameras) {
      if (camera.settings && typeof camera.settings === "object") {
        overrides[camera.id] = {
          ...(camera.settings as Record<string, string | number | boolean>),
        };
      }
    }
    return overrides;
  });

  const cameraName = (cameraId: number) =>
    initial.cameras.find((camera) => camera.id === cameraId)?.name ||
    `${t("cameraUnknownName")} ${cameraId}`;
  const targetLabel =
    applyTo === "all" ? t("applyToTargetAll") : cameraName(applyTo);

  /** اسم الحقل: العام KEY أو CAM_<id>_<KEY> عند تخصيص كاميرا */
  const fieldName = (key: string) =>
    applyTo === "all" ? key : `CAM_${applyTo}_${key}`;

  /** القيمة الفعلية المعروضة: override الكاميرا أو تراجع للقيمة العامة */
  const effectiveDefault = (key: string, globalValue: string | number) => {
    if (applyTo === "all") return globalValue;
    const override = camOverrides[applyTo]?.[key];
    return (override ?? globalValue) as string | number;
  };
  const effectiveBool = (key: string, globalValue: boolean) => {
    if (applyTo === "all") return globalValue;
    const override = camOverrides[applyTo]?.[key];
    return override === undefined ? globalValue : Boolean(override);
  };

  /** كتابة قيمة منفردة للكاميرا المختارة (الخام — التحقق عند الحفظ) */
  const setCameraOverride = (key: string, value: string | number | boolean) => {
    if (applyTo === "all") return;
    const cameraId = applyTo;
    setCamOverrides((prev) => ({
      ...prev,
      [cameraId]: { ...(prev[cameraId] ?? {}), [key]: value },
    }));
  };

  /** ملاحظة النطاق داخل الأقسام القابلة للتخصيص لكل كاميرا */
  const scopeNote =
    applyTo === "all" ? undefined : (
      <p className="mb-4 rounded-md border border-teal-500/30 bg-teal-500/10 px-3 py-2 text-xs leading-relaxed text-teal-300 md:col-span-2">
        {t("perCameraScopeNote").replace(
          "{target}",
          `${t("applyToCameraPrefix")} ${targetLabel}`
        )}
      </p>
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
                    {/* معرّف الكاميرا + إعداداتها المنفردة (JSON) — يرسلان مع الحفظ
                        دائماً لكل صف لكي يبقى تخصيص كل كاميرا محفوظاً */}
                    <input type="hidden" name={`CAMERAS_${index}_ID`} value={camera.id} />
                    <input
                      type="hidden"
                      name={`CAMERAS_${index}_SETTINGS`}
                      value={JSON.stringify(camOverrides[camera.id] ?? {})}
                    />
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

      {/* ===== نطاق تطبيق الإعدادات (Per-Camera Settings) ===== */}
      <SettingsSection titleKey="applyToSection" icon={Target} hintKey="applyToHint" cols={1}>
        <div>
          <label
            htmlFor="APPLY_TO"
            className="mb-1.5 block text-xs font-medium text-slate-300"
          >
            {t("applyToLabel")}
          </label>
          <select
            id="APPLY_TO"
            name="APPLY_TO"
            value={applyTo === "all" ? "all" : String(applyTo)}
            onChange={(event) =>
              setApplyTo(
                event.target.value === "all"
                  ? "all"
                  : Number(event.target.value)
              )
            }
            disabled={isPending || initial.cameras.length === 0}
            className={INPUT_CLASS}
          >
            <option value="all">{t("applyToAllCameras")}</option>
            {initial.cameras.map((camera) => (
              <option key={camera.id} value={String(camera.id)}>
                {`${t("applyToCameraPrefix")} ${camera.name || `${t("cameraUnknownName")} ${camera.id}`}`}
              </option>
            ))}
          </select>
        </div>
      </SettingsSection>

      {/* ===== المنطقة الحساسة (قابلة للتخصيص لكل كاميرا) ===== */}
      <SettingsSection
        key={applyTo === "all" ? "all" : `cam-${applyTo}`}
        titleKey="zoneSection"
        icon={LocateFixed}
        hintKey="zoneHint"
        note={scopeNote}
      >
        <ZoneField
          fieldKey="ZONE_TOP_LEFT_X"
          name={fieldName("ZONE_TOP_LEFT_X")}
          label={t("zoneTopLeftX")}
          defaultValue={effectiveDefault("ZONE_TOP_LEFT_X", initial.zone.tlx)}
          onChange={(event) => setCameraOverride("ZONE_TOP_LEFT_X", event.target.value)}
        />
        <ZoneField
          fieldKey="ZONE_TOP_LEFT_Y"
          name={fieldName("ZONE_TOP_LEFT_Y")}
          label={t("zoneTopLeftY")}
          defaultValue={effectiveDefault("ZONE_TOP_LEFT_Y", initial.zone.tly)}
          onChange={(event) => setCameraOverride("ZONE_TOP_LEFT_Y", event.target.value)}
        />
        <ZoneField
          fieldKey="ZONE_BOTTOM_RIGHT_X"
          name={fieldName("ZONE_BOTTOM_RIGHT_X")}
          label={t("zoneBottomRightX")}
          defaultValue={effectiveDefault("ZONE_BOTTOM_RIGHT_X", initial.zone.brx)}
          onChange={(event) => setCameraOverride("ZONE_BOTTOM_RIGHT_X", event.target.value)}
        />
        <ZoneField
          fieldKey="ZONE_BOTTOM_RIGHT_Y"
          name={fieldName("ZONE_BOTTOM_RIGHT_Y")}
          label={t("zoneBottomRightY")}
          defaultValue={effectiveDefault("ZONE_BOTTOM_RIGHT_Y", initial.zone.bry)}
          onChange={(event) => setCameraOverride("ZONE_BOTTOM_RIGHT_Y", event.target.value)}
        />
        <div className="md:col-span-2">
          <ZoneField
            fieldKey="ZONE_DWELL_TIME"
            name={fieldName("ZONE_DWELL_TIME")}
            label={t("zoneDwellLabel")}
            defaultValue={effectiveDefault("ZONE_DWELL_TIME", initial.zoneDwellTime)}
            step="0.5"
            onChange={(event) => setCameraOverride("ZONE_DWELL_TIME", event.target.value)}
          />
        </div>
      </SettingsSection>

      {/* ===== أوقات التنبيه (قابلة للتخصيص لكل كاميرا) ===== */}
      <SettingsSection
        key={applyTo === "all" ? "schedule-all" : `schedule-${applyTo}`}
        titleKey="scheduleSection"
        icon={AlarmClock}
        hintKey="scheduleHint"
        note={scopeNote}
      >
        <ZoneField
          fieldKey="ALERT_START_HOUR"
          name={fieldName("ALERT_START_HOUR")}
          label={t("startHourLabel")}
          defaultValue={effectiveDefault("ALERT_START_HOUR", initial.alerts.startHour)}
          min={0}
          max={23}
          onChange={(event) => setCameraOverride("ALERT_START_HOUR", event.target.value)}
        />
        <ZoneField
          fieldKey="ALERT_END_HOUR"
          name={fieldName("ALERT_END_HOUR")}
          label={t("endHourLabel")}
          defaultValue={effectiveDefault("ALERT_END_HOUR", initial.alerts.endHour)}
          min={0}
          max={23}
          onChange={(event) => setCameraOverride("ALERT_END_HOUR", event.target.value)}
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

      {/* ===== كشف المشاجرات (قابل للتخصيص لكل كاميرا) ===== */}
      <SettingsSection
        key={applyTo === "all" ? "fight-all" : `fight-${applyTo}`}
        titleKey="fightSection"
        icon={Swords}
        hintKey="fightHint"
        note={scopeNote}
      >
        <label className="flex cursor-pointer select-none items-center gap-3 text-sm font-medium text-slate-300 md:col-span-2">
          <input
            type="checkbox"
            name={fieldName("ENABLE_FIGHT_DETECTION")}
            checked={
              applyTo === "all"
                ? fightEnabled
                : effectiveBool("ENABLE_FIGHT_DETECTION", initial.fight.enabled)
            }
            onChange={(event) => {
              if (applyTo === "all") setFightEnabled(event.target.checked);
              setCameraOverride("ENABLE_FIGHT_DETECTION", event.target.checked);
            }}
            disabled={isPending}
            className="h-4 w-4 rounded border-slate-600 bg-slate-800 accent-teal-500"
          />
          {t("enableFightDetection")}
        </label>
        <div>
          <ZoneField
            fieldKey="FIGHT_IOU_THRESHOLD"
            name={fieldName("FIGHT_IOU_THRESHOLD")}
            label={t("fightIouThreshold")}
            defaultValue={effectiveDefault("FIGHT_IOU_THRESHOLD", initial.fight.iouThreshold)}
            step="0.05"
            min={0.05}
            max={0.9}
            onChange={(event) => setCameraOverride("FIGHT_IOU_THRESHOLD", event.target.value)}
          />
          <p className="mt-1.5 text-xs text-slate-500">{t("fightIouHint")}</p>
        </div>
        <div>
          <ZoneField
            fieldKey="FIGHT_MOTION_THRESHOLD"
            name={fieldName("FIGHT_MOTION_THRESHOLD")}
            label={t("fightMotionThreshold")}
            defaultValue={effectiveDefault("FIGHT_MOTION_THRESHOLD", initial.fight.motionThreshold)}
            step="5"
            min={0}
            onChange={(event) => setCameraOverride("FIGHT_MOTION_THRESHOLD", event.target.value)}
          />
          <p className="mt-1.5 text-xs text-slate-500">
            {t("fightMotionHint")}
          </p>
        </div>
        <div>
          <ZoneField
            fieldKey="FIGHT_MIN_FRAMES"
            name={fieldName("FIGHT_MIN_FRAMES")}
            label={t("fightMinFrames")}
            defaultValue={effectiveDefault("FIGHT_MIN_FRAMES", initial.fight.minFrames)}
            step="1"
            min={1}
            onChange={(event) => setCameraOverride("FIGHT_MIN_FRAMES", event.target.value)}
          />
          <p className="mt-1.5 text-xs text-slate-500">
            {t("fightMinFramesHint")}
          </p>
        </div>
        <div>
          <ZoneField
            fieldKey="CROWD_CONVERGENCE_THRESHOLD"
            name={fieldName("CROWD_CONVERGENCE_THRESHOLD")}
            label={t("crowdConvergenceThreshold")}
            defaultValue={effectiveDefault("CROWD_CONVERGENCE_THRESHOLD", initial.fight.convergenceThreshold)}
            step="5"
            min={0}
            onChange={(event) => setCameraOverride("CROWD_CONVERGENCE_THRESHOLD", event.target.value)}
          />
          <p className="mt-1.5 text-xs text-slate-500">
            {t("crowdConvergenceHint")}
          </p>
        </div>
        <div>
          <ZoneField
            fieldKey="CROWD_MIN_PERSONS"
            name={fieldName("CROWD_MIN_PERSONS")}
            label={t("crowdMinPersons")}
            defaultValue={effectiveDefault("CROWD_MIN_PERSONS", initial.fight.minPersons)}
            step="1"
            min={2}
            max={20}
            onChange={(event) => setCameraOverride("CROWD_MIN_PERSONS", event.target.value)}
          />
          <p className="mt-1.5 text-xs text-slate-500">
            {t("crowdMinPersonsHint")}
          </p>
        </div>
        <div>
          <ZoneField
            fieldKey="CROWD_CONVERGENCE_RADIUS_PX"
            name={fieldName("CROWD_CONVERGENCE_RADIUS_PX")}
            label={t("crowdConvergenceRadius")}
            defaultValue={effectiveDefault("CROWD_CONVERGENCE_RADIUS_PX", initial.fight.convergenceRadius)}
            step="10"
            min={20}
            onChange={(event) => setCameraOverride("CROWD_CONVERGENCE_RADIUS_PX", event.target.value)}
          />
          <p className="mt-1.5 text-xs text-slate-500">
            {t("crowdConvergenceRadiusHint")}
          </p>
        </div>
      </SettingsSection>

      {/* ===== كشف الزي المدرسي/اللون الممنوع (قابل للتخصيص لكل كاميرا) ===== */}
      <SettingsSection
        key={applyTo === "all" ? "color-all" : `color-${applyTo}`}
        titleKey="colorSection"
        icon={Palette}
        hintKey="colorHint"
        note={scopeNote}
      >
        <label className="flex cursor-pointer select-none items-center gap-3 text-sm font-medium text-slate-300 md:col-span-2">
          <input
            type="checkbox"
            name={fieldName("ENABLE_COLOR_DETECTION")}
            checked={
              applyTo === "all"
                ? colorEnabled
                : effectiveBool("ENABLE_COLOR_DETECTION", initial.color.enabled)
            }
            onChange={(event) => {
              if (applyTo === "all") setColorEnabled(event.target.checked);
              setCameraOverride("ENABLE_COLOR_DETECTION", event.target.checked);
            }}
            disabled={isPending}
            className="h-4 w-4 rounded border-slate-600 bg-slate-800 accent-teal-500"
          />
          {t("enableColorDetection")}
        </label>
        <div>
          <label
            htmlFor={fieldName("FORBIDDEN_COLOR_HEX")}
            className="mb-1.5 block text-xs font-medium text-slate-300"
          >
            {t("forbiddenColorLabel")}
          </label>
          <div className="flex items-center gap-3">
            {/* منتقي لون أصلي — يرسل القيمة السداسية دائماً مع الحفظ */}
            <input
              id={fieldName("FORBIDDEN_COLOR_HEX")}
              name={fieldName("FORBIDDEN_COLOR_HEX")}
              type="color"
              defaultValue={String(effectiveDefault("FORBIDDEN_COLOR_HEX", initial.color.forbiddenColorHex))}
              onChange={(event) =>
                setCameraOverride("FORBIDDEN_COLOR_HEX", event.target.value.toUpperCase())
              }
              disabled={isPending}
              className="h-10 w-14 shrink-0 cursor-pointer rounded-md border border-slate-700 bg-slate-800/80 p-1"
            />
            <span
              dir="ltr"
              className="font-mono text-xs text-slate-400"
            >
              {String(effectiveDefault("FORBIDDEN_COLOR_HEX", initial.color.forbiddenColorHex))}
            </span>
          </div>
          <p className="mt-1.5 text-xs text-slate-500">
            {t("forbiddenColorHint")}
          </p>
        </div>
        <div>
          <ZoneField
            fieldKey="COLOR_TOLERANCE"
            name={fieldName("COLOR_TOLERANCE")}
            label={t("colorToleranceLabel")}
            defaultValue={effectiveDefault("COLOR_TOLERANCE", initial.color.tolerance)}
            step="1"
            min={0}
            max={255}
            onChange={(event) => setCameraOverride("COLOR_TOLERANCE", event.target.value)}
          />
          <p className="mt-1.5 text-xs text-slate-500">
            {t("colorToleranceHint")}
          </p>
        </div>
        <div>
          <ZoneField
            fieldKey="COLOR_MIN_PERCENTAGE"
            name={fieldName("COLOR_MIN_PERCENTAGE")}
            label={t("colorMinPercentageLabel")}
            defaultValue={effectiveDefault("COLOR_MIN_PERCENTAGE", initial.color.minPercentage)}
            step="1"
            min={0}
            max={100}
            onChange={(event) => setCameraOverride("COLOR_MIN_PERCENTAGE", event.target.value)}
          />
          <p className="mt-1.5 text-xs text-slate-500">
            {t("colorMinPercentageHint")}
          </p>
        </div>
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
