import { useSearchParams } from "react-router-dom";
import { useFilterOptions, useIncidents } from "../api/queries";
import { IncidentTable } from "../components/IncidentTable";
import { PageHeader } from "../components/Layout";
import { Card, EmptyState, ErrorState, Spinner } from "../components/ui";
import { humanize } from "../lib/format";

const PAGE_SIZE = 25;
const FILTERS = ["severity", "status", "event_type", "camera_id"] as const;
type Filter = (typeof FILTERS)[number];

function Select({ label, value, options, onChange }: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="min-w-40 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm text-slate-900 focus:border-sky-500 focus:ring-1 focus:ring-sky-500 focus:outline-none"
      >
        <option value="">All</option>
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
  const incidents = useIncidents({ ...filters, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE });

  const update = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) (v ? next.set(k, v) : next.delete(k));
    if (!("page" in changes)) next.delete("page");
    setParams(next);
  };
  const active = FILTERS.some((f) => filters[f]);
  const total = incidents.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <>
      <PageHeader title="Incidents" subtitle={incidents.data ? `${total} incident${total === 1 ? "" : "s"}` : undefined} />
      <Card>
        <div className="mb-5 flex flex-wrap items-end gap-3">
          <Select label="Severity" value={filters.severity} onChange={(v) => update({ severity: v })}
            options={(options.data?.severities ?? []).map((s) => ({ value: s, label: humanize(s) }))} />
          <Select label="Status" value={filters.status} onChange={(v) => update({ status: v })}
            options={(options.data?.statuses ?? []).map((s) => ({ value: s, label: humanize(s.toUpperCase()) }))} />
          <Select label="Type" value={filters.event_type} onChange={(v) => update({ event_type: v })}
            options={(options.data?.event_types ?? []).map((t) => ({ value: t, label: humanize(t) }))} />
          <Select label="Camera" value={filters.camera_id} onChange={(v) => update({ camera_id: v })}
            options={(options.data?.camera_ids ?? []).map((c) => ({ value: c, label: c }))} />
          {active && (
            <button
              onClick={() => setParams({})}
              className="rounded-md px-2.5 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100"
            >
              Clear filters
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
              <IncidentTable incidents={incidents.data.items} />
            </div>
            <nav className="mt-4 flex items-center justify-between text-sm text-slate-600" aria-label="Pagination">
              <span>
                Page {page} of {pages}
              </span>
              <div className="flex gap-2">
                <button
                  disabled={page <= 1}
                  onClick={() => update({ page: String(page - 1) })}
                  className="rounded-md border border-slate-300 px-3 py-1.5 hover:bg-slate-50 disabled:opacity-40"
                >
                  Previous
                </button>
                <button
                  disabled={page >= pages}
                  onClick={() => update({ page: String(page + 1) })}
                  className="rounded-md border border-slate-300 px-3 py-1.5 hover:bg-slate-50 disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </nav>
          </>
        ) : (
          <EmptyState title={active ? "No incidents match these filters" : "No incidents yet"}>
            {active ? "Try clearing a filter." : "New incidents appear here as soon as they're detected."}
          </EmptyState>
        )}
      </Card>
    </>
  );
}
