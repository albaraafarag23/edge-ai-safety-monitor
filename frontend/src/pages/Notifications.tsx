import { BellRing, CheckCheck, Mail, Monitor, Volume2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { mediaUrl } from "../api/client";
import { useIncidents } from "../api/queries";
import type { Incident } from "../api/types";
import { PageHeader } from "../components/Layout";
import { Card, EmptyState, ErrorState, SeverityBadge, Spinner, StatusBadge } from "../components/ui";
import { formatDateTime, humanize, humanizeItem, timeAgo } from "../lib/format";
import { desktopSupported, enableDesktop, isUnread, updatePrefs, useNotificationPrefs } from "../lib/notifications";

const VIEWS = [
  { key: "all", label: "All" },
  { key: "unread", label: "Unread" },
  { key: "urgent", label: "High & critical" },
] as const;
type View = (typeof VIEWS)[number]["key"];

const EMAIL_TEXT: Record<string, [string, string]> = {
  sent: ["Emailed to supervisors", "text-emerald-700"],
  failed: ["Email failed", "text-red-700"],
  not_configured: ["Email not configured", "text-slate-500"],
  suppressed_duplicate: ["Repeat, not re-emailed", "text-slate-500"],
};

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition ${checked ? "bg-slate-900" : "bg-slate-200"}`}
    >
      <span className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition ${checked ? "translate-x-5" : ""}`} />
    </button>
  );
}

function Setting({ icon, title, children, control }: { icon: ReactNode; title: string; children: ReactNode; control: ReactNode }) {
  return (
    <div className="flex items-start gap-3 py-4 first:pt-0 last:pb-0">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600">{icon}</span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-slate-900">{title}</p>
        <p className="mt-0.5 text-xs leading-5 text-slate-500">{children}</p>
      </div>
      {control}
    </div>
  );
}

function Settings() {
  const [prefs, update] = useNotificationPrefs();
  const [blocked, setBlocked] = useState(desktopSupported() && Notification.permission === "denied");

  return (
    <Card title="Alert settings">
      <div className="divide-y divide-slate-100">
        <Setting
          icon={<Monitor className="h-4 w-4" />}
          title="Desktop notifications"
          control={
            <Toggle
              label="Desktop notifications"
              checked={prefs.desktop}
              onChange={async (on) => {
                if (!on) return update({ desktop: false });
                setBlocked(!(await enableDesktop()));
              }}
            />
          }
        >
          {!desktopSupported()
            ? "This browser doesn't support notifications."
            : blocked
              ? "Blocked by the browser. Allow notifications for this site in the browser settings, then try again."
              : "Pop-up for high and critical incidents while this console is open in a tab."}
        </Setting>
        <Setting
          icon={<Volume2 className="h-4 w-4" />}
          title="Sound"
          control={<Toggle label="Sound" checked={prefs.sound} onChange={(on) => update({ sound: on })} />}
        >
          A short chime for high and critical incidents.
        </Setting>
        <Setting icon={<Mail className="h-4 w-4" />} title="Email" control={null}>
          Every incident is emailed with its AI report, snapshot and clip to the supervisor list set on the server.
          Repeats of the same rule on the same camera are held back for a few minutes.
        </Setting>
      </div>
      <p className="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
        Desktop and sound settings apply to this browser only.
      </p>
    </Card>
  );
}

function NotificationItem({ incident: i, unread }: { incident: Incident; unread: boolean }) {
  const thumb = mediaUrl(i.snapshot_url);
  const email = EMAIL_TEXT[i.report?.delivery_status ?? ""];
  const missing = i.metadata.missing_equipment?.map(humanizeItem).join(", ").toLowerCase();
  return (
    <li>
      <Link
        to={`/app/incidents/${i.event_id}`}
        className={`flex gap-4 px-5 py-4 transition hover:bg-slate-50 ${unread ? "bg-sky-50/50" : ""}`}
      >
        <span className="relative h-16 w-24 shrink-0 overflow-hidden rounded-lg bg-slate-100">
          {thumb && <img src={thumb} alt="" loading="lazy" className="h-full w-full object-cover" />}
          {unread && <span className="absolute top-1.5 left-1.5 h-2.5 w-2.5 rounded-full bg-sky-500 ring-2 ring-white" aria-label="Unread" />}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-slate-900">{humanize(i.event_type)}</span>
            <SeverityBadge severity={i.severity} />
            <StatusBadge status={i.status} />
          </span>
          <span className="mt-1 block text-sm text-slate-600">
            {i.camera_id}
            {i.location !== "NOT SPECIFIED" ? ` · ${i.location}` : ""}
            {missing ? ` · missing ${missing}` : ""}
          </span>
          <span className="mt-1 flex flex-wrap gap-x-3 text-xs text-slate-500">
            <span title={formatDateTime(i.received_at)}>{timeAgo(i.received_at)}</span>
            {i.report ? (
              <span className={email?.[1] ?? "text-slate-500"}>{email?.[0] ?? "Report written"}</span>
            ) : (
              <span>Writing report…</span>
            )}
          </span>
        </span>
      </Link>
    </li>
  );
}

export function Notifications() {
  const [view, setView] = useState<View>("all");
  const [prefs] = useNotificationPrefs();
  const incidents = useIncidents({ limit: 50 });
  const all = incidents.data?.items ?? [];
  const unreadCount = all.filter((i) => isUnread(i, prefs.lastSeen)).length;
  const shown = all.filter((i) =>
    view === "unread" ? isUnread(i, prefs.lastSeen) : view === "urgent" ? i.severity === "HIGH" || i.severity === "CRITICAL" : true,
  );

  return (
    <>
      <PageHeader
        title="Notifications"
        subtitle={unreadCount ? `${unreadCount} unread alert${unreadCount === 1 ? "" : "s"}` : "You're all caught up"}
        actions={
          unreadCount > 0 && (
            <button
              onClick={() => updatePrefs({ lastSeen: new Date().toISOString() })}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              <CheckCheck className="h-4 w-4" /> Mark all as read
            </button>
          )
        }
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex gap-1 border-b border-slate-100 px-3 py-2" role="tablist">
            {VIEWS.map((v) => (
              <button
                key={v.key}
                role="tab"
                aria-selected={view === v.key}
                onClick={() => setView(v.key)}
                className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                  view === v.key ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {v.label}
                {v.key === "unread" && unreadCount > 0 && <span className="ml-1.5 tabular-nums opacity-70">{unreadCount}</span>}
              </button>
            ))}
          </div>
          {incidents.isPending ? (
            <Spinner />
          ) : incidents.isError ? (
            <div className="p-5">
              <ErrorState error={incidents.error} onRetry={() => incidents.refetch()} />
            </div>
          ) : shown.length ? (
            <ul className="divide-y divide-slate-100">
              {shown.map((i) => (
                <NotificationItem key={i.event_id} incident={i} unread={isUnread(i, prefs.lastSeen)} />
              ))}
            </ul>
          ) : (
            <div className="py-6">
              <EmptyState title={view === "unread" ? "No unread alerts" : "No alerts yet"}>
                <span className="inline-flex items-center gap-1.5">
                  <BellRing className="h-4 w-4" /> New incidents show up here the moment they're detected.
                </span>
              </EmptyState>
            </div>
          )}
          {all.length >= 50 && (
            <p className="border-t border-slate-100 px-5 py-3 text-center text-sm">
              <Link to="/app/incidents" className="font-medium text-sky-700 hover:underline">
                Older alerts are in Incidents →
              </Link>
            </p>
          )}
        </section>
        <div>
          <Settings />
        </div>
      </div>
    </>
  );
}
