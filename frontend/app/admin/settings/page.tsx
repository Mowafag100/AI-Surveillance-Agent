// صفحة الإعدادات — server component يجلب القيم ثم يمررها لنموذج العميل
import FormSettings from "@/components/form-settings";
import { serverFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AdminSettingsPage() {
  const res = await serverFetch("/api/settings");
  const settings = res.ok
    ? ((await res.json()) as Record<string, unknown>)
    : {};

  // توكن بوت التلغرام يصل مقنّعاً من الباكند — لا نمرر قيمته للنموذج
  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-2">⚙️ إعدادات النظام</h1>
      <p className="text-sm text-gray-400 mb-6">
        التعديلات تُحفظ في <code className="text-gray-300">config.json</code>{" "}
        ويطبّقها الوكيل فوراً (Hot Reload) دون إعادة تشغيل.
      </p>

      <div className="rounded-xl border border-gray-800 bg-gray-800/60 p-6 shadow-xl">
        <FormSettings
          initial={{
            // قائمة الكاميرات الحقيقية — أوى توافق خلفي صف واحد من CAMERA_URL القديم
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
                : [], // التمرير maxlen: FormSettings يعرض صف editing فارغاً إن كانت فراغاً
            telegramChatId: typeof settings["TELEGRAM_CHAT_ID"] === "string"
              ? settings["TELEGRAM_CHAT_ID"]
              : "",
            zoneDwellTime:
              typeof settings["ZONE_DWELL_TIME"] === "number"
                ? settings["ZONE_DWELL_TIME"]
                : 2,
          }}
        />
      </div>
    </div>
  );
}
