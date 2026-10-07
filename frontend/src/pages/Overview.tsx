import { Link, useSearchParams } from "react-router-dom";
import { useCameras, useIncidents, useStats } from "../api/queries";
import type { Stats } from "../api/types";
import { CameraFeed } from "../components/CameraFeed";
import { IncidentTable } from "../components/IncidentTable";
import { PageHeader } from "../components/Layout";
import { BarList, Card, EmptyState, ErrorState, Spinner, StatCard } from "../components/ui";
import { SEVERITY_ORDER, SEVERITY_STYLES, humanize } from "../lib/format";

const PERIODS = [
  { hours: 24, label: "24 hours" },
  { hours: 24 * 7, label: "7 days" },
  { hours: 24 * 30, label: "30 days" },
];

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
      <div className="flex h-40 items-end gap-[2px]" role="img" aria-label={`Incidents per ${byDay ? "day" : "hour"}`}>
        {data.map(([t, count]) => (
          <div key={t} className="group relative flex h-full flex-1 items-end">
            <div
              className={`w-full rounded-t ${count ? "bg-slate-700 group-hover:bg-amber-500" : "bg-slate-100"}`}
              style={{ height: count ? `${Math.max(4, (count / max) * 100)}%` : "4px" }}
            />
            <span className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden -translate-x-1/2 whitespace-nowrap rounded bg-slate-900 px-2 py-1 text-xs text-white group-hover:block">
              {label(t)}: {count}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-2 flex justify-between text-xs text-slate-400">
        <span>{label(data[0]?.[0] ?? now)}</span>
        <span>Now</span>
      </div>
    </div>
  );
}

function LiveCameraCard() {
  const cameras = useCameras();
  const camera = cameras.data?.find((c) => c.online) ?? cameras.data?.[0];
  return (
    <Card
      title="Live view"
      action={<Link to="/app/cameras" className="text-sm font-medium text-sky-700 hover:underline">All cameras</Link>}
    >
      {cameras.isPending ? (
        <Spinner />
      ) : cameras.isError ? (
        <ErrorState error={cameras.error} />
      ) : camera ? (
        <Link to={`/app/cameras?camera=${encodeURIComponent(camera.camera_id)}`} className="block">
          <CameraFeed camera={camera} showFullscreen={false} />
        </Link>
      ) : (
        <EmptyState title="No cameras connected">Start the detector to see the live view here.</EmptyState>
      )}
    </Card>
  );
}

export function Overview() {
  const [params, setParams] = useSearchParams();
  const hours = Number(params.get("hours")) || 24;
  const stats = useStats(hours);
  const latest = useIncidents({ limit: 8 });

  const periodPicker = (
    <div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5 text-sm" role="group" aria-label="Time period">
      {PERIODS.map((p) => (
        <button
          key={p.hours}
          onClick={() => setParams(p.hours === 24 ? {} : { hours: String(p.hours) })}
          aria-pressed={hours === p.hours}
          className={`rounded-md px-3 py-1.5 ${hours === p.hours ? "bg-slate-900 text-white" : "text-slate-600 hover:text-slate-900"}`}
        >
          {p.label}
        </button>
      ))}
    </div>
  );

  return (
    <>
      <PageHeader title="Overview" subtitle="Safety status across all cameras on site" actions={periodPicker} />

      {stats.isPending ? (
        <Spinner />
      ) : stats.isError ? (
        <ErrorState error={stats.error} onRetry={() => stats.refetch()} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Incidents" value={stats.data.total} hint={`Last ${PERIODS.find((p) => p.hours === hours)?.label ?? `${hours} h`}`} />
            <StatCard label="Open" value={stats.data.open} hint="Not yet acknowledged" accent="bg-sky-500" />
            <StatCard label="Critical" value={stats.data.by_severity.CRITICAL ?? 0} accent={SEVERITY_STYLES.CRITICAL.bar} />
            <StatCard label="High" value={stats.data.by_severity.HIGH ?? 0} accent={SEVERITY_STYLES.HIGH.bar} />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <LiveCameraCard />
            </div>
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
          </div>

          <Card title="Incidents over time" className="mt-6">
            <Timeline stats={stats.data} />
          </Card>

          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            <Card
              title="Latest incidents"
              className="lg:col-span-2"
              action={<Link to="/app/incidents" className="text-sm font-medium text-sky-700 hover:underline">View all</Link>}
            >
              {latest.isPending ? (
                <Spinner />
              ) : latest.isError ? (
                <ErrorState error={latest.error} />
              ) : latest.data.items.length ? (
                <IncidentTable incidents={latest.data.items} compact />
              ) : (
                <EmptyState title="No incidents yet">New incidents appear here as soon as they're detected.</EmptyState>
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
        </>
      )}
    </>
  );
}
