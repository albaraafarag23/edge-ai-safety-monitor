import type { IncidentStatus, Severity } from "../api/types";
import { currentLang, LOCALES } from "./i18n";

const locale = () => LOCALES[currentLang()];
const isAr = () => currentLang() === "ar";

/** PPE_MISSING -> "PPE missing", PERSON_NEAR_MACHINERY -> "Person near machinery". */
export function humanize(code: string | null | undefined): string {
  if (!code) return "Unknown";
  const words = code.split("_").map((w) => (["PPE", "ID"].includes(w) ? w : w.toLowerCase()));
  const text = words.join(" ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** hard_hat -> "Hard hat" */
export function humanizeItem(item: string): string {
  const text = item.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  // Arabic: month by name ("10 أكتوبر 2026"); numeric dates with slashes get reordered inside right-to-left text
  return isAr()
    ? d.toLocaleString(locale(), { day: "numeric", month: "long", year: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit" })
    : d.toLocaleString(locale(), { dateStyle: "medium", timeStyle: "medium" });
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" });
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
  ["second", 1],
];

export function timeAgo(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "—";
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000);
  const justNow = isAr() ? "الآن" : "just now";
  if (Math.abs(seconds) < 10) return justNow;
  const rtf = new Intl.RelativeTimeFormat(locale(), { numeric: "auto" });
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return rtf.format(Math.round(seconds / size), unit);
  }
  return justNow;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const [sec, min] = isAr() ? ["ث", "د"] : ["s", "min"];
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} ${sec}`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return s ? `${m} ${min} ${s} ${sec}` : `${m} ${min}`;
}

export const SEVERITY_ORDER: Severity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

export const SEVERITY_STYLES: Record<Severity, { badge: string; dot: string; bar: string }> = {
  CRITICAL: { badge: "bg-red-100 text-red-800 ring-red-600/20", dot: "bg-red-600", bar: "bg-red-600" },
  HIGH: { badge: "bg-orange-100 text-orange-800 ring-orange-600/20", dot: "bg-orange-500", bar: "bg-orange-500" },
  MEDIUM: { badge: "bg-amber-100 text-amber-800 ring-amber-600/20", dot: "bg-amber-500", bar: "bg-amber-400" },
  LOW: { badge: "bg-emerald-100 text-emerald-800 ring-emerald-600/20", dot: "bg-emerald-500", bar: "bg-emerald-500" },
};

export const STATUS_STYLES: Record<IncidentStatus, string> = {
  open: "bg-sky-100 text-sky-800 ring-sky-600/20",
  acknowledged: "bg-violet-100 text-violet-800 ring-violet-600/20",
  resolved: "bg-slate-100 text-slate-600 ring-slate-500/20",
};
