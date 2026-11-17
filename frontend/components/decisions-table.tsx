"use client";

// جدول سجل قرارات الوكيل — يعرض (الوقت، الكاميرا، نوع القرار، السبب/الشرح)
// الصفوف تأتي من الـ server component (GET /api/decisions محمي بـ JWT)
import { useLanguage } from "@/components/language-context";
import { localeDateTimeTag } from "@/lib/dictionary";

interface DecisionRow {
  id: number;
  timestamp: string;
  cameraId: string;
  decisionType: string;
  reasoning: string;
  confidence: number | null;
}

/** لون/شارة لكل نوع قرار — تُميَّز بصرياً حسب حرجتها */
const typeStyles: Record<string, string> = {
  alert_sent: "bg-red-900/40 text-red-300 border-red-800",
  alert_suppressed: "bg-green-900/40 text-green-300 border-green-800",
  anomaly_escalated: "bg-amber-900/40 text-amber-300 border-amber-800",
  camera_offline: "bg-gray-800 text-gray-300 border-gray-700",
  fight_detected: "bg-red-900/40 text-red-300 border-red-800",
  crowd_surge_detected: "bg-orange-900/40 text-orange-300 border-orange-800",
  forbidden_color_intrusion: "bg-violet-900/40 text-violet-300 border-violet-800",
};

export default function DecisionsTable({
  decisions,
}: {
  decisions: DecisionRow[];
}) {
  const { t, locale } = useLanguage();

  const typeLabel = (type: string) => {
    const labels: Record<string, string> = {
      alert_sent: t("decisionAlertSent"),
      alert_suppressed: t("decisionAlertSuppressed"),
      anomaly_escalated: t("decisionAnomalyEscalated"),
      camera_offline: t("decisionCameraOffline"),
      fight_detected: t("decisionFightDetected"),
      crowd_surge_detected: t("decisionCrowdSurgeDetected"),
      forbidden_color_intrusion: t("decisionForbiddenColor"),
    };
    return labels[type] || type || t("decisionTypeUnknown");
  };

  const cameraLabel = (cameraId: string) => {
    if (!cameraId) return t("unknownCamera");
    return `${t("cameraUnknownName")} ${cameraId}`;
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold mb-2">{t("decisionsTitle")}</h1>
        <p className="text-sm text-gray-400">{t("decisionsSubtitle")}</p>
      </div>

      {decisions.length === 0 ? (
        <p className="rounded-md border border-gray-800 bg-gray-800/60 px-4 py-3 text-sm text-gray-400">
          {t("decisionsEmpty")}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-800 bg-gray-800/60 shadow-xl">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700 bg-gray-900/60 text-left text-gray-300">
                <th className="px-4 py-3 font-medium">{t("decisionsTimeColumn")}</th>
                <th className="px-4 py-3 font-medium">{t("decisionsCameraColumn")}</th>
                <th className="px-4 py-3 font-medium">{t("decisionsTypeColumn")}</th>
                <th className="px-4 py-3 font-medium">{t("decisionsReasonColumn")}</th>
              </tr>
            </thead>
            <tbody>
              {decisions.map((decision) => (
                <tr
                  key={decision.id}
                  className="border-b border-gray-800 last:border-b-0 hover:bg-gray-900/40 transition"
                >
                  <td className="px-4 py-3 text-gray-300 whitespace-nowrap" suppressHydrationWarning>
                    {decision.timestamp
                      ? new Date(decision.timestamp).toLocaleString(
                          localeDateTimeTag(locale),
                          { hour12: false }
                        )
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-gray-300 whitespace-nowrap">
                    {cameraLabel(decision.cameraId)}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span
                      className={`inline-block rounded border px-2 py-0.5 text-xs ${
                        typeStyles[decision.decisionType] ||
                        "bg-gray-800 text-gray-300 border-gray-700"
                      }`}
                    >
                      {typeLabel(decision.decisionType)}
                    </span>
                    {decision.confidence !== null && (
                      <span className="mx-1 text-xs text-gray-500" suppressHydrationWarning>
                        {t("decisionConfidence")}: {(decision.confidence * 100).toFixed(0)}%
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-300" dir="auto">
                    {decision.reasoning || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
