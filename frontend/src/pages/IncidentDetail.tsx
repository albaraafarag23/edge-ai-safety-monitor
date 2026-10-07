import { useState } from "react";
import Markdown from "react-markdown";
import { Link, useParams } from "react-router-dom";
import { ApiError, mediaUrl } from "../api/client";
import { useIncident, useReport, useSetStatus } from "../api/queries";
import type { Incident, IncidentStatus } from "../api/types";
import { PageHeader } from "../components/Layout";
import { Card, ErrorState, SeverityBadge, Spinner, StatusBadge } from "../components/ui";
import { formatDateTime, formatDuration, humanize, humanizeItem, timeAgo } from "../lib/format";

function Evidence({ incident }: { incident: Incident }) {
  const [imageFailed, setImageFailed] = useState(false);
  const [videoFailed, setVideoFailed] = useState(false);
  const snapshot = mediaUrl(incident.snapshot_url);
  const clip = mediaUrl(incident.clip_url);

  return (
    <Card title="Evidence">
      <div className="grid gap-4 md:grid-cols-2">
        <figure>
          {snapshot && !imageFailed ? (
            <a href={snapshot} target="_blank" rel="noreferrer">
              <img src={snapshot} alt="Annotated frame when the rule fired" onError={() => setImageFailed(true)}
                className="aspect-video w-full rounded-lg border border-slate-200 bg-slate-100 object-contain" />
            </a>
          ) : (
            <div className="flex aspect-video items-center justify-center rounded-lg border border-dashed border-slate-300 text-sm text-slate-400">
              No snapshot available
            </div>
          )}
          <figcaption className="mt-1.5 text-xs text-slate-500">Snapshot when the rule fired</figcaption>
        </figure>
        <figure>
          {clip && !videoFailed ? (
            <video controls preload="metadata" onError={() => setVideoFailed(true)}
              className="aspect-video w-full rounded-lg border border-slate-200 bg-slate-900">
              <source src={clip} type="video/mp4" onError={() => setVideoFailed(true)} />
            </video>
          ) : (
            <div className="flex aspect-video flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-slate-300 text-sm text-slate-400">
              {clip ? "This browser can't play the clip" : "No clip available"}
            </div>
          )}
          <figcaption className="mt-1.5 flex justify-between text-xs text-slate-500">
            <span>Video around the incident</span>
            {clip && (
              <a href={clip} download className="font-medium text-sky-700 hover:underline">
                Download clip
              </a>
            )}
          </figcaption>
        </figure>
      </div>
    </Card>
  );
}

const DELIVERY_TEXT: Record<string, string> = {
  sent: "Emailed",
  failed: "Email failed",
  not_configured: "Email not configured",
  suppressed_duplicate: "Not re-sent (repeat)",
};

function ReportCard({ id }: { id: string }) {
  const report = useReport(id);
  if (report.isPending) return <Card title="AI report"><Spinner label="Loading report…" /></Card>;
  if (report.isError) {
    const notYet = report.error instanceof ApiError && report.error.status === 404;
    return (
      <Card title="AI report">
        {notYet ? (
          <p className="text-sm text-slate-500">The report is being written. It will appear here automatically.</p>
        ) : (
          <ErrorState error={report.error} onRetry={() => report.refetch()} />
        )}
      </Card>
    );
  }
  const r = report.data;
  const d = r.delivery ?? {};
  return (
    <Card
      title="AI report"
      action={<span className="text-xs text-slate-400">by {r.generated_by} · {timeAgo(r.created_at)}</span>}
    >
      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
        <span className="font-medium text-slate-800">{DELIVERY_TEXT[d.status ?? ""] ?? "Not sent"}</span>
        {d.recipients?.length ? <span>To {d.recipients.join(", ")}</span> : null}
        {d.attachments?.length ? <span>Attached: {d.attachments.join(", ")}</span> : null}
        {d.duplicate_of && (
          <Link to={`/incidents/${d.duplicate_of}`} className="text-sky-700 hover:underline">
            Original: {d.duplicate_of}
          </Link>
        )}
        {d.error && <span className="text-red-700">{d.error}</span>}
      </div>
      <article className="report text-sm leading-6 text-slate-700">
        <Markdown>{r.markdown}</Markdown>
      </article>
    </Card>
  );
}

