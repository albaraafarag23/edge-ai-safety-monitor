import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useFilterOptions, useIncidents } from "../api/queries";
import { IncidentList } from "../components/IncidentTable";
import { PageHeader } from "../components/Layout";
import { Card, EmptyState, ErrorState, Spinner } from "../components/ui";
import { bilingual, plural, useText } from "../lib/i18n";
import { eventTypeLabel, severityLabel } from "../lib/terms";

const TEXT = bilingual(
  {
    title: "Incidents",
    count: (n: number): string => `${n} incident${n === 1 ? "" : "s"}`,
    all: "All",
    severity: "Severity",
    status: "Status",
    type: "Type",
    camera: "Camera",
    clear: "Clear filters",
    pagination: "Pagination",
    page: (page: number, pages: number) => `Page ${page} of ${pages}`,
    previous: "Previous",
    next: "Next",
    noMatch: "No incidents match these filters",
    noIncidents: "No incidents yet",
    noMatchHint: "Try clearing a filter.",
    noIncidentsHint: "New incidents appear here as soon as they're detected.",
    tabs: { open: "Waiting", acknowledged: "On it", resolved: "Done", all: "All" } as Record<string, string>,
    show: "Show",
    moreFilters: "More filters",
  },
  {
    title: "الحوادث",
    count: (n: number) => `${n} ${plural("ar", n, { one: "حادثة", two: "حادثة", few: "حوادث", other: "حادثة" })}`,
    all: "الكل",
    severity: "الخطورة",
    status: "الحالة",
    type: "النوع",
    camera: "الكاميرا",
    clear: "مسح عوامل التصفية",
    pagination: "التنقل بين الصفحات",
    page: (page: number, pages: number) => `الصفحة ${page} من ${pages}`,
    previous: "السابق",
    next: "التالي",
    noMatch: "لا توجد حوادث تطابق عوامل التصفية",
    noIncidents: "لا توجد حوادث بعد",
    noMatchHint: "جرّب إزالة أحد عوامل التصفية.",
    noIncidentsHint: "تظهر الحوادث الجديدة هنا فور رصدها.",
    tabs: { open: "بانتظارك", acknowledged: "قيد المتابعة", resolved: "تمت", all: "الكل" },
    show: "عرض",
    moreFilters: "عوامل تصفية أخرى",
  },
);

const PAGE_SIZE = 25;
const FILTERS = ["severity", "status", "event_type", "camera_id"] as const;
type Filter = (typeof FILTERS)[number];

function Select({ label, value, options, onChange }: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  const t = useText(TEXT);
  return (
    <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="min-w-40 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm text-slate-900 focus:border-sky-500 focus:ring-1 focus:ring-sky-500 focus:outline-none"
      >
        <option value="">{t.all}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function Incidents() {
  // filters and page live in the URL, so a filtered view can be bookmarked or shared
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get("page")) || 1);
  const filters = Object.fromEntries(FILTERS.map((f) => [f, params.get(f) ?? ""])) as Record<Filter, string>;
  const options = useFilterOptions();
  const t = useText(TEXT);
  const incidents = useIncidents({ ...filters, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE });

  const update = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) (v ? next.set(k, v) : next.delete(k));
    if (!("page" in changes)) next.delete("page");
    setParams(next);
  };
  const active = FILTERS.some((f) => filters[f]);
  const [showFilters, setShowFilters] = useState(false);
  const filtersOpen = showFilters || ["severity", "event_type", "camera_id"].some((f) => filters[f as Filter]);
  const total = incidents.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <>
      <PageHeader title={t.title} subtitle={incidents.data ? t.count(total) : undefined} />
      <Card>
        <div className="mb-4 inline-flex flex-wrap rounded-full bg-paper p-1 text-sm ring-1 ring-ink/10" role="group" aria-label={t.show}>
          {["open", "acknowledged", "resolved", ""].map((s) => (
            <button
              key={s || "all"}
              onClick={() => update({ status: s })}
              aria-pressed={filters.status === s}
              className={`rounded-full px-4 py-1.5 font-medium ${filters.status === s ? "bg-ink text-paper" : "text-ink/60 hover:text-ink"}`}
            >
              {t.tabs[s || "all"]}
            </button>
          ))}
        </div>
        {/* on phones the extra filters fold away behind one button (open by itself when one is in use) */}
        <button
          onClick={() => setShowFilters((v) => !v)}
          aria-expanded={filtersOpen}
          className="mb-4 ms-2 rounded-full px-3 py-1.5 text-sm font-medium text-ink/65 ring-1 ring-ink/15 sm:hidden"
        >
          {t.moreFilters}
        </button>
        <div className={`mb-5 flex-wrap items-end gap-3 ${filtersOpen ? "flex" : "hidden"} sm:flex`}>
          <Select label={t.severity} value={filters.severity} onChange={(v) => update({ severity: v })}
            options={(options.data?.severities ?? []).map((s) => ({ value: s, label: severityLabel(s) }))} />
          <Select label={t.type} value={filters.event_type} onChange={(v) => update({ event_type: v })}
            options={(options.data?.event_types ?? []).map((e) => ({ value: e, label: eventTypeLabel(e) }))} />
          <Select label={t.camera} value={filters.camera_id} onChange={(v) => update({ camera_id: v })}
            options={(options.data?.camera_ids ?? []).map((c) => ({ value: c, label: c }))} />
          {active && (
            <button
              onClick={() => setParams({})}
              className="rounded-md px-2.5 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100"
            >
              {t.clear}
            </button>
          )}
        </div>

        {incidents.isPending ? (
          <Spinner />
        ) : incidents.isError ? (
          <ErrorState error={incidents.error} onRetry={() => incidents.refetch()} />
        ) : incidents.data.items.length ? (
          <>
            <div className={incidents.isPlaceholderData ? "opacity-60" : ""}>
              <IncidentList incidents={incidents.data.items} />
            </div>
            <nav className="mt-4 flex items-center justify-between text-sm text-slate-600" aria-label={t.pagination}>
              <span>{t.page(page, pages)}</span>
              <div className="flex gap-2">
                <button
                  disabled={page <= 1}
                  onClick={() => update({ page: String(page - 1) })}
                  className="rounded-md border border-slate-300 px-3 py-1.5 hover:bg-slate-50 disabled:opacity-40"
                >
                  {t.previous}
                </button>
                <button
                  disabled={page >= pages}
                  onClick={() => update({ page: String(page + 1) })}
                  className="rounded-md border border-slate-300 px-3 py-1.5 hover:bg-slate-50 disabled:opacity-40"
                >
                  {t.next}
                </button>
              </div>
            </nav>
          </>
        ) : (
          <EmptyState title={active ? t.noMatch : t.noIncidents}>
            {active ? t.noMatchHint : t.noIncidentsHint}
          </EmptyState>
        )}
      </Card>
    </>
  );
}
