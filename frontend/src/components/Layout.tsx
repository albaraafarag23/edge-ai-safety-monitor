import { BarChart3, Bell, Camera, ChevronDown, LayoutDashboard, ListChecks, LogOut, ShieldCheck, UserCog, Users } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useIncidents } from "../api/queries";
import { useAuth } from "../lib/auth";
import { SEVERITY_STYLES, timeAgo } from "../lib/format";
import { bilingual, LanguageSwitch, useText } from "../lib/i18n";
import { LiveProvider, useLive } from "../lib/live";
import { isUnread, useNotificationPrefs } from "../lib/notifications";
import { incidentTitle, roleLabel, severityLabel, usePluginText } from "../lib/terms";
import { Logo } from "./Brand";
import { SeverityBadge } from "./ui";

const TEXT = bilingual(
  {
    nav: {
      overview: "Overview",
      cameras: "Live cameras",
      incidents: "Incidents",
      analytics: "Analytics",
      notifications: "Notifications",
      rules: "Safety rules",
      users: "Users",
    },
    connection: { live: "Connected", connecting: "Connecting…", offline: "Offline" },
    dismiss: "Dismiss",
    viewIncident: "View incident",
    notifications: "Notifications",
    unread: (n: number) => `, ${n} unread`,
    markAllRead: "Mark all as read",
    noAlerts: "No alerts yet",
    allNotifications: "All notifications and settings",
    account: "Account and password",
    signOut: "Sign out",
    consoleName: "Site safety console",
    monitoring: "Monitoring",
    pluginName: "Construction safety",
  },
  {
    nav: {
      overview: "نظرة عامة",
      cameras: "الكاميرات المباشرة",
      incidents: "الحوادث",
      analytics: "التحليلات",
      notifications: "الإشعارات",
      rules: "قواعد السلامة",
      users: "المستخدمون",
    },
    connection: { live: "متصل", connecting: "جارٍ الاتصال…", offline: "غير متصل" },
    dismiss: "إغلاق",
    viewIncident: "عرض الحادثة",
    notifications: "الإشعارات",
    unread: (n: number) => `، ${n} غير مقروءة`,
    markAllRead: "تحديد الكل كمقروء",
    noAlerts: "لا توجد تنبيهات بعد",
    allNotifications: "كل الإشعارات والإعدادات",
    account: "الحساب وكلمة المرور",
    signOut: "تسجيل الخروج",
    consoleName: "لوحة تحكم سلامة الموقع",
    monitoring: "المراقبة",
    pluginName: "سلامة مواقع البناء",
  },
);
type NavKey = keyof typeof TEXT.en.nav;

// Each console page is a numbered "chapter" with its own opener photo (public/edition), like the product page.
const NAV = [
  { to: "/app", key: "overview" as NavKey, icon: LayoutDashboard, end: true, photo: "console" },
  { to: "/app/cameras", key: "cameras" as NavKey, icon: Camera, end: false, photo: "ppe" },
  { to: "/app/incidents", key: "incidents" as NavKey, icon: ListChecks, end: false, photo: "alerts" },
  { to: "/app/analytics", key: "analytics" as NavKey, icon: BarChart3, end: false, photo: "rules" },
  { to: "/app/notifications", key: "notifications" as NavKey, icon: Bell, end: false, photo: "closing" },
  { to: "/app/rules", key: "rules" as NavKey, icon: ShieldCheck, end: false, photo: "zones" },
];
const ADMIN_NAV = [{ to: "/app/users", key: "users" as NavKey, icon: Users, end: false, photo: "how" }];
const OTHER_PAGES: Record<string, string> = { "/app/account": "hero" };

function useNav() {
  const { user } = useAuth();
  const t = useText(TEXT);
  return (user?.role === "admin" ? [...NAV, ...ADMIN_NAV] : NAV).map((n) => ({ ...n, label: t.nav[n.key] }));
}

