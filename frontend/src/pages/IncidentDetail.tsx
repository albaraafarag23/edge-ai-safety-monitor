import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import { Link, useParams } from "react-router-dom";
import { ApiError, mediaUrl } from "../api/client";
import { useIncident, useIncidents, useReport, useSetStatus } from "../api/queries";
import type { Incident, IncidentStatus } from "../api/types";
import { PageHeader } from "../components/Layout";
import { Card, ErrorState, SeverityBadge, Spinner, StatusBadge } from "../components/ui";
import { useAuth } from "../lib/auth";
import { formatDateTime, formatDuration, timeAgo } from "../lib/format";
import { bilingual, useLang, useText } from "../lib/i18n";
import { classLabel, incidentTitle, itemLabel, joinList, joinParts, severityLabel, usePluginText } from "../lib/terms";

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
    actions: { acknowledged: "I'm on it", resolved: "Done", open: "Reopen" },
    status: "Status",
    whatNow: "What to do now",
    state: {
      open: "Nobody is on this yet.",
      acknowledged: (who: string | null, when: string) => (who ? `${who} is on it (${when}).` : `Someone is on it (${when}).`),
      resolved: (who: string | null, when: string) => (who ? `Done. Closed by ${who} ${when}.` : `Done. Closed ${when}.`),
    },
    noSteps: "Check the snapshot and the clip, then deal with it as your site rules say.",
    addNote: "Add a note",
    keys: "Keys: A I'm on it · D Done · R Reopen",
    print: "Print",
    printedFrom: (when: string) => `Printed from the SiteSentry console on ${when}`,
    pattern: (n: number) => `This has happened ${n} times in the last 24 hours on this camera.`,
    firstToday: "First time in the last 24 hours on this camera.",
    seeThem: "See them",
    technical: "Technical details",
    report_hint: "The formal record of this incident, written for the site file.",
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
    lasted: (d: string) => `lasted ${d}`,
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
    actions: { acknowledged: "أتولّى الأمر", resolved: "تم", open: "إعادة فتح" },
    status: "الحالة",
    whatNow: "ما العمل الآن",
    state: {
      open: "لم يتولَّ أحد هذه الحادثة بعد.",
      acknowledged: (who: string | null, when: string) => (who ? `${who} يتولّى الأمر (${when}).` : `هناك من يتولّى الأمر (${when}).`),
      resolved: (who: string | null, when: string) => (who ? `تم. أغلقها ${who} ${when}.` : `تم. أُغلقت ${when}.`),
    },
    noSteps: "راجع اللقطة والمقطع، ثم تعامل مع الأمر وفق قواعد الموقع.",
    addNote: "إضافة ملاحظة",
    keys: "المفاتيح: A أتولّى الأمر · D تم · R إعادة فتح",
    print: "طباعة",
    printedFrom: (when: string) => `طُبع من لوحة تحكم SiteSentry في ${when}`,
    pattern: (n: number) => `تكرر هذا ${n} مرة خلال آخر 24 ساعة على هذه الكاميرا.`,
    firstToday: "أول مرة خلال آخر 24 ساعة على هذه الكاميرا.",
    seeThem: "عرضها",
    technical: "التفاصيل التقنية",
    report_hint: "السجل الرسمي لهذه الحادثة، مكتوب لملف الموقع.",
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
    lasted: (d: string) => `استمرت ${d}`,
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
        <figure className="print:hidden">
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
      <p className="-mt-1 mb-3 text-sm text-ink/65">{t.report_hint}</p>
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

/** "This has happened 12 times in the last 24 hours on this camera": a one-off or a pattern. */
function Pattern({ incident }: { incident: Incident }) {
  const t = useText(TEXT);
  const same = useIncidents({ camera_id: incident.camera_id, event_type: incident.event_type, hours: 24, limit: 1 });
  if (!same.data) return null;
  const n = same.data.total;
  return (
    <p className="mt-5 border-t border-ink/10 pt-4 text-sm text-ink/70">
      {n > 1 ? t.pattern(n) : t.firstToday}
      {n > 1 && (
        <Link
          to={`/app/incidents?camera_id=${encodeURIComponent(incident.camera_id)}&event_type=${encodeURIComponent(incident.event_type)}`}
          className="ms-2 font-semibold text-amber-700 hover:underline print:hidden"
        >
          {t.seeThem}
        </Link>
      )}
    </p>
  );
}

