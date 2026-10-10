import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { useAnalytics } from "../api/queries";
import type { Analytics as Data, Severity } from "../api/types";
import { PageHeader } from "../components/Layout";
import { BarList, Card, EmptyState, ErrorState, Spinner } from "../components/ui";
import { SEVERITY_ORDER, SEVERITY_STYLES } from "../lib/format";
import { bilingual, LOCALES, currentLang, plural, useText } from "../lib/i18n";
import { dayNames } from "../lib/rules";
import { eventTypeLabel, itemLabel, severityLabel, usePluginText } from "../lib/terms";

const PERIODS = [7, 30, 90];

const TEXT = bilingual(
  {
    total: "Total",
    showTable: "Show as table",
    day: "Day",
    perDayBySeverity: "Incidents per day, by severity",
    byWeekdayHour: (busiest: string) => `Incidents by weekday and hour. Busiest: ${busiest}`,
    none: "none",
    incidents: (n: number): string => `${n} incident${n === 1 ? "" : "s"}`,
    busiest: "Busiest: ",
    noIncidents: "No incidents in this period",
    timesIn: (tz: string) => ` · times in ${tz}`,
    fewer: "Fewer",
    more: "More",
    timePeriod: "Time period",
    days: (n: number) => `${n} days`,
    title: "Analytics",
    subtitle: "When, where and what kind of safety incidents happen",
    tiles: {
      incidents: "Incidents",
      lastDays: (n: number) => `last ${n} days`,
      vsPrevious: (n: number) => `vs previous ${n} days`,
      handled: "Handled",
      handledHint: (n: number) => `${n} acknowledged or resolved`,
      median: "Median time to handle",
      medianHint: "detection to latest status change",
      common: "Most common",
    },
    perDay: "Incidents per day",
    when: "When incidents happen",
    byZone: "By zone",
    byType: "By type",
    missingPpe: "Missing PPE",
    noPpe: "No PPE incidents in this period",
    byCamera: "By camera",
    noZone: "No zone",
    units: { s: "s", min: "min", h: "h" },
  },
  {
    total: "المجموع",
    showTable: "عرض كجدول",
    day: "اليوم",
    perDayBySeverity: "الحوادث في اليوم حسب الخطورة",
    byWeekdayHour: (busiest: string) => `الحوادث حسب اليوم والساعة. الأكثر ازدحامًا: ${busiest}`,
    none: "لا يوجد",
    incidents: (n: number) => `${n} ${plural("ar", n, { one: "حادثة", two: "حادثة", few: "حوادث", other: "حادثة" })}`,
    busiest: "الأكثر ازدحامًا: ",
    noIncidents: "لا حوادث في هذه الفترة",
    timesIn: (tz: string) => ` · الأوقات بتوقيت ${tz}`,
    fewer: "أقل",
    more: "أكثر",
    timePeriod: "الفترة الزمنية",
    days: (n: number) => `${n} ${plural("ar", n, { few: "أيام", other: "يومًا" })}`,
    title: "التحليلات",
    subtitle: "متى وأين وما نوع حوادث السلامة التي تقع",
    tiles: {
      incidents: "الحوادث",
      lastDays: (n: number) => `آخر ${n} ${plural("ar", n, { few: "أيام", other: "يومًا" })}`,
      vsPrevious: (n: number) => `مقارنةً بالـ ${n} ${plural("ar", n, { few: "أيام", other: "يومًا" })} السابقة`,
      handled: "تمت معالجتها",
      handledHint: (n: number) => `${n} تم استلامها أو حلها`,
      median: "متوسط وقت المعالجة",
      medianHint: "من الرصد حتى آخر تغيير في الحالة",
      common: "الأكثر تكرارًا",
    },
    perDay: "الحوادث في اليوم",
    when: "متى تقع الحوادث",
    byZone: "حسب المنطقة",
    byType: "حسب النوع",
    missingPpe: "معدات الوقاية الناقصة",
    noPpe: "لا حوادث معدات وقاية في هذه الفترة",
    byCamera: "حسب الكاميرا",
    noZone: "بلا منطقة",
    units: { s: "ث", min: "د", h: "س" },
  },
);
// one-hue sequential ramp (light -> dark) for the heatmap
const HEAT_STEPS = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
// severity stacks bottom-up from critical, so the most serious sits on the baseline
const STACK: Severity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

