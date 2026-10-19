// صفحة الإعدادات — server component يجلب القيم ثم يمررها لنموذج العميل
import FormSettings from "@/components/form-settings";
import SettingsHeading from "@/components/settings-heading";
import { serverFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AdminSettingsPage() {
  const res = await serverFetch("/api/settings");
  const settings = res.ok
    ? ((await res.json()) as Record<string, unknown>)
    : {};

  // توكن بوت التلغرام وكلمة مرور SMTP يصلان مقنّعين من الباكند — لا نمرر قيمتهما للنموذج
  return (
    <div className="max-w-2xl">
      <SettingsHeading />

      <div className="rounded-xl border border-gray-800 bg-gray-800/60 p-6 shadow-xl">
        <FormSettings
          initial={{
            // قائمة الكاميرات الحقيقية — أو توافق خلفي صف واحد من CAMERA_URL القديم
            cameras: Array.isArray(settings["CAMERAS"])
              ? ((settings["CAMERAS"] as Record<string, unknown>[])
                  .map((camera, index) => ({
                    id: Number(camera.id) || index + 1,
                    name: typeof camera.name === "string" ? camera.name : "",
                    url: typeof camera.url === "string" ? camera.url : "",
                  }))
                  .filter((camera) => camera.url || camera.name))
              : typeof settings["CAMERA_URL"] === "string" &&
                  settings["CAMERA_URL"]
                ? [
                    {
                      id: 1,
                      name: "Camera 1",
                      url: String(settings["CAMERA_URL"]),
                    },
                  ]
                : [], // FormSettings يعرض صفاً فارغاً واحداً عندما تكون القائمة فارغة
            telegramChatId: typeof settings["TELEGRAM_CHAT_ID"] === "string"
              ? settings["TELEGRAM_CHAT_ID"]
              : "",
            zoneDwellTime:
              typeof settings["ZONE_DWELL_TIME"] === "number"
                ? settings["ZONE_DWELL_TIME"]
                : 2,
            cameraTimeoutSec:
              typeof settings["CAMERA_TIMEOUT_SEC"] === "number"
                ? settings["CAMERA_TIMEOUT_SEC"]
                : 30,
            zone: {
              tlx: typeof settings["ZONE_TOP_LEFT_X"] === "number"
                ? settings["ZONE_TOP_LEFT_X"]
                : 100,
              tly: typeof settings["ZONE_TOP_LEFT_Y"] === "number"
                ? settings["ZONE_TOP_LEFT_Y"]
                : 100,
              brx: typeof settings["ZONE_BOTTOM_RIGHT_X"] === "number"
                ? settings["ZONE_BOTTOM_RIGHT_X"]
                : 400,
              bry: typeof settings["ZONE_BOTTOM_RIGHT_Y"] === "number"
                ? settings["ZONE_BOTTOM_RIGHT_Y"]
                : 300,
            },
            alerts: {
              startHour: typeof settings["ALERT_START_HOUR"] === "number"
                ? settings["ALERT_START_HOUR"]
                : 0,
              endHour: typeof settings["ALERT_END_HOUR"] === "number"
                ? settings["ALERT_END_HOUR"]
                : 23,
            },
            modelSize: typeof settings["MODEL_SIZE"] === "string"
              ? settings["MODEL_SIZE"]
              : "n",
            minConfidence:
              typeof settings["MIN_CONFIDENCE"] === "number"
                ? settings["MIN_CONFIDENCE"]
                : 0.3,
            email: {
              enabled: settings["ENABLE_EMAIL_ALERTS"] === true,
              host: typeof settings["SMTP_HOST"] === "string"
                ? settings["SMTP_HOST"]
                : "",
              port: typeof settings["SMTP_PORT"] === "number"
                ? settings["SMTP_PORT"]
                : 587,
              user: typeof settings["SMTP_USER"] === "string"
                ? settings["SMTP_USER"]
                : "",
              passwordSet: typeof settings["SMTP_PASSWORD"] === "string" &&
                settings["SMTP_PASSWORD"].length > 0,
              emailTo: typeof settings["ALERT_EMAIL_TO"] === "string"
                ? settings["ALERT_EMAIL_TO"]
                : "",
            },
          }}
        />
      </div>
    </div>
  );
}
