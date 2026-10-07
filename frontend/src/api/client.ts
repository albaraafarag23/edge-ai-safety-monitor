import type { FilterOptions, Incident, IncidentQuery, IncidentStatus, Report, Stats } from "./types";

// All backend calls go through /api (proxied by Vite in dev and nginx in Docker).
export const API_BASE = "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<{ data: T; headers: Headers }> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      // body wasn't JSON; keep the status text
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return { data: (await res.json()) as T, headers: res.headers };
}

function toQuery(params: object): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

/** Media paths from the backend ("/media/...") as URLs the browser can load. */
export function mediaUrl(path: string | null | undefined): string | null {
  return path ? `${API_BASE}${path}` : null;
}

export const api = {
  async incidents(query: IncidentQuery): Promise<{ items: Incident[]; total: number }> {
    const { data, headers } = await request<Incident[]>(`/incidents${toQuery(query)}`);
    return { items: data, total: Number(headers.get("X-Total-Count") ?? data.length) };
  },
  incident: async (id: string) => (await request<Incident>(`/incidents/${encodeURIComponent(id)}`)).data,
  report: async (id: string) => (await request<Report>(`/incidents/${encodeURIComponent(id)}/report`)).data,
  stats: async (hours: number) => (await request<Stats>(`/stats${toQuery({ hours })}`)).data,
  filters: async () => (await request<FilterOptions>("/filters")).data,
  setStatus: async (id: string, status: IncidentStatus, note?: string) =>
    (
      await request<Incident>(`/incidents/${encodeURIComponent(id)}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status, note: note || null }),
      })
    ).data,
};