function StatTile({ label, value, hint, delta }: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  delta?: { text: string; good: boolean; up: boolean };
}) {
  return (
    <div className="border-t-[3px] border-ink pt-5">
      <p className="font-serif text-xl text-ink/60 italic">{label}</p>
      <p
        className={`mt-1 font-display leading-none font-semibold tracking-[-0.04em] text-ink tabular-nums ${
          typeof value === "number" ? "text-6xl sm:text-7xl" : "text-4xl sm:text-5xl"
        }`}
      >
        {value}
      </p>
      <div className="mt-1 flex items-center gap-2 text-xs">
        {delta && (
          <span className={`inline-flex items-center gap-0.5 font-medium ${delta.good ? "text-emerald-700" : "text-red-700"}`}>
            {delta.up ? <ArrowUpRight className="h-3.5 w-3.5" /> : <ArrowDownRight className="h-3.5 w-3.5" />}
            {delta.text}
          </span>
        )}
        {hint && <span className="text-ink/40">{hint}</span>}
      </div>
    </div>
  );
}

/** Every day in the period, including days with no incidents. */
function fillDays(data: Data) {
  const byDay = new Map(data.by_day.map((d) => [d.day, d]));
  const days: ({ day: string } & Record<Severity, number>)[] = [];
  const today = new Date();
  for (let i = data.days - 1; i >= 0; i--) {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    days.push(byDay.get(key) ?? { day: key, CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 });
  }
  return days;
}

