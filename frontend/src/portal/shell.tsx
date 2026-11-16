/** The portal's frame: dark menu at the side (on top on a phone), page header, and shared words. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, ClipboardCheck, HardDrive, Home, KeyRound, LogOut, ScrollText } from "lucide-react";
import type { ReactNode } from "react";
import { Navigate, NavLink, Outlet, useLocation } from "react-router-dom";
import { bilingual, LanguageSwitch, useLang, useText } from "../lib/i18n";
import { ApiError, get, send, type DeviceStatus, type Me, type Role } from "./api";

export const WORDS = bilingual(
  {
    role: { overseer: "Overseer", manager: "Manager", supervisor: "Supervisor", viewer: "Viewer" } as Record<Role, string>,
    device: { pending: "Waiting for approval", approved: "Approved", refused: "Refused", revoked: "Removed" } as Record<DeviceStatus, string>,
  },
  {
    role: { overseer: "المشرف العام", manager: "مدير", supervisor: "مشرف", viewer: "مشاهد" },
    device: { pending: "بانتظار الموافقة", approved: "معتمد", refused: "مرفوض", revoked: "أُزيل" },
  },
);

const TEXT = bilingual(
  {
    portal: "Portal",
    nav: { home: "Overview", companies: "Companies", boxes: "Boxes", approvals: "Approvals", log: "Security log",
           devices: "My devices", myCompany: "My company" },
    allClients: "All clients",
    signOut: "Sign out",
    signedInHere: "Signed in with a passkey",
    menu: "Portal menu",
  },
  {
    portal: "البوابة",
    nav: { home: "نظرة عامة", companies: "الشركات", boxes: "الأجهزة", approvals: "الموافقات", log: "سجل الأمان",
           devices: "أجهزتي", myCompany: "شركتي" },
    allClients: "كل العملاء",
    signOut: "تسجيل الخروج",
    signedInHere: "دخلت بمفتاح المرور",
    menu: "قائمة البوابة",
  },
);

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => get<Me>("/auth/me"),
    retry: (n, err) => !(err instanceof ApiError && err.status === 401) && n < 2,
    staleTime: 60_000,
  });
}

/** Wraps the signed-in screens; anyone not signed in goes to the sign-in screen. */
export function Shell() {
  const me = useMe();
  const t = useText(TEXT);
  const words = useText(WORDS);
  const location = useLocation();
  const qc = useQueryClient();
  const pending = useQuery({
    queryKey: ["approvals"],
    queryFn: () => get<unknown[]>("/approvals"),
    enabled: me.data?.role === "overseer" || me.data?.role === "manager",
    refetchInterval: 60_000,
  });

  if (me.isPending) return <div className="min-h-screen bg-ink" aria-busy="true" />;
  if (me.isError) return <Navigate to="/signin" replace state={{ from: location.pathname + location.search }} />;
  const user = me.data;
  const approver = user.role === "overseer" || user.role === "manager";
  const links: { to: string; label: string; icon: typeof Home; badge?: number }[] = user.role === "overseer"
    ? [
        { to: "/", label: t.nav.home, icon: Home },
        { to: "/companies", label: t.nav.companies, icon: Building2 },
        { to: "/boxes", label: t.nav.boxes, icon: HardDrive },
        { to: "/approvals", label: t.nav.approvals, icon: ClipboardCheck, badge: pending.data?.length },
        { to: "/log", label: t.nav.log, icon: ScrollText },
      ]
    : [
        { to: `/companies/${user.company?.id}`, label: t.nav.myCompany, icon: Building2 },
        ...(approver ? [
          { to: "/approvals", label: t.nav.approvals, icon: ClipboardCheck, badge: pending.data?.length },
          { to: "/log", label: t.nav.log, icon: ScrollText },
        ] : []),
      ];
  links.push({ to: "/devices", label: t.nav.devices, icon: KeyRound });

  const signOut = async () => {
    await send("/auth/signout");
    qc.clear();
    window.location.assign("/signin");
  };

  return (
    <div className="flex min-h-screen flex-col bg-paper text-ink lg:flex-row">
      <nav aria-label={t.menu} className="flex shrink-0 flex-col gap-6 bg-ink px-5 py-5 text-paper lg:sticky lg:top-0 lg:h-screen lg:w-64 lg:py-6">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Logo />
            <div>
              <div className="font-display text-base font-bold">SiteSentry</div>
              <div className="text-xs text-[#b9b2a4]">{t.portal}</div>
            </div>
          </div>
          <LanguageSwitch className="border border-[#3a352c] text-paper hover:bg-[#2a261f]" />
        </div>
        <div className="flex flex-row flex-wrap gap-x-5 gap-y-1 lg:flex-col lg:gap-1">
          {user.role === "overseer" && (
            <div className="mb-1 hidden font-serif text-lg italic text-[#f2b705] lg:block">{t.allClients}</div>
          )}
          {links.map(({ to, label, icon: Icon, badge }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-2.5 py-1.5 font-display text-[17px] font-semibold ${isActive ? "text-white" : "text-[#b9b2a4] hover:text-white"}`}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {label}
              {badge ? (
                <span className="ms-auto rounded-full bg-[#f2b705] px-2 py-0.5 font-sans text-xs font-semibold text-ink">{badge}</span>
              ) : null}
            </NavLink>
          ))}
        </div>
        <div className="mt-auto hidden border-t border-[#2e2a22] pt-4 text-[13px] text-[#b9b2a4] lg:block">
          <div className="font-medium text-paper">{user.name} · {words.role[user.role]}</div>
          {user.company && <div>{user.company.name}</div>}
          <div>{t.signedInHere}</div>
          <button type="button" onClick={signOut} className="mt-2 inline-flex items-center gap-1.5 font-semibold text-[#f2b705] hover:text-[#ffd24d]">
            <LogOut className="h-4 w-4 flip-rtl" aria-hidden="true" /> {t.signOut}
          </button>
        </div>
        <button type="button" onClick={signOut} className="inline-flex items-center gap-1.5 self-start text-sm font-semibold text-[#f2b705] lg:hidden">
          <LogOut className="h-4 w-4 flip-rtl" aria-hidden="true" /> {t.signOut}
        </button>
      </nav>
      <main className="min-w-0 flex-1 px-4 py-8 sm:px-8 lg:px-12 lg:py-10">
        <div className="mx-auto flex max-w-6xl flex-col gap-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

export function Logo({ size = 36 }: { size?: number }) {
  return (
    <div className="flex items-center justify-center rounded-[9px] bg-[#f2b705]" style={{ width: size, height: size }}>
      <svg width={size * 0.56} height={size * 0.56} viewBox="0 0 24 24" fill="none" stroke="#15130f" strokeWidth="2.2"
        strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6l8-3z" />
      </svg>
    </div>
  );
}

export function Header({ kicker, title, lead, back, children }: {
  kicker?: ReactNode; title: ReactNode; lead?: ReactNode; back?: ReactNode; children?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-2.5">
      {back}
      {kicker && <div className="text-xs font-semibold uppercase tracking-[0.08em] text-[#6b6355]">{kicker}</div>}
      <h1 className="font-display text-4xl font-extrabold leading-[1.05] tracking-tight sm:text-5xl">{title}</h1>
      {lead && <p className="max-w-3xl font-serif text-2xl leading-snug text-[#3a352c]">{lead}</p>}
      {children && <div className="mt-2 flex flex-wrap gap-2.5">{children}</div>}
    </header>
  );
}

export function Panel({ title, note, children, className = "" }: {
  title?: ReactNode; note?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`rounded-2xl border border-[#d9d2c4] bg-white p-5 sm:p-6 ${className}`}>
      {title && (
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-display text-xl font-bold">{title}</h2>
          {note && <span className="text-[13px] text-[#6b6355]">{note}</span>}
        </div>
      )}
      {children}
    </section>
  );
}

export const BTN = "inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-ink px-4 py-2.5 text-sm font-semibold text-paper hover:bg-black disabled:opacity-40";
export const BTN_LINE = "inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-[#b9b2a4] px-4 py-2.5 text-sm font-semibold text-ink hover:bg-[#f5f1ea] disabled:opacity-40";
export const FIELD = "mt-1.5 block w-full rounded-xl border border-[#b9b2a4] bg-white px-3.5 py-2.5 text-[15px] text-ink focus:border-ink focus:outline-none focus:ring-2 focus:ring-[#f2b705]/50";

export function Dot({ tone }: { tone: "good" | "warn" | "bad" | "off" }) {
  const color = { good: "bg-[#16a34a]", warn: "bg-[#b7791f]", bad: "bg-[#c2410c]", off: "bg-[#a8a092]" }[tone];
  return <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${color}`} aria-hidden="true" />;
}

export function useLocale() {
  return useLang().lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB";
}

export function when(iso: string | null | undefined, locale: string): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(locale, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** A plain message for a server error code. */
export function problem(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.code.startsWith("{") ? fallback : err.code;
  return fallback;
}
