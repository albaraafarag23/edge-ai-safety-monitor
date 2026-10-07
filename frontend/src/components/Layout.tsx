import { Bell, Camera, ChevronDown, LayoutDashboard, ListChecks, LogOut } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useIncidents } from "../api/queries";
import { useAuth } from "../lib/auth";
import { SEVERITY_STYLES, humanize, timeAgo } from "../lib/format";
import { LiveProvider, useLive } from "../lib/live";
import { isUnread, useNotificationPrefs } from "../lib/notifications";
import { Logo } from "./Brand";
import { SeverityBadge } from "./ui";

const NAV = [
  { to: "/app", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/app/cameras", label: "Live cameras", icon: Camera, end: false },
  { to: "/app/incidents", label: "Incidents", icon: ListChecks, end: false },
  { to: "/app/notifications", label: "Notifications", icon: Bell, end: false },
];

function LiveIndicator() {
  const { connection } = useLive();
  const styles = {
    live: ["bg-emerald-500", "Connected"],
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
        <div key={id} className="pointer-events-auto rounded-xl border border-slate-200 bg-white p-4 shadow-xl shadow-slate-900/10">
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
            to={`/app/incidents/${incident.event_id}`}
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

/** Closes a popover on outside click or Escape. */
function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return { open, setOpen, ref };
}

function NotificationBell() {
  const { open, setOpen, ref } = usePopover();
  const [prefs, update] = useNotificationPrefs();
  const recent = useIncidents({ limit: 8 });
  const items = recent.data?.items ?? [];

  // first visit: start counting from now instead of flagging the whole history as unread
  useEffect(() => {
    if (!prefs.lastSeen) update({ lastSeen: new Date().toISOString() });
  }, [prefs.lastSeen, update]);

  const unread = items.filter((i) => isUnread(i, prefs.lastSeen)).length;
  const markRead = () => update({ lastSeen: new Date().toISOString() });

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="relative rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
        aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
        aria-expanded={open}
      >
        <Bell className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute top-1 right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">
            {unread >= items.length && items.length >= 8 ? "8+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-[22rem] max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl shadow-slate-900/10">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <p className="text-sm font-semibold text-slate-900">Notifications</p>
            {unread > 0 && (
              <button onClick={markRead} className="text-xs font-medium text-sky-700 hover:underline">
                Mark all as read
              </button>
            )}
          </div>
          <ul className="max-h-96 divide-y divide-slate-100 overflow-y-auto">
            {items.length === 0 && <li className="px-4 py-8 text-center text-sm text-slate-500">No alerts yet</li>}
            {items.map((i) => (
              <li key={i.event_id}>
                <Link
                  to={`/app/incidents/${i.event_id}`}
                  onClick={() => setOpen(false)}
                  className={`flex gap-3 px-4 py-3 hover:bg-slate-50 ${isUnread(i, prefs.lastSeen) ? "bg-sky-50/60" : ""}`}
                >
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${SEVERITY_STYLES[i.severity]?.dot ?? "bg-slate-400"}`} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-slate-900">{humanize(i.event_type)}</span>
                    <span className="block truncate text-xs text-slate-500">
                      {i.severity} · {i.camera_id}
                      {i.location !== "NOT SPECIFIED" ? ` · ${i.location}` : ""}
                    </span>
                  </span>
                  <span className="shrink-0 text-xs text-slate-400">{timeAgo(i.received_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
          <Link
            to="/app/notifications"
            onClick={() => setOpen(false)}
            className="block border-t border-slate-100 px-4 py-2.5 text-center text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            All notifications and settings
          </Link>
        </div>
      )}
    </div>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { open, setOpen, ref } = usePopover();
  if (!user) return null;
  const initials = user.name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 rounded-lg py-1 pr-2 pl-1 hover:bg-slate-100"
        aria-expanded={open}
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-900 text-xs font-semibold text-white">
          {initials}
        </span>
        <span className="hidden text-left leading-tight sm:block">
          <span className="block text-sm font-medium text-slate-900">{user.name}</span>
          <span className="block text-xs text-slate-500 capitalize">{user.role}</span>
        </span>
        <ChevronDown className="h-4 w-4 text-slate-400" />
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-60 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl shadow-slate-900/10">
          <div className="border-b border-slate-100 px-4 py-3">
            <p className="text-sm font-medium text-slate-900">{user.name}</p>
            <p className="truncate text-xs text-slate-500">{user.email}</p>
          </div>
          <button
            onClick={async () => {
              await logout();
              navigate("/login", { replace: true });
            }}
            className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-50"
          >
            <LogOut className="h-4 w-4" /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function SideNav() {
  return (
    <aside className="hidden bg-slate-950 text-slate-300 lg:fixed lg:inset-y-0 lg:flex lg:w-64 lg:flex-col">
      <div className="px-5 py-5">
        <Logo to="/app" dark subtitle="Site safety console" />
      </div>
      <nav className="flex-1 space-y-1 px-3 py-2">
        <p className="px-3 pb-2 text-[11px] font-semibold tracking-wider text-slate-500 uppercase">Monitoring</p>
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                isActive ? "bg-white/10 text-white" : "text-slate-400 hover:bg-white/5 hover:text-white"
              }`
            }
          >
            <Icon className="h-[18px] w-[18px]" aria-hidden />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="space-y-1 border-t border-white/10 px-5 py-4">
        <p className="text-xs font-medium text-slate-300">Construction safety</p>
        <LiveIndicator />
      </div>
    </aside>
  );
}

function TopBar() {
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/85 backdrop-blur">
      <div className="flex h-16 items-center gap-4 px-4 sm:px-6 lg:px-8">
        <div className="lg:hidden">
          <Logo to="/app" />
        </div>
        <div className="ml-auto flex items-center gap-2">
          <NotificationBell />
          <span className="mx-1 h-6 w-px bg-slate-200" aria-hidden />
          <UserMenu />
        </div>
      </div>
      {/* small screens: nav as a scrollable row under the top bar */}
      <nav className="flex gap-1 overflow-x-auto px-3 pb-2 lg:hidden">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium ${
                isActive ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
              }`
            }
          >
            <Icon className="h-4 w-4" aria-hidden />
            {label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}

/** Signed-in console: side navigation, top bar with notifications and account, live updates. */
export function AppShell() {
  return (
    <LiveProvider>
      <div className="min-h-screen bg-slate-50">
        <SideNav />
        <div className="lg:pl-64">
          <TopBar />
          <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
            <Outlet />
          </main>
        </div>
        <Toasts />
      </div>
    </LiveProvider>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}
