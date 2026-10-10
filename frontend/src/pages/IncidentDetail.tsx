import { useState } from "react";
import Markdown from "react-markdown";
import { Link, useParams } from "react-router-dom";
import { ApiError, mediaUrl } from "../api/client";
import { useIncident, useReport, useSetStatus } from "../api/queries";
import type { Incident, IncidentStatus } from "../api/types";
import { PageHeader } from "../components/Layout";
import { Card, ErrorState, SeverityBadge, Spinner, StatusBadge } from "../components/ui";
import { useAuth } from "../lib/auth";
import { formatDateTime, formatDuration, timeAgo } from "../lib/format";
import { bilingual, useLang, useText } from "../lib/i18n";
import { classLabel, eventTypeLabel, itemLabel, joinList, joinParts, usePluginText } from "../lib/terms";

const TEXT = bilingual(
  {
    evidence: "Evidence",
    snapshotAlt: "Annotated frame when the rule fired",
    noSnapshot: "No snapshot available",
    snapshotCaption: "Snapshot when the rule fired",
    cantPlay: "This browser can't play the clip",
    noClip: "No clip available",
    clipCaption: "Video around the incident",
    downloadClip: "Download clip",
    delivery: {
      sent: "Emailed",
      retrying: "Email not sent yet, retrying",
      failed: "Email failed",
      not_configured: "Email not configured",
      suppressed_duplicate: "Not re-sent (repeat)",
    } as Record<string, string>,
    notSent: "Not sent",
    report: "AI report",
    loadingReport: "Loading report…",
    beingWritten: "The report is being written. It will appear here automatically.",
    by: (who: string, when: string) => `by ${who} · ${when}`,
    authors: { template: "template", duplicate: "repeat notice" } as Record<string, string>,
    to: (list: string) => `To ${list}`,
    attached: (list: string) => `Attached: ${list}`,
    original: (id: string) => `Original: ${id}`,
    nextTry: (when: string, attempt: number) => `Next try ${when} (attempt ${attempt})`,
    englishOnly: "",
    actions: { acknowledged: "Acknowledge", resolved: "Resolve", open: "Reopen" },
    status: "Status",
    updated: (when: string) => `updated ${when}`,
    note: "Note (optional)",
    notePlaceholder: "e.g. Worker given a hard hat at 14:05",
    couldntUpdate: (message: string) => `Couldn't update: ${message}`,
    viewOnly: "You have view-only access. A supervisor or admin handles incidents.",
    back: "Incidents",
    doesntExist: (id: string) => `Incident ${id} doesn't exist.`,
    details: "Details",
    rows: {
      eventId: "Event ID",
      detected: "Detected",
      duration: "Duration",
      camera: "Camera",
      zone: "Zone",
      rule: "Rule",
      missing: "Missing equipment",
      objects: "Detected objects",
      model: "Model",
    },
    rulesViolated: "Rules violated",
    raw: "Raw incident JSON",
  },
  {
    evidence: "الأدلة",
    snapshotAlt: "الإطار مع ما رُصد فيه لحظة تحقق القاعدة",
    noSnapshot: "لا توجد لقطة",
    snapshotCaption: "لقطة لحظة تحقق القاعدة",
    cantPlay: "لا يستطيع هذا المتصفح تشغيل المقطع",
    noClip: "لا يوجد مقطع",
    clipCaption: "فيديو حول وقت الحادثة",
    downloadClip: "تنزيل المقطع",
    delivery: {
      sent: "أُرسل بالبريد",
      retrying: "لم يُرسل البريد بعد، جارٍ إعادة المحاولة",
      failed: "فشل إرسال البريد",
      not_configured: "البريد غير مُعدّ",
      suppressed_duplicate: "لم يُعد إرساله (تكرار)",
    },
    notSent: "لم يُرسل",
    report: "تقرير الذكاء الاصطناعي",
    loadingReport: "جارٍ تحميل التقرير…",
    beingWritten: "جارٍ كتابة التقرير. سيظهر هنا تلقائيًا.",
    by: (who: string, when: string) => `بواسطة ${who} · ${when}`,
    authors: { template: "النموذج الثابت", duplicate: "إشعار تكرار" },
    to: (list: string) => `إلى ${list}`,
    attached: (list: string) => `المرفقات: ${list}`,
    original: (id: string) => `الأصلية: ${id}`,
    nextTry: (when: string, attempt: number) => `المحاولة التالية ${when} (المحاولة ${attempt})`,
    englishOnly: "كُتب هذا التقرير بالإنجليزية فقط.",
    actions: { acknowledged: "استلام", resolved: "تم الحل", open: "إعادة فتح" },
    status: "الحالة",
    updated: (when: string) => `حُدّثت ${when}`,
    note: "ملاحظة (اختيارية)",
    notePlaceholder: "مثال: سُلّم العامل خوذة الساعة 14:05",
    couldntUpdate: (message: string) => `تعذّر التحديث: ${message}`,
    viewOnly: "لديك صلاحية المشاهدة فقط. يتعامل المشرف أو المسؤول مع الحوادث.",
    back: "الحوادث",
    doesntExist: (id: string) => `الحادثة ${id} غير موجودة.`,
    details: "التفاصيل",
    rows: {
      eventId: "رقم الحادثة",
      detected: "وقت الرصد",
      duration: "المدة",
      camera: "الكاميرا",
      zone: "المنطقة",
      rule: "القاعدة",
      missing: "المعدات الناقصة",
      objects: "ما رُصد",
      model: "النموذج",
    },
    rulesViolated: "القواعد المخالَفة",
    raw: "بيانات الحادثة الخام (JSON)",
  },
);

