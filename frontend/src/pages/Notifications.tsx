import { BellRing, CheckCheck, Mail, Monitor, Volume2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { mediaUrl } from "../api/client";
import { useIncidents } from "../api/queries";
import type { Incident } from "../api/types";
import { PageHeader } from "../components/Layout";
import { Card, EmptyState, ErrorState, SeverityBadge, Spinner, StatusBadge } from "../components/ui";
import { formatDateTime, timeAgo } from "../lib/format";
import { bilingual, plural, useText } from "../lib/i18n";
import { desktopSupported, enableDesktop, isUnread, updatePrefs, useNotificationPrefs } from "../lib/notifications";
import { incidentTitle, itemLabel, joinList, usePluginText } from "../lib/terms";

const VIEWS = ["all", "unread", "urgent"] as const;
type View = (typeof VIEWS)[number];

const EMAIL_STYLE: Record<string, string> = {
  sent: "text-emerald-700",
  retrying: "text-amber-700",
  failed: "text-red-700",
  not_configured: "text-slate-500",
  suppressed_duplicate: "text-slate-500",
};

const TEXT = bilingual(
  {
    views: { all: "All", unread: "Unread", urgent: "High & critical" } as Record<View, string>,
    email: {
      sent: "Emailed to supervisors",
      retrying: "Email not sent yet, retrying",
      failed: "Email failed",
      not_configured: "Email not configured",
      suppressed_duplicate: "Repeat, not re-emailed",
    } as Record<string, string>,
    alertSettings: "Alert settings",
    desktop: "Desktop notifications",
    desktopUnsupported: "This browser doesn't support notifications.",
    desktopBlocked: "Blocked by the browser. Allow notifications for this site in the browser settings, then try again.",
    desktopHint: "Pop-up for high and critical incidents while this console is open in a tab.",
    sound: "Sound",
    soundHint: "A short chime for high and critical incidents.",
    emailTitle: "Email",
    emailHint:
      "Every incident is emailed with its AI report, snapshot and clip to the supervisor list set on the server. " +
      "Repeats of the same rule on the same camera are held back for a few minutes.",
    thisBrowser: "Desktop and sound settings apply to this browser only.",
    unread: "Unread",
    missing: (items: string) => ` · missing ${items.toLowerCase()}`,
    reportWritten: "Report written",
    writingReport: "Writing report…",
    title: "Notifications",
    unreadCount: (n: number): string => `${n} unread alert${n === 1 ? "" : "s"}`,
    caughtUp: "You're all caught up",
    markAllRead: "Mark all as read",
    noUnread: "No unread alerts",
    noAlerts: "No alerts yet",
    newHint: "New incidents show up here the moment they're detected.",
    older: "Older alerts are in Incidents",
  },
  {
    views: { all: "الكل", unread: "غير المقروءة", urgent: "المرتفعة والحرجة" },
    email: {
      sent: "أُرسل إلى المشرفين بالبريد",
      retrying: "لم يُرسل البريد بعد، جارٍ إعادة المحاولة",
      failed: "فشل إرسال البريد",
      not_configured: "البريد غير مُعدّ",
      suppressed_duplicate: "تكرار، لم يُعد إرساله",
    },
    alertSettings: "إعدادات التنبيه",
    desktop: "إشعارات سطح المكتب",
    desktopUnsupported: "هذا المتصفح لا يدعم الإشعارات.",
    desktopBlocked: "حظرها المتصفح. اسمح بالإشعارات لهذا الموقع من إعدادات المتصفح، ثم حاول مرة أخرى.",
    desktopHint: "إشعار منبثق للحوادث المرتفعة والحرجة ما دامت لوحة التحكم مفتوحة في تبويب.",
    sound: "الصوت",
    soundHint: "نغمة قصيرة للحوادث المرتفعة والحرجة.",
    emailTitle: "البريد الإلكتروني",
    emailHint:
      "تُرسل كل حادثة بالبريد مع تقرير الذكاء الاصطناعي واللقطة والمقطع إلى قائمة المشرفين المحددة على الخادم. " +
      "وتُؤجَّل تكرارات القاعدة نفسها على الكاميرا نفسها بضع دقائق.",
    thisBrowser: "تنطبق إعدادات سطح المكتب والصوت على هذا المتصفح فقط.",
    unread: "غير مقروءة",
    missing: (items: string) => ` · ينقصه: ${items}`,
    reportWritten: "كُتب التقرير",
    writingReport: "جارٍ كتابة التقرير…",
    title: "الإشعارات",
    unreadCount: (n: number) => `${n} ${plural("ar", n, { one: "تنبيه غير مقروء", two: "تنبيه غير مقروء", few: "تنبيهات غير مقروءة", other: "تنبيه غير مقروء" })}`,
    caughtUp: "لا جديد، اطّلعت على كل شيء",
    markAllRead: "تحديد الكل كمقروء",
    noUnread: "لا توجد تنبيهات غير مقروءة",
    noAlerts: "لا توجد تنبيهات بعد",
    newHint: "تظهر الحوادث الجديدة هنا لحظة رصدها.",
    older: "التنبيهات الأقدم في صفحة الحوادث",
  },
);

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition ${checked ? "bg-slate-900" : "bg-slate-200"}`}
    >
      <span className={`absolute top-0.5 start-0.5 h-5 w-5 rounded-full bg-white shadow transition ${checked ? "translate-x-5 rtl:-translate-x-5" : ""}`} />
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
  const t = useText(TEXT);

  return (
    <Card title={t.alertSettings}>
      <div className="divide-y divide-slate-100">
        <Setting
          icon={<Monitor className="h-4 w-4" />}
          title={t.desktop}
          control={
            <Toggle
              label={t.desktop}
              checked={prefs.desktop}
              onChange={async (on) => {
                if (!on) return update({ desktop: false });
                setBlocked(!(await enableDesktop()));
              }}
            />
          }
        >
          {!desktopSupported()
            ? t.desktopUnsupported
            : blocked
              ? t.desktopBlocked
              : t.desktopHint}
        </Setting>
        <Setting
          icon={<Volume2 className="h-4 w-4" />}
          title={t.sound}
          control={<Toggle label={t.sound} checked={prefs.sound} onChange={(on) => update({ sound: on })} />}
        >
          {t.soundHint}
        </Setting>
        <Setting icon={<Mail className="h-4 w-4" />} title={t.emailTitle} control={null}>
          {t.emailHint}
        </Setting>
      </div>
      <p className="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
        {t.thisBrowser}
      </p>
    </Card>
  );
}

function NotificationItem({ incident: i, unread }: { incident: Incident; unread: boolean }) {
  const thumb = mediaUrl(i.snapshot_url);
  const t = useText(TEXT);
  const plugin = usePluginText();
  const status = i.report?.delivery_status ?? "";
  const missing = i.metadata.missing_equipment?.length ? joinList(i.metadata.missing_equipment.map(itemLabel)) : "";
  const location = plugin.location(i.location, i.metadata.zone_id);
  return (
    <li>
      <Link
        to={`/app/incidents/${i.event_id}`}
        className={`flex gap-4 px-5 py-4 transition hover:bg-slate-50 ${unread ? "bg-sky-50/50" : ""}`}
      >
        <span className="relative h-16 w-24 shrink-0 overflow-hidden rounded-lg bg-slate-100">
          {thumb && <img src={thumb} alt="" loading="lazy" className="h-full w-full object-cover" />}
          {unread && <span className="absolute top-1.5 start-1.5 h-2.5 w-2.5 rounded-full bg-sky-500 ring-2 ring-white" aria-label={t.unread} />}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-slate-900">{incidentTitle(i)}</span>
            <SeverityBadge severity={i.severity} />
            <StatusBadge status={i.status} />
          </span>
          <span className="mt-1 block text-sm text-slate-600">
            {i.camera_id}
            {location ? ` · ${location}` : ""}
            {missing ? t.missing(missing) : ""}
          </span>
          <span className="mt-1 flex flex-wrap gap-x-3 text-xs text-slate-500">
            <span title={formatDateTime(i.received_at)}>{timeAgo(i.received_at)}</span>
            {i.report ? (
              <span className={EMAIL_STYLE[status] ?? "text-slate-500"}>{t.email[status] ?? t.reportWritten}</span>
            ) : (
              <span>{t.writingReport}</span>
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
  const t = useText(TEXT);
  const all = incidents.data?.items ?? [];
  const unreadCount = all.filter((i) => isUnread(i, prefs.lastSeen)).length;
  const shown = all.filter((i) =>
    view === "unread" ? isUnread(i, prefs.lastSeen) : view === "urgent" ? i.severity === "HIGH" || i.severity === "CRITICAL" : true,
  );

  return (
    <>
      <PageHeader
        title={t.title}
        subtitle={unreadCount ? t.unreadCount(unreadCount) : t.caughtUp}
        actions={
          unreadCount > 0 && (
            <button
              onClick={() => updatePrefs({ lastSeen: new Date().toISOString() })}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              <CheckCheck className="h-4 w-4" /> {t.markAllRead}
            </button>
          )
        }
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <section className="overflow-hidden rounded-lg bg-white ring-1 ring-ink/10 shadow-sm">
          <div className="flex gap-1 border-b border-slate-100 px-3 py-2" role="tablist">
            {VIEWS.map((v) => (
              <button
                key={v}
                role="tab"
                aria-selected={view === v}
                onClick={() => setView(v)}
                className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                  view === v ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {t.views[v]}
                {v === "unread" && unreadCount > 0 && <span className="ms-1.5 tabular-nums opacity-70">{unreadCount}</span>}
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
              <EmptyState title={view === "unread" ? t.noUnread : t.noAlerts}>
                <span className="inline-flex items-center gap-1.5">
                  <BellRing className="h-4 w-4" /> {t.newHint}
                </span>
              </EmptyState>
            </div>
          )}
          {all.length >= 50 && (
            <p className="border-t border-slate-100 px-5 py-3 text-center text-sm">
              <Link to="/app/incidents" className="font-medium text-sky-700 hover:underline">
                {t.older} <span className="flip-rtl inline-block">→</span>
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
