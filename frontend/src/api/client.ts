import type { Analytics, Camera, FilterOptions, Incident, IncidentQuery, IncidentStatus, Report, Role, RuleChange, SafetyRule, SafetyRules, Stats, User } from "./types";

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

// Called when a signed-in request comes back 401 (session expired); the auth provider signs the user out.
let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

// The session is an HttpOnly cookie (same origin), so fetch sends it without any extra code.
async function request<T>(path: string, init?: RequestInit): Promise<{ data: T; headers: Headers }> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (res.status === 401 && !path.startsWith("/auth/")) onUnauthorized();
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      // body wasn't JSON; keep the status text
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  const data = res.status === 204 ? undefined : await res.json();
  return { data: data as T, headers: res.headers };
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

/** Live Motion-JPEG stream and latest still frame of a camera. */
export const cameraStreamUrl = (id: string) => `${API_BASE}/cameras/${encodeURIComponent(id)}/stream`;
export const cameraFrameUrl = (id: string) => `${API_BASE}/cameras/${encodeURIComponent(id)}/frame`;

export const api = {
  me: async () => (await request<User>("/auth/me")).data,
  login: async (email: string, password: string) =>
    (await request<User>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) })).data,
  logout: async () => {
    await request<void>("/auth/logout", { method: "POST" });
  },
  cameras: async () => (await request<Camera[]>("/cameras")).data,
  changePassword: async (current_password: string, new_password: string) =>
    (await request<User>("/auth/password", { method: "POST", body: JSON.stringify({ current_password, new_password }) })).data,
  users: async () => (await request<User[]>("/users")).data,
  addUser: async (user: { email: string; name: string; role: Role; password: string }) =>
    (await request<User>("/users", { method: "POST", body: JSON.stringify(user) })).data,
  updateUser: async (id: number, change: { name?: string; role?: Role; active?: boolean }) =>
    (await request<User>(`/users/${id}`, { method: "PATCH", body: JSON.stringify(change) })).data,
  resetPassword: async (id: number, password: string) => {
    await request<void>(`/users/${id}/password`, { method: "POST", body: JSON.stringify({ password }) });
  },
  analytics: async (days: number, tz: string) => (await request<Analytics>(`/analytics${toQuery({ days, tz })}`)).data,
  async incidents(query: IncidentQuery): Promise<{ items: Incident[]; total: number }> {
    const { data, headers } = await request<Incident[]>(`/incidents${toQuery(query)}`);
    return { items: data, total: Number(headers.get("X-Total-Count") ?? data.length) };
  },
  incident: async (id: string) => (await request<Incident>(`/incidents/${encodeURIComponent(id)}`)).data,
  report: async (id: string) => (await request<Report>(`/incidents/${encodeURIComponent(id)}/report`)).data,
  stats: async (hours: number) => (await request<Stats>(`/stats${toQuery({ hours })}`)).data,
  rules: async () => (await request<SafetyRules>("/rules")).data,
  changeRule: async (ruleId: string, change: RuleChange) =>
    (await request<SafetyRule>(`/rules/${encodeURIComponent(ruleId)}`, { method: "PATCH", body: JSON.stringify(change) }))
      .data,
  filters: async () => (await request<FilterOptions>("/filters")).data,
  setStatus: async (id: string, status: IncidentStatus, note?: string) =>
    (
      await request<Incident>(`/incidents/${encodeURIComponent(id)}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status, note: note || null }),
      })
    ).data,
};
