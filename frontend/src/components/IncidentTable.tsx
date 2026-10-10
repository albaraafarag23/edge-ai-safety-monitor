import { useNavigate } from "react-router-dom";
import type { Incident } from "../api/types";
import { formatDateTime, formatDuration, humanize, humanizeItem, timeAgo } from "../lib/format";
import { SeverityBadge, StatusBadge } from "./ui";

const DELIVERY_LABEL: Record<string, string> = {
  sent: "Emailed",
  retrying: "Email retrying",
  failed: "Email failed",
  not_configured: "Email off",
  suppressed_duplicate: "Repeat",
};

export function IncidentTable({ incidents, compact = false }: { incidents: Incident[]; compact?: boolean }) {
  const navigate = useNavigate();
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
            <th className="py-2 pr-4">Severity</th>
            <th className="py-2 pr-4">Incident</th>
            <th className="py-2 pr-4">Camera</th>
            {!compact && <th className="py-2 pr-4">Duration</th>}
            <th className="py-2 pr-4">Status</th>
            {!compact && <th className="py-2 pr-4">Report</th>}
            <th className="py-2 text-right">When</th>
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
              <td className="py-3 pr-4">
                <SeverityBadge severity={i.severity} />
              </td>
              <td className="py-3 pr-4">
                <p className="font-medium text-slate-900">{humanize(i.event_type)}</p>
                <p className="text-xs text-slate-500">
                  {i.location !== "NOT SPECIFIED" ? i.location : "No zone"}
                  {i.metadata.missing_equipment?.length
                    ? ` · missing ${i.metadata.missing_equipment.map(humanizeItem).join(", ").toLowerCase()}`
                    : ""}
                </p>
              </td>
              <td className="py-3 pr-4 text-slate-600">{i.camera_id}</td>
              {!compact && <td className="py-3 pr-4 tabular-nums text-slate-600">{formatDuration(i.duration_seconds)}</td>}
              <td className="py-3 pr-4">
                <StatusBadge status={i.status} />
              </td>
              {!compact && (
                <td className="py-3 pr-4 text-xs text-slate-500">
                  {i.report ? DELIVERY_LABEL[i.report.delivery_status ?? ""] ?? "Written" : "Pending"}
                </td>
              )}
              <td className="py-3 text-right text-slate-500" title={formatDateTime(i.received_at)}>
                {timeAgo(i.received_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
