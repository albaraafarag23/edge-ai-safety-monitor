import { Check, Hand } from "lucide-react";
import { Link } from "react-router-dom";
import { mediaUrl } from "../api/client";
import { useSetStatus } from "../api/queries";
import type { Incident } from "../api/types";
import { useAuth } from "../lib/auth";
import { formatDateTime, SEVERITY_STYLES, timeAgo } from "../lib/format";
import { bilingual, useText } from "../lib/i18n";
import { incidentTitle, joinParts, severityLabel, usePluginText } from "../lib/terms";
import { StatusBadge } from "./ui";

const TEXT = bilingual(
  {
    onIt: "I'm on it",
    done: "Done",
    isOnIt: (who: string) => `${who} is on it`,
    closedBy: (who: string) => `closed by ${who}`,
  },
  {
    onIt: "أتولّى الأمر",
    done: "تم",
    isOnIt: (who: string) => `${who} يتولّى الأمر`,
    closedBy: (who: string) => `أغلقها ${who}`,
  },
);

function Row({ incident: i, canHandle }: { incident: Incident; canHandle: boolean }) {
  const t = useText(TEXT);
  const plugin = usePluginText();
  const setStatus = useSetStatus(i.event_id);
  const thumb = mediaUrl(i.snapshot_url);
  const who = i.status_updated_by?.split(" ")[0];
  const by = who && i.status === "acknowledged" ? t.isOnIt(who) : who && i.status === "resolved" ? t.closedBy(who) : null;
  const next = i.status === "open" ? "acknowledged" : i.status === "acknowledged" ? "resolved" : null;

  return (
    <li className="flex items-center gap-4 py-3">
      <span className={`h-12 w-1 shrink-0 rounded-full ${SEVERITY_STYLES[i.severity]?.bar ?? "bg-ink/30"}`} aria-hidden />
      <Link to={`/app/incidents/${i.event_id}`} className="group flex min-w-0 flex-1 items-center gap-4">
        <span className="relative hidden aspect-[4/3] w-20 shrink-0 overflow-hidden rounded-lg bg-ink/10 sm:block">
          {thumb && (
            <img src={thumb} alt="" loading="lazy" className="absolute inset-0 h-full w-full object-cover"
              onError={(e) => (e.currentTarget.style.display = "none")} />
          )}
        </span>
        <span className="min-w-0">
          <span className="block truncate font-display font-semibold text-ink group-hover:text-amber-700">{incidentTitle(i)}</span>
          <span className="block truncate text-sm text-ink/65" title={formatDateTime(i.received_at)}>
            {joinParts([severityLabel(i.severity), plugin.location(i.location, i.metadata.zone_id) ?? i.camera_id, timeAgo(i.received_at), by])}
          </span>
        </span>
      </Link>
      <StatusBadge status={i.status} />
      {canHandle && next && (
        <button
          disabled={setStatus.isPending}
          onClick={() => setStatus.mutate({ status: next })}
          className={`hidden shrink-0 items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-semibold disabled:opacity-50 sm:inline-flex ${
            next === "acknowledged" ? "bg-ink text-paper hover:bg-ink/85" : "text-ink ring-1 ring-ink/20 hover:bg-paper"
          }`}
        >
          {next === "acknowledged" ? <Hand className="h-4 w-4" /> : <Check className="h-4 w-4" />}
          {next === "acknowledged" ? t.onIt : t.done}
        </button>
      )}
    </li>
  );
}

/** Incidents one per line: what, where, when, who is on it, and the next step in one tap. */
export function IncidentList({ incidents }: { incidents: Incident[] }) {
  const canHandle = useAuth().user?.role !== "viewer";
  return (
    <ul className="divide-y divide-ink/[0.07]">
      {incidents.map((i) => (
        <Row key={i.event_id} incident={i} canHandle={canHandle} />
      ))}
    </ul>
  );
}