function Evidence({ incident }: { incident: Incident }) {
  const [imageFailed, setImageFailed] = useState(false);
  const [videoFailed, setVideoFailed] = useState(false);
  const snapshot = mediaUrl(incident.snapshot_url);
  const clip = mediaUrl(incident.clip_url);
  const t = useText(TEXT);

  return (
    <Card title={t.evidence}>
      <div className="grid gap-4 md:grid-cols-2">
        <figure>
          {snapshot && !imageFailed ? (
            <a href={snapshot} target="_blank" rel="noreferrer">
              <img src={snapshot} alt={t.snapshotAlt} onError={() => setImageFailed(true)}
                className="aspect-video w-full rounded-lg border border-slate-200 bg-slate-100 object-contain" />
            </a>
          ) : (
            <div className="flex aspect-video items-center justify-center rounded-lg border border-dashed border-slate-300 text-sm text-slate-400">
              {t.noSnapshot}
            </div>
          )}
          <figcaption className="mt-1.5 text-xs text-slate-500">{t.snapshotCaption}</figcaption>
        </figure>
        <figure>
          {clip && !videoFailed ? (
            <video controls preload="metadata" onError={() => setVideoFailed(true)}
              className="aspect-video w-full rounded-lg border border-slate-200 bg-slate-900">
              <source src={clip} type="video/mp4" onError={() => setVideoFailed(true)} />
            </video>
          ) : (
            <div className="flex aspect-video flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-slate-300 text-sm text-slate-400">
              {clip ? t.cantPlay : t.noClip}
            </div>
          )}
          <figcaption className="mt-1.5 flex justify-between text-xs text-slate-500">
            <span>{t.clipCaption}</span>
            {clip && (
              <a href={clip} download className="font-medium text-sky-700 hover:underline">
                {t.downloadClip}
              </a>
            )}
          </figcaption>
        </figure>
      </div>
    </Card>
  );
}

function ReportCard({ id }: { id: string }) {
  const report = useReport(id);
  const t = useText(TEXT);
  const { lang } = useLang();
  if (report.isPending) return <Card title={t.report}><Spinner label={t.loadingReport} /></Card>;
  if (report.isError) {
    const notYet = report.error instanceof ApiError && report.error.status === 404;
    return (
      <Card title={t.report}>
        {notYet ? (
          <p className="text-sm text-slate-500">{t.beingWritten}</p>
        ) : (
          <ErrorState error={report.error} onRetry={() => report.refetch()} />
        )}
      </Card>
    );
  }
  const r = report.data;
  const d = r.delivery ?? {};
  // the report in the reader's language when it exists (older reports are English only)
  const arabic = lang === "ar" && r.markdown_ar ? r.markdown_ar : null;
  return (
    <Card title={t.report} action={<span className="text-xs text-slate-400">{t.by(t.authors[r.generated_by] ?? r.generated_by, timeAgo(r.created_at))}</span>}>
      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
        <span className="font-medium text-slate-800">{t.delivery[d.status ?? ""] ?? t.notSent}</span>
        {d.recipients?.length ? <span>{t.to(d.recipients.join(", "))}</span> : null}
        {d.attachments?.length ? <span>{t.attached(d.attachments.join(", "))}</span> : null}
        {d.duplicate_of && (
          <Link to={`/app/incidents/${d.duplicate_of}`} className="text-sky-700 hover:underline">
            {t.original(d.duplicate_of)}
          </Link>
        )}
        {d.status === "retrying" && d.next_attempt_at && (
          <span>{t.nextTry(timeAgo(d.next_attempt_at), (d.attempts ?? 0) + 1)}</span>
        )}
        {d.error && <span className={d.status === "retrying" ? "text-amber-700" : "text-red-700"}>{d.error}</span>}
      </div>
      {lang === "ar" && !arabic && <p className="mb-3 text-xs text-slate-500">{t.englishOnly}</p>}
      <article className="report text-sm leading-6 text-slate-700" dir={arabic ? "rtl" : "ltr"} lang={arabic ? "ar" : "en"}>
        <Markdown>{arabic ?? r.markdown}</Markdown>
      </article>
    </Card>
  );
}

