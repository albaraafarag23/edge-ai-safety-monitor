import { ArrowRight, Camera as CameraIcon, ShieldCheck, Siren } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useCameras, useIncidents, useStats } from "../api/queries";
import type { Incident, Stats } from "../api/types";
import { CameraFeed } from "../components/CameraFeed";
import { BarList, Card, CountUp, EmptyState, ErrorState, Spinner, StatCard, StatusBadge } from "../components/ui";
import { useAuth } from "../lib/auth";
import { SEVERITY_ORDER, SEVERITY_STYLES, formatDuration, humanize, timeAgo } from "../lib/format";
import { useLive } from "../lib/live";

const PERIODS = [
  { hours: 24, label: "24 hours" },
  { hours: 24 * 7, label: "7 days" },
  { hours: 24 * 30, label: "30 days" },
];

function greeting(hour: number) {
  if (hour < 5) return "Working late";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

/** Incidents per hour (up to 48 h) or per day, with empty periods filled in. */
function Timeline({ stats }: { stats: Stats }) {
  const byDay = stats.hours > 48;
  const step = (byDay ? 24 : 1) * 3_600_000;
  const now = Date.now();
  const start = Math.floor((now - stats.hours * 3_600_000) / step) * step;
  const buckets = new Map<number, number>();
  for (let t = start; t <= now; t += step) buckets.set(t, 0);
  for (const { hour, count } of stats.timeline) {
    const t = Math.floor(new Date(hour).getTime() / step) * step;
    if (buckets.has(t)) buckets.set(t, (buckets.get(t) ?? 0) + count);
  }
  const data = [...buckets.entries()];
  const max = Math.max(1, ...data.map(([, c]) => c));
  const label = (t: number) =>
    new Date(t).toLocaleString(undefined, byDay ? { month: "short", day: "numeric" } : { hour: "2-digit", minute: "2-digit" });

  return (
    <div>
      <div className="flex h-44 items-end gap-[3px]" role="img" aria-label={`Incidents per ${byDay ? "day" : "hour"}`}>
        {data.map(([t, count], i) => {
          const current = i === data.length - 1;
          return (
            <div key={t} className="group relative flex h-full flex-1 items-end">
              <div
                className={`w-full rounded-t-sm transition-[height] duration-700 ${
                  count ? (current ? "bg-amber-500" : "bg-ink group-hover:bg-amber-500") : "bg-ink/[0.06]"
                }`}
                style={{ height: count ? `${Math.max(4, (count / max) * 100)}%` : "3px" }}
              />
              <span className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden -translate-x-1/2 rounded bg-ink px-2 py-1 text-xs whitespace-nowrap text-paper group-hover:block">
                {label(t)}: {count}
              </span>
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex justify-between text-xs text-ink/40">
        <span>{label(data[0]?.[0] ?? now)}</span>
        <span className="font-medium text-amber-700">Now</span>
      </div>
    </div>
  );
}

/** Dark band at the top: greeting, the site's state in one sentence, a clock, and the live camera. */
function ControlRoom({ stats, hoursLabel }: { stats: Stats | undefined; hoursLabel: string }) {
  const { user } = useAuth();
  const { connection } = useLive();
  const cameras = useCameras();
  const now = useClock();
  const camera = cameras.data?.find((c) => c.online) ?? cameras.data?.[0];
  const online = cameras.data?.filter((c) => c.online).length ?? 0;
  const open = stats?.open ?? 0;
  const critical = stats?.by_severity.CRITICAL ?? 0;
  const firstName = user?.name.split(" ")[0] ?? "";

  return (
    <section className="relative -mx-4 -mt-8 overflow-hidden bg-ink text-paper sm:-mx-6 lg:-mx-10">
      <img
        src="/edition/console-1200.webp"
        srcSet="/edition/console-1200.webp 1200w, /edition/console-2400.webp 2400w"
        sizes="(min-width: 1024px) calc(100vw - 16rem), 100vw"
        alt=""
        className="page-photo absolute inset-0 h-full w-full object-cover"
        aria-hidden
      />
      <div className="absolute inset-0 bg-gradient-to-r from-ink/95 via-ink/65 to-ink/10" aria-hidden />
      <div className="relative grid gap-10 px-4 pt-10 pb-24 sm:px-6 lg:px-10 xl:grid-cols-[1fr_1.1fr] xl:items-center xl:pt-14">
        <div>
          <p className="mb-3 font-serif text-xl text-amber-300 italic">I</p>
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-paper/60">
            <span className="tabular-nums">
              {now.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })} ·{" "}
              {now.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="relative flex h-2 w-2">
                {connection === "live" && <span className="radar absolute inset-0 rounded-full bg-emerald-400" />}
                <span className={`relative h-2 w-2 rounded-full ${connection === "live" ? "bg-emerald-400" : "bg-amber-400"}`} />
              </span>
              {connection === "live" ? "Watching live" : "Reconnecting…"}
            </span>
          </p>
          <h1 className="mt-4 font-serif text-4xl leading-tight sm:text-5xl">
            {greeting(now.getHours())}
            {firstName && <span className="text-amber-400 italic">, {firstName}</span>}.
          </h1>
          <p className="mt-4 max-w-2xl font-display text-[clamp(2.2rem,4.2vw,4.25rem)] leading-[0.95] font-semibold tracking-[-0.04em] text-balance">
            {open === 0 ? (
              <>All clear. Nothing waiting for you in the last {hoursLabel}.</>
            ) : (
              <>
                <span className={critical ? "text-red-400" : "text-amber-400"}>
                  <CountUp value={open} /> {open === 1 ? "incident needs" : "incidents need"}
                </span>{" "}
                your attention
                {critical ? (
                  <>
                    , <CountUp value={critical} /> critical
                  </>
                ) : null}
                .
              </>
            )}
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            {open > 0 ? (
              <Link
                to="/app/incidents?status=open"
                className="inline-flex items-center gap-2 rounded-full bg-amber-400 px-5 py-2.5 text-sm font-semibold text-ink hover:bg-amber-300"
              >
                <Siren className="h-4 w-4" /> Review open incidents <ArrowRight className="h-4 w-4" />
              </Link>
            ) : (
              <span className="inline-flex items-center gap-2 rounded-full bg-emerald-400/15 px-5 py-2.5 text-sm font-semibold text-emerald-300">
                <ShieldCheck className="h-4 w-4" /> Site is clear
              </span>
            )}
            <Link
              to="/app/cameras"
              className="inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold text-paper ring-1 ring-paper/25 hover:bg-white/10"
            >
              <CameraIcon className="h-4 w-4" /> {online} of {cameras.data?.length ?? 0} cameras live
            </Link>
          </div>
        </div>
        <figure>
          {cameras.isPending ? (
            <Spinner />
          ) : camera ? (
            <Link to={`/app/cameras?camera=${encodeURIComponent(camera.camera_id)}`} className="block">
              <CameraFeed camera={camera} showFullscreen={false} className="shadow-2xl shadow-black/60 ring-white/10" />
            </Link>
          ) : (
            <div className="flex aspect-video items-center justify-center rounded-xl bg-black/40 text-sm text-paper/60 ring-1 ring-white/10">
              No cameras connected yet
            </div>
          )}
          {camera && (
            <figcaption className="mt-3 font-serif text-lg text-paper/70 italic">
              What {camera.camera_id}
              {camera.location ? ` at ${camera.location}` : ""} sees right now, with every detection boxed.
            </figcaption>
          )}
        </figure>
      </div>
    </section>
  );
}

/** Latest incidents as a live feed: new ones slide in at the top. */
function LiveFeed({ incidents }: { incidents: Incident[] }) {
  return (
    <ol className="-mx-5 -my-5 divide-y divide-ink/[0.07]">
      {incidents.map((i, n) => (
        <li key={i.event_id} className="feed-in" style={{ animationDelay: `${n * 50}ms` }}>
          <Link to={`/app/incidents/${i.event_id}`} className="group flex items-center gap-4 px-5 py-3.5 hover:bg-paper/60">
            <span className={`h-10 w-1 shrink-0 rounded-full ${SEVERITY_STYLES[i.severity]?.bar ?? "bg-ink/30"}`} aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="truncate font-display font-semibold text-ink group-hover:text-amber-700">{humanize(i.event_type)}</p>
              <p className="truncate text-xs text-ink/50">
                <span className="sm:hidden">{timeAgo(i.received_at)} · </span>
                {i.severity.charAt(0) + i.severity.slice(1).toLowerCase()} · {i.camera_id}
                {i.location !== "NOT SPECIFIED" ? ` · ${i.location}` : ""} · lasted {formatDuration(i.duration_seconds)}
              </p>
            </div>
            <StatusBadge status={i.status} />
            <span className="hidden w-24 shrink-0 text-right text-xs text-ink/45 tabular-nums sm:block">{timeAgo(i.received_at)}</span>
          </Link>
        </li>
      ))}
    </ol>
  );
}

export function Overview() {
  const [params, setParams] = useSearchParams();
  const hours = Number(params.get("hours")) || 24;
  const hoursLabel = PERIODS.find((p) => p.hours === hours)?.label ?? `${hours} hours`;
  const stats = useStats(hours);
  const latest = useIncidents({ limit: 8 });

  return (
    <>
      <ControlRoom stats={stats.data} hoursLabel={hoursLabel} />

      <div className="paper-grain relative z-10 -mx-4 -mt-10 mb-8 flex flex-wrap items-end justify-between gap-4 rounded-t-[2rem] bg-paper px-4 pt-9 sm:-mx-6 sm:px-6 lg:-mx-10 lg:px-10">
        <h2 className="font-serif text-4xl tracking-tight sm:text-5xl">
          <span className="text-[1.3em] leading-none text-amber-600 italic">T</span>he last {hoursLabel}
        </h2>
        <div className="inline-flex rounded-full bg-white p-1 text-sm ring-1 ring-ink/10" role="group" aria-label="Time period">
          {PERIODS.map((p) => (
            <button
              key={p.hours}
              onClick={() => setParams(p.hours === 24 ? {} : { hours: String(p.hours) })}
              aria-pressed={hours === p.hours}
              className={`rounded-full px-3.5 py-1.5 font-medium ${hours === p.hours ? "bg-ink text-paper" : "text-ink/60 hover:text-ink"}`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {stats.isPending ? (
        <Spinner />
      ) : stats.isError ? (
        <ErrorState error={stats.error} onRetry={() => stats.refetch()} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-x-8 gap-y-8 lg:grid-cols-4">
            <StatCard label="Incidents" value={stats.data.total} hint={`Last ${hoursLabel}`} />
            <StatCard label="Open" value={stats.data.open} hint="Not yet acknowledged" accent="bg-sky-500" />
            <StatCard label="Critical" value={stats.data.by_severity.CRITICAL ?? 0} accent={SEVERITY_STYLES.CRITICAL.bar} />
            <StatCard label="High" value={stats.data.by_severity.HIGH ?? 0} accent={SEVERITY_STYLES.HIGH.bar} />
          </div>

          <div className="mt-12 grid grid-cols-1 gap-6 lg:grid-cols-3">
            <Card
              title={
                <span className="flex items-center gap-2">
                  <span className="relative flex h-2 w-2">
                    <span className="radar absolute inset-0 rounded-full bg-red-500" />
                    <span className="relative h-2 w-2 rounded-full bg-red-500" />
                  </span>
                  Live feed
                </span>
              }
              className="min-w-0 lg:col-span-2"
              action={<Link to="/app/incidents" className="text-sm font-medium text-amber-700 hover:underline">View all</Link>}
            >
              {latest.isPending ? (
                <Spinner />
              ) : latest.isError ? (
                <ErrorState error={latest.error} />
              ) : latest.data.items.length ? (
                <LiveFeed incidents={latest.data.items} />
              ) : (
                <EmptyState title="No incidents yet">New incidents appear here as soon as they're detected.</EmptyState>
              )}
            </Card>
            <div className="space-y-6">
              <Card title="By severity">
                {stats.data.total ? (
                  <BarList
                    items={SEVERITY_ORDER.map((s) => ({ key: s, label: humanize(s), value: stats.data.by_severity[s] ?? 0 }))}
                    colorFor={(s) => SEVERITY_STYLES[s as keyof typeof SEVERITY_STYLES].bar}
                  />
                ) : (
                  <EmptyState title="No incidents in this period" />
                )}
              </Card>
              <Card title="By type">
                {Object.keys(stats.data.by_event_type).length ? (
                  <BarList
                    items={Object.entries(stats.data.by_event_type)
                      .sort((a, b) => b[1] - a[1])
                      .map(([k, v]) => ({ key: k, label: humanize(k), value: v }))}
                  />
                ) : (
                  <EmptyState title="No incidents in this period" />
                )}
              </Card>
            </div>
          </div>

          <Card title="Incidents over time" className="mt-8">
            <Timeline stats={stats.data} />
          </Card>
        </>
      )}
    </>
  );
}
