import { useNavigate } from "react-router-dom";
import type { Incident } from "../api/types";
import { formatDateTime, formatDuration, timeAgo } from "../lib/format";
import { bilingual, useText } from "../lib/i18n";
import { incidentTitle, itemLabel, joinList, usePluginText } from "../lib/terms";
import { SeverityBadge, StatusBadge } from "./ui";

const TEXT = bilingual(
  {
    head: { severity: "Severity", incident: "Incident", camera: "Camera", duration: "Duration", status: "Status", report: "Report", when: "When" },
    delivery: {
      sent: "Emailed",
      retrying: "Email retrying",
      failed: "Email failed",
      not_configured: "Email off",
      suppressed_duplicate: "Repeat",
    } as Record<string, string>,
    written: "Written",
    pending: "Pending",
    noZone: "No zone",
    missing: (items: string) => ` · missing ${items.toLowerCase()}`,
  },
  {
    head: { severity: "الخطورة", incident: "الحادثة", camera: "الكاميرا", duration: "المدة", status: "الحالة", report: "التقرير", when: "الوقت" },
    delivery: {
      sent: "أُرسل بالبريد",
      retrying: "إعادة محاولة الإرسال",
      failed: "فشل الإرسال",
      not_configured: "البريد متوقف",
      suppressed_duplicate: "تكرار",
    },
    written: "مكتوب",
    pending: "قيد الكتابة",
    noZone: "بلا منطقة",
    missing: (items: string) => ` · ينقصه: ${items}`,
  },
);

export function IncidentTable({ incidents, compact = false }: { incidents: Incident[]; compact?: boolean }) {
  const navigate = useNavigate();
  const t = useText(TEXT);
  const plugin = usePluginText();
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-start text-xs font-medium uppercase tracking-wide text-slate-500">
            <th className="py-2 pe-4">{t.head.severity}</th>
            <th className="py-2 pe-4">{t.head.incident}</th>
            <th className="py-2 pe-4">{t.head.camera}</th>
            {!compact && <th className="py-2 pe-4">{t.head.duration}</th>}
            <th className="py-2 pe-4">{t.head.status}</th>
            {!compact && <th className="py-2 pe-4">{t.head.report}</th>}
            <th className="py-2 text-end">{t.head.when}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {incidents.map((i) => (
            <tr
              key={i.event_id}
              onClick={() => navigate(`/app/incidents/${i.event_id}`)}
              onKeyDown={(e) => e.key === "Enter" && navigate(`/app/incidents/${i.event_id}`)}
              tabIndex={0}
              className="cursor-pointer hover:bg-slate-50 focus:bg-slate-50 focus:outline-none"
            >
              <td className="py-3 pe-4">
                <SeverityBadge severity={i.severity} />
              </td>
              <td className="py-3 pe-4">
                <p className="font-medium text-slate-900">{incidentTitle(i)}</p>
                <p className="text-xs text-slate-500">
                  {plugin.location(i.location, i.metadata.zone_id) ?? t.noZone}
                  {i.metadata.missing_equipment?.length ? t.missing(joinList(i.metadata.missing_equipment.map(itemLabel))) : ""}
                </p>
              </td>
              <td className="py-3 pe-4 text-slate-600">{i.camera_id}</td>
              {!compact && <td className="py-3 pe-4 tabular-nums text-slate-600">{formatDuration(i.duration_seconds)}</td>}
              <td className="py-3 pe-4">
                <StatusBadge status={i.status} />
              </td>
              {!compact && (
                <td className="py-3 pe-4 text-xs text-slate-500">
                  {i.report ? (t.delivery[i.report.delivery_status ?? ""] ?? t.written) : t.pending}
                </td>
              )}
              <td className="py-3 text-end text-slate-500" title={formatDateTime(i.received_at)}>
                {timeAgo(i.received_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
