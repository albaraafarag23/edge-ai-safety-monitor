import { Link, NavLink, Outlet } from "react-router-dom";
import { humanize } from "../lib/format";
import { useLive } from "../lib/live";
import { SeverityBadge } from "./ui";

const NAV = [
  { to: "/", label: "Overview", end: true },
  { to: "/incidents", label: "Incidents", end: false },
];

function LiveIndicator() {
  const { connection } = useLive();
  const styles = {
    live: ["bg-emerald-500", "Live"],
    connecting: ["bg-amber-400", "Connecting…"],
    offline: ["bg-red-500", "Offline"],
  } as const;
  const [color, label] = styles[connection];
  return (
    <span className="flex items-center gap-2 text-xs text-slate-400" aria-live="polite">
      <span className="relative flex h-2 w-2">
        {connection === "live" && <span className={`absolute h-2 w-2 animate-ping rounded-full ${color} opacity-60`} />}
        <span className={`relative h-2 w-2 rounded-full ${color}`} />
      </span>
      {label}
    </span>
  );
}

function Toasts() {
  const { toasts, dismiss } = useLive();
  return (
    <div className="pointer-events-none fixed right-4 bottom-4 z-50 flex w-80 flex-col gap-2" aria-live="assertive">
      {toasts.map(({ id, incident }) => (
        <div key={id} className="pointer-events-auto rounded-lg border border-slate-200 bg-white p-4 shadow-lg">
          <div className="flex items-start justify-between gap-2">
            <SeverityBadge severity={incident.severity} />
            <button onClick={() => dismiss(id)} className="text-slate-400 hover:text-slate-600" aria-label="Dismiss">
              ×
            </button>
          </div>
          <p className="mt-2 text-sm font-medium text-slate-900">{humanize(incident.event_type)}</p>
          <p className="text-xs text-slate-500">
            {incident.camera_id}
            {incident.location !== "NOT SPECIFIED" ? ` · ${incident.location}` : ""}
          </p>
          <Link
            to={`/incidents/${incident.event_id}`}
            onClick={() => dismiss(id)}
            className="mt-2 inline-block text-xs font-medium text-sky-700 hover:underline"
          >
            View incident →
          </Link>
        </div>
      ))}
    </div>
  );
}

export function Layout() {
  return (
    <div className="min-h-screen bg-slate-50 md:flex">
      <aside className="bg-slate-900 text-slate-300 md:fixed md:inset-y-0 md:w-60">
        <div className="flex items-center gap-2 px-5 py-5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-500 text-slate-900" aria-hidden>
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
              <path d="M12 2 2 21h20L12 2zm0 6 1 7h-2l1-7zm0 9a1.2 1.2 0 1 1 0 2.4A1.2 1.2 0 0 1 12 17z" />
            </svg>
          </span>
          <div>
            <p className="text-sm font-semibold text-white">Safety Monitor</p>
            <p className="text-xs text-slate-400">Construction site</p>
          </div>
        </div>
        <nav className="flex gap-1 px-3 pb-3 md:flex-col">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm font-medium ${
                  isActive ? "bg-slate-800 text-white" : "hover:bg-slate-800/60 hover:text-white"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="hidden px-5 py-4 md:absolute md:bottom-0 md:block">
          <LiveIndicator />
        </div>
      </aside>
      <main className="flex-1 md:ml-60">
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
          <Outlet />
        </div>
      </main>
      <Toasts />
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}