/** The top of the page: who's on it, the site-approved steps, and the buttons to handle it. */
function WhatNow({ incident }: { incident: Incident }) {
  const [note, setNote] = useState("");
  const [noteOpen, setNoteOpen] = useState(false);
  const setStatus = useSetStatus(incident.event_id);
  const canHandle = useAuth().user?.role !== "viewer";
  const t = useText(TEXT);
  const plugin = usePluginText();
  const steps = plugin.ruleActions(incident.metadata?.rule_id);
  const when = timeAgo(incident.status_updated_at);
  const who = incident.status_updated_by ?? null;
  const state =
    incident.status === "open" ? t.state.open : incident.status === "acknowledged" ? t.state.acknowledged(who, when) : t.state.resolved(who, when);
  const next: IncidentStatus[] =
    incident.status === "open" ? ["acknowledged", "resolved"] : incident.status === "acknowledged" ? ["resolved", "open"] : ["open"];
  const act = (status: IncidentStatus) =>
    setStatus.mutate({ status, note }, { onSuccess: () => { setNote(""); setNoteOpen(false); } });

  // A = I'm on it, D = Done, R = Reopen, for desk users; ignored while typing a note
  useEffect(() => {
    if (!canHandle) return;
    const keys: Record<string, IncidentStatus> = { a: "acknowledged", d: "resolved", r: "open" };
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (e.ctrlKey || e.metaKey || e.altKey || target.closest("input, textarea, select, [contenteditable]")) return;
      const status = keys[e.key.toLowerCase()];
      if (status && next.includes(status) && !setStatus.isPending) {
        e.preventDefault();
        act(status);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <section className="mb-8 grid gap-6 rounded-2xl bg-white p-6 ring-1 ring-ink/[0.08] lg:grid-cols-[1.4fr_1fr]">
      <div>
        <h2 className="font-serif text-3xl text-ink">{t.whatNow}</h2>
        {steps.length ? (
          <ol className="mt-4 space-y-3">
            {steps.map((step, n) => (
              <li key={n} className="flex gap-3 text-[15px] leading-relaxed text-ink/80">
                <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${n === 0 ? "bg-amber-400 text-ink" : "bg-ink/[0.07] text-ink/60"}`}>
                  {n + 1}
                </span>
                <span className={n === 0 ? "font-semibold text-ink" : ""}>{step}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="mt-4 text-ink/70">{t.noSteps}</p>
        )}
        <Pattern incident={incident} />
      </div>
      <div className="flex flex-col gap-4 rounded-xl bg-paper p-5">
        <div className="flex items-center gap-2">
          <StatusBadge status={incident.status} />
        </div>
        <p className="text-lg leading-snug text-ink">{state}</p>
        {incident.status_note && <p className="rounded-lg bg-white px-3 py-2 text-sm text-ink/70">“{incident.status_note}”</p>}
        {canHandle ? (
          <div className="flex flex-col gap-4 print:hidden">
            <div className="flex flex-wrap gap-2">
              {next.map((status, n) => (
                <button
                  key={status}
                  disabled={setStatus.isPending}
                  onClick={() => act(status)}
                  className={`rounded-full px-5 py-2.5 text-sm font-semibold disabled:opacity-50 ${
                    n === 0 ? "bg-ink text-paper hover:bg-ink/85" : "text-ink ring-1 ring-ink/20 hover:bg-white"
                  }`}
                >
                  {t.actions[status]}
                </button>
              ))}
            </div>
            <p className="hidden text-xs text-ink/50 lg:block">{t.keys}</p>
            {noteOpen ? (
              <label className="block text-xs font-medium text-ink/60">
                {t.note}
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={2}
                  autoFocus
                  placeholder={t.notePlaceholder}
                  className="mt-1 w-full rounded-lg border border-ink/15 bg-white px-3 py-2 text-sm text-ink focus:border-amber-500 focus:ring-1 focus:ring-amber-500 focus:outline-none"
                />
              </label>
            ) : (
              <button onClick={() => setNoteOpen(true)} className="self-start text-sm font-medium text-amber-700 hover:underline">
                + {t.addNote}
              </button>
            )}
            {setStatus.isError && <p className="text-sm text-red-700">{t.couldntUpdate(setStatus.error.message)}</p>}
          </div>
        ) : (
          <p className="text-sm text-ink/65 print:hidden">{t.viewOnly}</p>
        )}
        <button onClick={() => window.print()} className="self-start text-sm font-medium text-ink/65 hover:text-ink print:hidden">
          {t.print}
        </button>
      </div>
    </section>
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
        title={incidentTitle(i)}
        image={mediaUrl(i.snapshot_url)}
        back={back}
        subtitle={joinParts([location ?? i.camera_id, timeAgo(i.received_at), t.lasted(formatDuration(i.duration_seconds))])}
        actions={<SeverityBadge severity={i.severity} />}
      />

      {/* on paper: a compact header instead of the photo opener */}
      <header className="mb-6 hidden border-b border-ink/20 pb-4 print:block">
        <p className="text-sm">{t.printedFrom(formatDateTime(new Date().toISOString()))}</p>
        <h1 className="mt-2 font-display text-3xl font-semibold">{incidentTitle(i)}</h1>
        <p className="mt-1 text-sm">
          {joinParts([severityLabel(i.severity), location, i.camera_id, formatDateTime(i.timestamp), formatDuration(i.duration_seconds), i.event_id])}
        </p>
      </header>
      <WhatNow incident={i} />

      <div className="space-y-6">
        <Evidence incident={i} />
        <div className="print:break-inside-avoid">
          <ReportCard id={i.event_id} />
        </div>
        <details className="group rounded-2xl bg-white p-5 ring-1 ring-ink/[0.08] print:hidden">
          <summary className="cursor-pointer font-display font-semibold text-ink/70 group-open:text-ink">{t.technical}</summary>
          <div className="mt-4 grid gap-6 lg:grid-cols-2">
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
            <div>
              <p className="text-sm font-medium text-slate-500">{t.rulesViolated}</p>
              <ul className="mt-2 space-y-2 text-sm text-slate-700">
                {i.rules_violated.map((r) => <li key={r}>{ruleText(r)}</li>)}
              </ul>
              <p className="mt-6 text-sm font-medium text-slate-500">{t.raw}</p>
              <pre dir="ltr" className="mt-2 max-h-72 overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">
                {JSON.stringify(i, null, 2)}
              </pre>
            </div>
          </div>
        </details>
      </div>
    </>
  );
}