const dayLabel = (key: string, opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" }) =>
  new Date(`${key}T12:00:00`).toLocaleDateString(LOCALES[currentLang()], opts);

/** Index in STACK of the top (last non-empty) segment of a day's column; it gets the rounded end. */
const topSegment = (d: Record<Severity, number>) => STACK.reduce((top, k, j) => (d[k] ? j : top), -1);

function niceMax(n: number) {
  if (n <= 4) return 4;
  const step = Math.pow(10, Math.floor(Math.log10(n)));
  return Math.ceil(n / step) * step;
}

function DailyChart({ data }: { data: Data }) {
  const t = useText(TEXT);
  const days = fillDays(data);
  const totals = days.map((d) => STACK.reduce((s, k) => s + (d[k] ?? 0), 0));
  const max = niceMax(Math.max(...totals));
  const ticks = [0, max / 2, max];
  const labelEvery = Math.ceil(days.length / 8);

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600" aria-hidden>
        {SEVERITY_ORDER.map((s) => (
          <span key={s} className="flex items-center gap-1.5">
            <span className={`h-2.5 w-2.5 rounded-sm ${SEVERITY_STYLES[s].bar}`} /> {severityLabel(s)}
          </span>
        ))}
      </div>
      {/* time runs left to right in both languages */}
      <div className="flex gap-3" dir="ltr">
        <div className="flex h-52 flex-col justify-between pb-0 text-end text-xs text-slate-400 tabular-nums" aria-hidden>
          {[...ticks].reverse().map((t) => (
            <span key={t} className="-translate-y-1/2 first:translate-y-0 last:translate-y-1/2">{t}</span>
          ))}
        </div>
        <div className="relative flex-1">
          {/* hairline gridlines */}
          <div className="pointer-events-none absolute inset-0 flex flex-col justify-between" aria-hidden>
            {ticks.map((t) => <div key={t} className="h-px bg-slate-100" />)}
          </div>
          <div className="relative flex h-52 items-end gap-[2px]" role="img" aria-label={t.perDayBySeverity}>
            {days.map((d, i) => (
              <div key={d.day} className="group relative flex h-full flex-1 flex-col items-center justify-end">
                <div className="flex w-full max-w-6 flex-col-reverse gap-[2px]">
                  {STACK.map((s, j) =>
                    d[s] ? (
                      <div
                        key={s}
                        className={`${SEVERITY_STYLES[s].bar} ${j === topSegment(d) ? "rounded-t" : ""} group-hover:opacity-90`}
                        style={{ height: `${(d[s] / max) * 208 - 2}px`, minHeight: 2 }}
                      />
                    ) : null,
                  )}
                </div>
                {/* hover target is the whole column slot */}
                <div dir={currentLang() === "ar" ? "rtl" : "ltr"} className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden w-40 -translate-x-1/2 rounded-lg bg-slate-900 px-3 py-2 text-xs text-white shadow-lg group-hover:block">
                  <p className="font-semibold">{dayLabel(d.day, { weekday: "short", month: "short", day: "numeric" })}</p>
                  {SEVERITY_ORDER.map((s) => (
                    <p key={s} className="mt-0.5 flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5">
                        <span className={`h-2 w-2 rounded-sm ${SEVERITY_STYLES[s].bar}`} />
                        {severityLabel(s)}
                      </span>
                      <span className="tabular-nums">{d[s]}</span>
                    </p>
                  ))}
                  <p className="mt-1 flex justify-between border-t border-white/20 pt-1 font-medium">
                    <span>{t.total}</span>
                    <span className="tabular-nums">{totals[i]}</span>
                  </p>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-2 flex text-xs text-slate-400" aria-hidden>
            {days.map((d, i) => (
              <span key={d.day} className="flex-1 text-center whitespace-nowrap">
                {i % labelEvery === 0 ? dayLabel(d.day) : ""}
              </span>
            ))}
          </div>
        </div>
      </div>
      <details className="mt-4 text-sm">
        <summary className="cursor-pointer text-xs font-medium text-slate-500 hover:text-slate-700">{t.showTable}</summary>
        <div className="mt-2 max-h-64 overflow-auto">
          <table className="min-w-full text-xs">
            <thead>
              <tr className="text-start text-slate-500">
                <th className="py-1 pe-4 font-medium">{t.day}</th>
                {SEVERITY_ORDER.map((s) => <th key={s} className="py-1 pe-4 text-end font-medium">{severityLabel(s)}</th>)}
                <th className="py-1 text-end font-medium">{t.total}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 tabular-nums text-slate-700">
              {days.map((d, i) => (
                <tr key={d.day}>
                  <td className="py-1 pe-4">{dayLabel(d.day, { weekday: "short", month: "short", day: "numeric" })}</td>
                  {SEVERITY_ORDER.map((s) => <td key={s} className="py-1 pe-4 text-end">{d[s]}</td>)}
                  <td className="py-1 text-end font-medium">{totals[i]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

function Heatmap({ data }: { data: Data }) {
  const t = useText(TEXT);
  const WEEKDAYS = dayNames();
  const counts = new Map(data.heatmap.map((c) => [`${c.weekday}-${c.hour}`, c.count]));
  const max = Math.max(1, ...data.heatmap.map((c) => c.count));
  const color = (n: number) => (n ? HEAT_STEPS[Math.min(HEAT_STEPS.length - 1, Math.floor((n / max) * (HEAT_STEPS.length - 1e-9)))] : "#f1f5f9");
  const busiest = data.heatmap.reduce((a, b) => (b.count > a.count ? b : a), { weekday: 0, hour: 0, count: 0 });
  const hourLabel = (h: number) => `${String(h).padStart(2, "0")}:00`;

  return (
    <div>
      <div className="overflow-x-auto" dir="ltr">
        <div className="min-w-[36rem]">
          <div className="grid gap-[2px]" style={{ gridTemplateColumns: "2.5rem repeat(24, minmax(0, 1fr))" }} role="img"
            aria-label={t.byWeekdayHour(busiest.count ? `${WEEKDAYS[busiest.weekday - 1]} ${hourLabel(busiest.hour)}` : t.none)}>
            {WEEKDAYS.map((w, wi) => (
              <div key={w} className="contents">
                <span className="truncate pe-2 text-end text-[11px] leading-6 text-slate-400">{w}</span>
                {Array.from({ length: 24 }, (_, h) => {
                  const n = counts.get(`${wi + 1}-${h}`) ?? 0;
                  return (
                    <div key={h} className="group relative h-6 rounded-[3px]" style={{ background: color(n) }}>
                      <span className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden -translate-x-1/2 rounded bg-slate-900 px-2 py-1 text-xs whitespace-nowrap text-white group-hover:block">
                        {w} {hourLabel(h)}–{hourLabel((h + 1) % 24)}: {t.incidents(n)}
                      </span>
                    </div>
                  );
                })}
              </div>
            ))}
            <span />
            {Array.from({ length: 24 }, (_, h) => (
              <span key={h} className="pt-1 text-center text-[10px] text-slate-400">{h % 3 === 0 ? h : ""}</span>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
        <span>
          {busiest.count
            ? <>{t.busiest}<span className="font-medium text-slate-700">{WEEKDAYS[busiest.weekday - 1]} {hourLabel(busiest.hour)}</span> ({busiest.count})</>
            : t.noIncidents}
          {t.timesIn(data.tz.replace(/_/g, " "))}
        </span>
        <span className="flex items-center gap-1" aria-hidden>
          {t.fewer}
          {HEAT_STEPS.map((c) => <span key={c} className="h-3 w-3 rounded-[2px]" style={{ background: c }} />)}
          {t.more}
        </span>
      </div>
    </div>
  );
}

function Breakdown({ items, label = (k: string) => k, empty }: {
  items: { key: string; count: number }[];
  label?: (key: string) => string;
  empty?: string;
}) {
  const t = useText(TEXT);
  if (!items.length) return <EmptyState title={empty ?? t.noIncidents} />;
  return <BarList items={items.slice(0, 8).map((i) => ({ key: i.key, label: label(i.key), value: i.count }))} colorFor={() => "bg-[#2a78d6]"} />;
}

function formatMinutes(m: number | null, units: { s: string; min: string; h: string }) {
  if (m === null) return "—";
  if (m < 1) return `${Math.round(m * 60)} ${units.s}`;
  if (m < 60) return `${m.toFixed(m < 10 ? 1 : 0)} ${units.min}`;
  return `${(m / 60).toFixed(1)} ${units.h}`;
}

export function Analytics() {
  const [params, setParams] = useSearchParams();
  const days = PERIODS.includes(Number(params.get("days"))) ? Number(params.get("days")) : 30;
  const analytics = useAnalytics(days);
  const t = useText(TEXT);

  const picker = (
    <div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5 text-sm" role="group" aria-label={t.timePeriod}>
      {PERIODS.map((p) => (
        <button
          key={p}
          onClick={() => setParams(p === 30 ? {} : { days: String(p) })}
          aria-pressed={days === p}
          className={`rounded-md px-3 py-1.5 ${days === p ? "bg-slate-900 text-white" : "text-slate-600 hover:text-slate-900"}`}
        >
          {t.days(p)}
        </button>
      ))}
    </div>
  );

  return (
    <>
      <PageHeader title={t.title} subtitle={t.subtitle} actions={picker} />
      {analytics.isPending ? (
        <Spinner />
      ) : analytics.isError ? (
        <ErrorState error={analytics.error} onRetry={() => analytics.refetch()} />
      ) : (
        <AnalyticsBody data={analytics.data} dim={analytics.isPlaceholderData} />
      )}
    </>
  );
}

function AnalyticsBody({ data, dim }: { data: Data; dim: boolean }) {
  const change = data.previous_total ? (data.total - data.previous_total) / data.previous_total : null;
  const handled = data.by_status.acknowledged + data.by_status.resolved;
  const top = data.by_type[0];
  const t = useText(TEXT);
  const plugin = usePluginText();

  return (
    <div className={dim ? "opacity-60 transition" : "transition"}>
      <div className="mb-4 grid grid-cols-2 gap-x-8 gap-y-8 lg:grid-cols-4">
        <StatTile
          label={t.tiles.incidents}
          value={data.total.toLocaleString(LOCALES[currentLang()])}
          hint={change === null ? t.tiles.lastDays(data.days) : t.tiles.vsPrevious(data.days)}
          delta={change === null ? undefined : { text: `${Math.abs(change * 100).toFixed(0)}%`, up: change > 0, good: change <= 0 }}
        />
        <StatTile label={t.tiles.handled} value={data.total ? `${Math.round((handled / data.total) * 100)}%` : "—"}
          hint={t.tiles.handledHint(handled)} />
        <StatTile label={t.tiles.median} value={formatMinutes(data.median_minutes_to_handle, t.units)} hint={t.tiles.medianHint} />
        <StatTile label={t.tiles.common} value={top ? eventTypeLabel(top.key) : "—"} hint={top ? t.incidents(top.count) : undefined} />
      </div>

      <Card title={t.perDay} className="mt-6">
        <DailyChart data={data} />
      </Card>

      <Card title={t.when} className="mt-6">
        <Heatmap data={data} />
      </Card>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title={t.byZone}>
          <Breakdown items={data.by_zone} label={(zone) => (zone === "No zone" ? t.noZone : (plugin.location(zone) ?? t.noZone))} />
        </Card>
        <Card title={t.byType}>
          <Breakdown items={data.by_type} label={eventTypeLabel} />
        </Card>
        <Card title={t.missingPpe}>
          <Breakdown items={data.missing_equipment} label={itemLabel} empty={t.noPpe} />
        </Card>
        <Card title={t.byCamera}>
          <Breakdown items={data.by_camera} />
        </Card>
      </div>
    </div>
  );
}
