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
                    // الإعدادات المنفردة للكاميرا (Per-Camera Settings) — إن وُجدت
                    settings:
                      camera.settings && typeof camera.settings === "object"
                        ? (camera.settings as Record<string, unknown>)
                        : undefined,
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
            trackCooldownSec:
              typeof settings["TRACK_COOLDOWN_SEC"] === "number"
                ? settings["TRACK_COOLDOWN_SEC"]
                : 60,
            fight: {
              enabled: settings["ENABLE_FIGHT_DETECTION"] === true,
              iouThreshold:
                typeof settings["FIGHT_IOU_THRESHOLD"] === "number"
                  ? settings["FIGHT_IOU_THRESHOLD"]
                  : 0.2,
              motionThreshold:
                typeof settings["FIGHT_MOTION_THRESHOLD"] === "number"
                  ? settings["FIGHT_MOTION_THRESHOLD"]
                  : 50,
              minFrames:
                typeof settings["FIGHT_MIN_FRAMES"] === "number"
                  ? settings["FIGHT_MIN_FRAMES"]
                  : 5,
              convergenceThreshold:
                typeof settings["CROWD_CONVERGENCE_THRESHOLD"] === "number"
                  ? settings["CROWD_CONVERGENCE_THRESHOLD"]
                  : 80,
              minPersons:
                typeof settings["CROWD_MIN_PERSONS"] === "number"
                  ? settings["CROWD_MIN_PERSONS"]
                  : 3,
              convergenceRadius:
                typeof settings["CROWD_CONVERGENCE_RADIUS_PX"] === "number"
                  ? settings["CROWD_CONVERGENCE_RADIUS_PX"]
                  : 150,
            },
            color: {
              enabled: settings["ENABLE_COLOR_DETECTION"] === true,
              forbiddenColorHex:
                typeof settings["FORBIDDEN_COLOR_HEX"] === "string"
                  ? settings["FORBIDDEN_COLOR_HEX"]
                  : "#0000FF",
              tolerance:
                typeof settings["COLOR_TOLERANCE"] === "number"
                  ? settings["COLOR_TOLERANCE"]
                  : 40,
              minPercentage:
                typeof settings["COLOR_MIN_PERCENTAGE"] === "number"
                  ? settings["COLOR_MIN_PERCENTAGE"]
                  : 30,
            },
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