function LiveIndicator() {
  const { connection } = useLive();
  const t = useText(TEXT);
  const color = { live: "bg-emerald-500", connecting: "bg-amber-400", offline: "bg-red-500" }[connection];
  const label = t.connection[connection];
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
  const t = useText(TEXT);
  const plugin = usePluginText();
  return (
    <div className="pointer-events-none fixed end-4 bottom-4 z-50 flex w-80 flex-col gap-2" aria-live="assertive">
      {toasts.map(({ id, incident }) => (
        <div key={id} className="pointer-events-auto rounded-xl border border-slate-200 bg-white p-4 shadow-xl shadow-slate-900/10">
          <div className="flex items-start justify-between gap-2">
            <SeverityBadge severity={incident.severity} />
            <button onClick={() => dismiss(id)} className="text-slate-400 hover:text-slate-600" aria-label={t.dismiss}>
              ×
            </button>
          </div>
          <p className="mt-2 text-sm font-medium text-slate-900">{incidentTitle(incident)}</p>
          <p className="text-xs text-slate-500">
            {incident.camera_id}
            {plugin.location(incident.location, incident.metadata?.zone_id) ? ` · ${plugin.location(incident.location, incident.metadata?.zone_id)}` : ""}
          </p>
          <Link
            to={`/app/incidents/${incident.event_id}`}
            onClick={() => dismiss(id)}
            className="mt-2 inline-block text-xs font-medium text-sky-700 hover:underline"
          >
            {t.viewIncident} <span className="flip-rtl inline-block">→</span>
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
  const t = useText(TEXT);
  const plugin = usePluginText();

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
        aria-label={`${t.notifications}${unread ? t.unread(unread) : ""}`}
        aria-expanded={open}
      >
        <Bell className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute top-1 end-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">
            {unread >= items.length && items.length >= 8 ? "8+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute end-0 z-40 mt-2 w-[22rem] max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl shadow-slate-900/10">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <p className="text-sm font-semibold text-slate-900">{t.notifications}</p>
            {unread > 0 && (
              <button onClick={markRead} className="text-xs font-medium text-sky-700 hover:underline">
                {t.markAllRead}
              </button>
            )}
          </div>
          <ul className="max-h-96 divide-y divide-slate-100 overflow-y-auto">
            {items.length === 0 && <li className="px-4 py-8 text-center text-sm text-slate-500">{t.noAlerts}</li>}
            {items.map((i) => (
              <li key={i.event_id}>
                <Link
                  to={`/app/incidents/${i.event_id}`}
                  onClick={() => setOpen(false)}
                  className={`flex gap-3 px-4 py-3 hover:bg-slate-50 ${isUnread(i, prefs.lastSeen) ? "bg-sky-50/60" : ""}`}
                >
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${SEVERITY_STYLES[i.severity]?.dot ?? "bg-slate-400"}`} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-slate-900">{incidentTitle(i)}</span>
                    <span className="block truncate text-xs text-slate-500">
                      {severityLabel(i.severity)} · {i.camera_id}
                      {plugin.location(i.location, i.metadata?.zone_id) ? ` · ${plugin.location(i.location, i.metadata?.zone_id)}` : ""}
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
            {t.allNotifications}
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
  const t = useText(TEXT);
  if (!user) return null;
  const initials = user.name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 rounded-lg py-1 pe-2 ps-1 hover:bg-slate-100"
        aria-expanded={open}
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-900 text-xs font-semibold text-white">
          {initials}
        </span>
        <span className="hidden text-start leading-tight sm:block">
          <span className="block text-sm font-medium text-slate-900">{user.name}</span>
          <span className="block text-xs text-slate-500">{roleLabel(user.role)}</span>
        </span>
        <ChevronDown className="h-4 w-4 text-slate-400" />
      </button>
      {open && (
        <div className="absolute end-0 z-40 mt-2 w-60 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl shadow-slate-900/10">
          <div className="border-b border-slate-100 px-4 py-3">
            <p className="text-sm font-medium text-slate-900">{user.name}</p>
            <p className="truncate text-xs text-slate-500">{user.email}</p>
          </div>
          <Link
            to="/app/account"
            onClick={() => setOpen(false)}
            className="flex w-full items-center gap-2 px-4 py-2.5 text-start text-sm text-slate-700 hover:bg-slate-50"
          >
            <UserCog className="h-4 w-4" /> {t.account}
          </Link>
          <button
            onClick={async () => {
              await logout();
              navigate("/login", { replace: true });
            }}
            className="flex w-full items-center gap-2 px-4 py-2.5 text-start text-sm text-slate-700 hover:bg-slate-50"
          >
            <LogOut className="flip-rtl h-4 w-4" /> {t.signOut}
          </button>
        </div>
      )}
    </div>
  );
}

function SideNav() {
  const nav = useNav();
  const t = useText(TEXT);
  return (
    <aside className="hidden bg-ink text-paper/70 lg:fixed lg:inset-y-0 lg:flex lg:w-64 lg:flex-col">
      <div className="px-5 py-5">
        <Logo to="/app" dark subtitle={t.consoleName} />
      </div>
      {/* the product page's chapter index, without the numerals: name, and a dotted leader on the current page */}
      <nav className="flex flex-1 flex-col justify-end px-5 pb-8">
        <p className="pb-3 font-serif text-lg text-amber-400/90 italic">{t.monitoring}</p>
        <ol className="space-y-1">
          {nav.map(({ to, label, end }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={end}
                className={({ isActive }) =>
                  `group flex items-baseline gap-2 py-0.5 font-display text-[19px] leading-tight font-semibold tracking-tight transition ${
                    isActive ? "text-paper" : "text-paper/40 hover:text-paper/80"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <span className="whitespace-nowrap">{label}</span>
                    <span className={`mb-1 h-px flex-1 border-b border-dotted ${isActive ? "border-amber-400" : "border-transparent"}`} />
                    <span className={`h-1.5 w-1.5 rounded-full ${isActive ? "bg-amber-400" : "bg-transparent"}`} />
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ol>
      </nav>
      <div className="space-y-1 border-t border-white/10 px-5 py-4">
        <p className="font-serif text-base text-paper/80 italic">{t.pluginName}</p>
        <LiveIndicator />
      </div>
    </aside>
  );
}

function TopBar() {
  const nav = useNav();
  return (
    <header className="sticky top-0 z-30 border-b border-ink/10 bg-paper/80 backdrop-blur-md">
      <div className="flex h-16 items-center gap-4 px-4 sm:px-6 lg:px-8">
        <div className="lg:hidden">
          <Logo to="/app" />
        </div>
        <div className="ms-auto flex items-center gap-2">
          <LanguageSwitch className="text-ink/70 ring-1 ring-ink/15 hover:bg-ink/5" />
          <NotificationBell />
          <span className="mx-1 h-6 w-px bg-ink/15" aria-hidden />
          <UserMenu />
        </div>
      </div>
      {/* small screens: nav as a scrollable row under the top bar */}
      <nav className="flex gap-1 overflow-x-auto px-3 pb-2 lg:hidden">
        {nav.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium ${
                isActive ? "bg-ink text-paper" : "text-ink/60 hover:bg-ink/5"
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
      <div className="paper-grain min-h-screen bg-paper font-display text-ink">
        <SideNav />
        <div className="lg:ps-64">
          <TopBar />
          <main className="px-4 py-8 sm:px-6 lg:px-10">
            <Outlet />
          </main>
        </div>
        <Toasts />
      </div>
    </LiveProvider>
  );
}

/**
 * A page opens like a chapter of the product page: a full-width photo with a
 * huge title, then a rounded sheet of paper that overlaps it, carrying the subtitle and the page's actions.
 * `image` replaces the photo (e.g. an incident's own snapshot); `back` is a link shown above the title.
 */
export function PageHeader({ title, subtitle, actions, image, back }: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  image?: string | null;
  back?: ReactNode;
}) {
  const { pathname } = useLocation();
  const nav = useNav();
  const index = nav.findIndex((n) => n.to === pathname);
  const photo = index >= 0 ? nav[index].photo : (OTHER_PAGES[pathname] ?? "alerts");
  const [imageFailed, setImageFailed] = useState(false);
  const useImage = image && !imageFailed;

  return (
    <>
      <div className="relative -mx-4 -mt-8 h-[clamp(260px,40vh,440px)] overflow-hidden bg-ink sm:-mx-6 lg:-mx-10">
        {useImage ? (
          <img src={image} alt="" onError={() => setImageFailed(true)} className="page-photo absolute inset-0 h-full w-full object-cover" />
        ) : (
          <img
            src={`/edition/${photo}-1200.webp`}
            srcSet={`/edition/${photo}-1200.webp 1200w, /edition/${photo}-2400.webp 2400w`}
            sizes="(min-width: 1024px) calc(100vw - 16rem), 100vw"
            alt=""
            className="page-photo absolute inset-0 h-full w-full object-cover"
          />
        )}
        <div className="absolute inset-0 bg-gradient-to-b from-black/45 via-black/20 to-black/70" aria-hidden />
        <div className="relative flex h-full flex-col justify-end px-4 pb-16 sm:px-6 lg:px-10">
          {back && <div className="mb-auto pt-6 text-sm text-paper/75 [&_a:hover]:text-paper">{back}</div>}
          <h1 className="font-display text-[clamp(2.8rem,7.5vw,7rem)] leading-[0.9] font-semibold tracking-[-0.045em] text-balance text-paper">
            {title}
          </h1>
        </div>
      </div>
      <div className="paper-grain relative z-10 -mx-4 -mt-10 mb-8 flex flex-wrap items-end justify-between gap-4 rounded-t-[2rem] bg-paper px-4 pt-8 sm:-mx-6 sm:px-6 lg:-mx-10 lg:px-10">
        {subtitle ? <p className="max-w-3xl font-serif text-2xl leading-snug text-ink/70 sm:text-[1.7rem]">{subtitle}</p> : <span />}
        {actions}
      </div>
    </>
  );
}