const ACTIONS: { status: IncidentStatus; label: string; style: string }[] = [
  { status: "acknowledged", label: "Acknowledge", style: "bg-violet-600 hover:bg-violet-700 text-white" },
  { status: "resolved", label: "Resolve", style: "bg-emerald-600 hover:bg-emerald-700 text-white" },
  { status: "open", label: "Reopen", style: "border border-slate-300 text-slate-700 hover:bg-slate-50" },
];

function StatusCard({ incident }: { incident: Incident }) {
  const [note, setNote] = useState("");
  const setStatus = useSetStatus(incident.event_id);
  return (
    <Card title="Status">
      <div className="flex items-center justify-between">
        <StatusBadge status={incident.status} />
        {incident.status_updated_at && (
          <span className="text-xs text-slate-400">updated {timeAgo(incident.status_updated_at)}</span>
        )}
      </div>
      {incident.status_note && (
        <p className="mt-3 rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700">{incident.status_note}</p>
      )}
      <label className="mt-4 block text-xs font-medium text-slate-500">
        Note (optional)
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          placeholder="e.g. Worker given a hard hat at 14:05"
          className="mt-1 w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm text-slate-900 focus:border-sky-500 focus:ring-1 focus:ring-sky-500 focus:outline-none"
        />
      </label>
      <div className="mt-3 flex flex-wrap gap-2">
        {ACTIONS.filter((a) => a.status !== incident.status).map((a) => (
          <button
            key={a.status}
            disabled={setStatus.isPending}
            onClick={() => setStatus.mutate({ status: a.status, note }, { onSuccess: () => setNote("") })}
            className={`rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${a.style}`}
          >
            {a.label}
          </button>
        ))}
      </div>
      {setStatus.isError && <p className="mt-2 text-sm text-red-700">Couldn't update: {setStatus.error.message}</p>}
    </Card>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-sm">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-medium text-slate-900">{children}</dd>
    </div>
  );
}

export function IncidentDetail() {
  const { id = "" } = useParams();
  const incident = useIncident(id);

  if (incident.isPending) return <Spinner />;
  if (incident.isError) {
    return (
      <>
        <Link to="/incidents" className="text-sm text-sky-700 hover:underline">← Incidents</Link>
        <div className="mt-4">
          {incident.error instanceof ApiError && incident.error.status === 404 ? (
            <p className="text-slate-600">Incident {id} doesn't exist.</p>
          ) : (
            <ErrorState error={incident.error} onRetry={() => incident.refetch()} />
          )}
        </div>
      </>
    );
  }

  const i = incident.data;
  const m = i.metadata ?? {};
  return (
    <>
      <Link to="/incidents" className="text-sm text-sky-700 hover:underline">← Incidents</Link>
      <div className="mt-3">
        <PageHeader
          title={humanize(i.event_type)}
          subtitle={`${i.camera_id}${i.location !== "NOT SPECIFIED" ? ` · ${i.location}` : ""} · ${formatDateTime(i.timestamp)}`}
          actions={<SeverityBadge severity={i.severity} />}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Evidence incident={i} />
          <ReportCard id={i.event_id} />
        </div>
        <div className="space-y-6">
          <StatusCard incident={i} />
          <Card title="Details">
            <dl className="divide-y divide-slate-100">
              <Row label="Event ID"><span className="font-mono text-xs">{i.event_id}</span></Row>
              <Row label="Detected">{formatDateTime(i.timestamp)}</Row>
              <Row label="Duration">{formatDuration(i.duration_seconds)}</Row>
              <Row label="Camera">{i.camera_id}</Row>
              <Row label="Zone">{m.zone_name ?? "—"}</Row>
              <Row label="Rule">{m.rule_id ?? "—"}</Row>
              <Row label="Missing equipment">
                {m.missing_equipment?.length ? m.missing_equipment.map(humanizeItem).join(", ") : "—"}
              </Row>
              <Row label="Detected objects">{m.detected_entities?.join(", ") || "—"}</Row>
              <Row label="Model">{m.model ?? "—"}</Row>
            </dl>
          </Card>
          <Card title="Rules violated">
            <ul className="space-y-2 text-sm text-slate-700">
              {i.rules_violated.map((r) => <li key={r}>{r}</li>)}
            </ul>
          </Card>
          <details className="rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
            <summary className="cursor-pointer font-medium text-slate-700">Raw incident JSON</summary>
            <pre className="mt-3 max-h-96 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-100">
              {JSON.stringify(i, null, 2)}
            </pre>
          </details>
        </div>
      </div>
    </>
  );
}
