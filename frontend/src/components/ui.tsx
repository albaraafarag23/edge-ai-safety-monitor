import { useEffect, useRef, useState, type ReactNode } from "react";
import type { IncidentStatus, Severity } from "../api/types";
import { SEVERITY_STYLES, STATUS_STYLES } from "../lib/format";
import { bilingual, useLang, useText } from "../lib/i18n";
import { severityLabel, statusLabel } from "../lib/terms";

const TEXT = bilingual(
  {
    loading: "Loading…",
    loadFailed: "Couldn't load data",
    backendHint: (message: string) => `${message}. Is the backend running?`,
    somethingWrong: "Something went wrong",
    tryAgain: "Try again",
    close: "Close",
  },
  {
    loading: "جارٍ التحميل…",
    loadFailed: "تعذّر تحميل البيانات",
    backendHint: (message: string) => `${message}. هل الخادم يعمل؟`,
    somethingWrong: "حدث خطأ ما",
    tryAgain: "إعادة المحاولة",
    close: "إغلاق",
  },
);

const BADGE = "inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset";

export function SeverityBadge({ severity }: { severity: Severity }) {
  const s = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.LOW;
  const { lang } = useLang();
  return (
    <span className={`${BADGE} ${s.badge}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} aria-hidden />
      {lang === "ar" ? severityLabel(severity) : severity}
    </span>
  );
}

export function StatusBadge({ status }: { status: IncidentStatus }) {
  return <span className={`${BADGE} ${STATUS_STYLES[status]}`}>{statusLabel(status)}</span>;
}

export function Card({ title, action, children, className = "" }: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-lg bg-white shadow-[0_1px_2px_rgb(21_19_15/0.04)] ring-1 ring-ink/10 ${className}`}>
      {title && (
        <header className="flex items-center justify-between border-b border-ink/[0.07] px-5 py-3.5">
          <h2 className="font-serif text-[1.4rem] leading-none text-ink">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

/** Counts up to a new value (e.g. when a new incident arrives); no animation with reduced motion. */
export function CountUp({ value, ms = 700 }: { value: number; ms?: number }) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const start = from.current;
    if (start === value || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      from.current = value;
      setShown(value);
      return;
    }
    const t0 = performance.now();
    let frame = requestAnimationFrame(function step(now) {
      const k = Math.min(1, (now - t0) / ms);
      const eased = 1 - Math.pow(1 - k, 3);
      setShown(Math.round(start + (value - start) * eased));
      if (k < 1) frame = requestAnimationFrame(step);
      else from.current = value;
    });
    return () => {
      cancelAnimationFrame(frame);
      from.current = value;
    };
  }, [value, ms]);
  return <>{shown}</>;
}

/** A big editorial number with a coloured rule on top. */
export function StatCard({ label, value, hint, accent = "bg-ink" }: {
  label: string;
  value: ReactNode;
  hint?: string;
  accent?: string;
}) {
  return (
    <div className="relative pt-5">
      <span className={`absolute inset-x-0 top-0 h-[3px] ${accent}`} aria-hidden />
      <p className="font-serif text-xl text-ink/60 italic">{label}</p>
      <p
        className={`mt-1 font-display leading-none font-semibold tracking-[-0.04em] text-ink tabular-nums ${
          typeof value === "number" ? "text-6xl sm:text-7xl" : "text-4xl sm:text-5xl"
        }`}
      >
        {typeof value === "number" ? <CountUp value={value} /> : value}
      </p>
      {hint && <p className="mt-2 text-xs text-ink/40">{hint}</p>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  const t = useText(TEXT);
  return (
    <div className="flex items-center justify-center gap-3 py-12 text-sm text-slate-500" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600" />
      {label ?? t.loading}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const t = useText(TEXT);
  const message = error instanceof Error ? error.message : t.somethingWrong;
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">
      <p className="font-medium">{t.loadFailed}</p>
      <p className="mt-0.5 text-red-700">{t.backendHint(message)}</p>
      {onRetry && (
        <button onClick={onRetry} className="mt-2 font-medium text-red-900 underline underline-offset-2">
          {t.tryAgain}
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="py-12 text-center">
      <p className="text-sm font-medium text-slate-700">{title}</p>
      {children && <p className="mt-1 text-sm text-slate-500">{children}</p>}
    </div>
  );
}

/** Horizontal bars, for "count by category" without a chart library. */
export function BarList({ items, colorFor }: {
  items: { label: string; value: number; key: string }[];
  colorFor?: (key: string) => string;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className="space-y-3">
      {items.map((item) => (
        <li key={item.key}>
          <div className="mb-1 flex justify-between text-sm">
            <span className="text-ink/75">{item.label}</span>
            <span className="font-semibold tabular-nums text-ink">{item.value}</span>
          </div>
          <div className="h-1.5 rounded-full bg-ink/[0.06]">
            <div
              className={`h-1.5 rounded-full transition-[width] duration-700 ${colorFor?.(item.key) ?? "bg-ink"}`}
              style={{ width: `${(item.value / max) * 100}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function FullPageSpinner() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-paper">
      <Spinner />
    </div>
  );
}

/** Centered dialog over a dimmed page. Closes on Escape or a click outside. */
export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const t = useText(TEXT);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div role="dialog" aria-modal="true" aria-label={title} className="w-full max-w-md rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          <button onClick={onClose} className="text-xl leading-none text-slate-400 hover:text-slate-600" aria-label={t.close}>
            ×
          </button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  );
}

export const INPUT =
  "mt-1.5 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-slate-900 focus:ring-1 focus:ring-slate-900 focus:outline-none";
export const BUTTON_PRIMARY =
  "inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 disabled:opacity-50";
export const BUTTON_SECONDARY =
  "inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50";

/** A random password that's easy to read out (no 0/O, 1/l). */
export function generatePassword(length = 14): string {
  const chars = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const values = crypto.getRandomValues(new Uint32Array(length));
  return Array.from(values, (v) => chars[v % chars.length]).join("");
}