const ACTIONS: { status: IncidentStatus; style: string }[] = [
  { status: "acknowledged", style: "bg-violet-600 hover:bg-violet-700 text-white" },
  { status: "resolved", style: "bg-emerald-600 hover:bg-emerald-700 text-white" },
  { status: "open", style: "border border-slate-300 text-slate-700 hover:bg-slate-50" },
];

function StatusCard({ incident }: { incident: Incident }) {
  const [note, setNote] = useState("");
  const setStatus = useSetStatus(incident.event_id);
  const canHandle = useAuth().user?.role !== "viewer";
  const t = useText(TEXT);
  return (
    <Card title={t.status}>
      <div className="flex items-center justify-between">
        <StatusBadge status={incident.status} />
        {incident.status_updated_at && (
          <span className="text-xs text-slate-400">{t.updated(timeAgo(incident.status_updated_at))}</span>
        )}
      </div>
      {incident.status_note && (
        <p className="mt-3 rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700">{incident.status_note}</p>
      )}
      {canHandle ? (
        <>
          <label className="mt-4 block text-xs font-medium text-slate-500">
            {t.note}
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder={t.notePlaceholder}
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
                {t.actions[a.status]}
              </button>
            ))}
          </div>
          {setStatus.isError && <p className="mt-2 text-sm text-red-700">{t.couldntUpdate(setStatus.error.message)}</p>}
        </>
      ) : (
        <p className="mt-4 text-xs text-slate-500">{t.viewOnly}</p>
      )}
    </Card>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-sm">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-end font-medium text-slate-900">{children}</dd>
    </div>
  );
}

export function IncidentDetail() {
  const { id = "" } = useParams();
  const incident = useIncident(id);
  const t = useText(TEXT);
  const plugin = usePluginText();
  const back = (
    <Link to="/app/incidents">
      <span className="flip-rtl inline-block">←</span> {t.back}
    </Link>
  );

  if (incident.isPending) return <Spinner />;
  if (incident.isError) {
    return (
      <>
        <span className="text-sm text-sky-700 hover:underline">{back}</span>
        <div className="mt-4">
          {incident.error instanceof ApiError && incident.error.status === 404 ? (
            <p className="text-slate-600">{t.doesntExist(id)}</p>
          ) : (
            <ErrorState error={incident.error} onRetry={() => incident.refetch()} />
          )}
        </div>
      </>
    );
  }

  const i = incident.data;
  const m = i.metadata ?? {};
  const location = plugin.location(i.location, m.zone_id);
  // "RULE_PPE_01: Hard hat required on site" -> the rule's description in the current language
  const ruleText = (line: string) => {
    const [ruleId, ...rest] = line.split(": ");
    return rest.length ? `${ruleId}: ${plugin.ruleDescription(ruleId, rest.join(": "))}` : line;
  };
  return (
    <>
      <PageHeader
        title={eventTypeLabel(i.event_type)}
        image={mediaUrl(i.snapshot_url)}
        back={back}
        subtitle={joinParts([i.camera_id, location, formatDateTime(i.timestamp)])}
        actions={<SeverityBadge severity={i.severity} />}
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Evidence incident={i} />
          <ReportCard id={i.event_id} />
        </div>
        <div className="space-y-6">
          <StatusCard incident={i} />
          <Card title={t.details}>
            <dl className="divide-y divide-slate-100">
              <Row label={t.rows.eventId}><span className="font-mono text-xs">{i.event_id}</span></Row>
              <Row label={t.rows.detected}>{formatDateTime(i.timestamp)}</Row>
              <Row label={t.rows.duration}>{formatDuration(i.duration_seconds)}</Row>
              <Row label={t.rows.camera}>{i.camera_id}</Row>
              <Row label={t.rows.zone}>{plugin.zoneName(m.zone_id, m.zone_name ?? null) ?? "—"}</Row>
              <Row label={t.rows.rule}>{m.rule_id ?? "—"}</Row>
              <Row label={t.rows.missing}>
                {m.missing_equipment?.length ? joinList(m.missing_equipment.map(itemLabel)) : "—"}
              </Row>
              <Row label={t.rows.objects}>{(m.detected_entities?.length ? joinList(m.detected_entities.map(classLabel)) : "—")}</Row>
              <Row label={t.rows.model}>{m.model ?? "—"}</Row>
            </dl>
          </Card>
          <Card title={t.rulesViolated}>
            <ul className="space-y-2 text-sm text-slate-700">
              {i.rules_violated.map((r) => <li key={r}>{ruleText(r)}</li>)}
            </ul>
          </Card>
          <details className="rounded-lg bg-white ring-1 ring-ink/10 p-4 text-sm shadow-sm">
            <summary className="cursor-pointer font-medium text-slate-700">{t.raw}</summary>
            <pre dir="ltr" className="mt-3 max-h-96 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-100">
              {JSON.stringify(i, null, 2)}
            </pre>
          </details>
        </div>
      </div>
    </>
  );
}
