import { Link } from "react-router-dom";

/** Product name used across the site; change it here. */
export const PRODUCT_NAME = "SiteSentry";

export function LogoMark({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <span className={`flex shrink-0 items-center justify-center rounded-lg bg-amber-400 text-slate-950 ${className}`} aria-hidden>
      <svg viewBox="0 0 24 24" className="h-[62%] w-[62%]" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        {/* an eye inside a shield: watching over the site */}
        <path d="M12 2.5 4 5.5v6c0 5 3.4 8.6 8 10 4.6-1.4 8-5 8-10v-6l-8-3z" />
        <path d="M7.5 12s1.8-3 4.5-3 4.5 3 4.5 3-1.8 3-4.5 3-4.5-3-4.5-3z" />
        <circle cx="12" cy="12" r="1" fill="currentColor" />
      </svg>
    </span>
  );
}

export function Logo({ to = "/", dark = false, subtitle }: { to?: string; dark?: boolean; subtitle?: string }) {
  return (
    <Link to={to} className="flex items-center gap-2.5">
      <LogoMark />
      <span className="leading-tight">
        <span className={`block text-[15px] font-semibold tracking-tight ${dark ? "text-white" : "text-slate-900"}`}>
          {PRODUCT_NAME}
        </span>
        {subtitle && <span className={`block text-xs ${dark ? "text-slate-400" : "text-slate-500"}`}>{subtitle}</span>}
      </span>
    </Link>
  );
}
