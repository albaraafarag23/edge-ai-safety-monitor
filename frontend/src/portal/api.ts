/**
 * Talking to the portal server (portal/main.py), and the passkey steps in the browser.
 *
 * Dangerous changes answer 428 "step_up" when the last passkey check is over 5 minutes old: send() then asks
 * for the passkey once (the browser's own fingerprint / face / PIN prompt) and repeats the request.
 */
import { startAuthentication, startRegistration } from "@simplewebauthn/browser";

export type Role = "overseer" | "manager" | "supervisor" | "viewer";
export type DeviceStatus = "pending" | "approved" | "refused" | "revoked";

export interface Device {
  id: number;
  user_id: number;
  label: string;
  status: DeviceStatus;
  created_at: string;
  last_used: string | null;
  decided_at: string | null;
  this?: boolean;
}
export interface Person {
  id: number;
  email: string;
  name: string;
  role: Role;
  company_id: number | null;
  active: boolean;
  last_sign_in: string | null;
  created_at: string;
}
export interface Me extends Person {
  company: { id: number; name: string } | null;
  device: Device;
  fresh: boolean;
}
export interface Box {
  id: number;
  serial: string;
  site_id: number | null;
  status: "waiting" | "approved" | "blocked";
  last_checkin: string | null;
  silent: boolean;
  health: Record<string, unknown>;
  site?: string | null;
  company?: string | null;
  company_id?: number | null;
  plugins: string[];
  connected: boolean;
}
export interface BoxHealth {
  cameras?: { id: string; fps: number; updated_at?: string }[];
  rules?: string | null;
  rules_state?: string | null;
  disk_used_pct?: number | null;
  version?: string | null;
}
export interface SiteRef {
  id: number;
  name: string;
  company_id: number;
  company: string;
}
export interface RuleSet {
  id: string;
  name: string;
}
export interface CompanySummary {
  id: number;
  name: string;
  active: boolean;
  created_at: string;
  sites: number;
  people: number;
  boxes: number;
  silent_boxes: number;
}
export interface Site {
  id: number;
  name: string;
  city: string | null;
}
export interface CompanyPerson extends Person {
  site_ids: number[];
  devices: Device[];
  invite_waiting: boolean;
  can_manage: boolean;
}
export interface CompanyDetail {
  id: number;
  name: string;
  active: boolean;
  created_at?: string;
  sites: Site[];
  boxes: Box[];
  people: CompanyPerson[];
}
export interface Approval extends Device {
  person: Person;
  company: string | null;
}
export interface Overview {
  companies: number;
  boxes: number;
  boxes_fine: number;
  silent: Box[];
  boxes_waiting: Box[];
  approvals: Approval[];
}
export interface LogEntry {
  id: number;
  at: string;
  actor: string;
  action: string;
  summary: string;
}
export interface Invite {
  name: string;
  email: string;
  role: Role;
  company: string | null;
  expires_at: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(code);
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (!response.ok) {
    let code = response.statusText;
    try {
      const body = await response.json();
      code = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(response.status, code);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export const get = <T>(path: string) => call<T>(path);

/** A change. Asks for the passkey again first when the server wants a fresh check. */
export async function send<T>(path: string, body?: unknown, method = "POST"): Promise<T> {
  const init = { method, body: body === undefined ? undefined : JSON.stringify(body) };
  try {
    return await call<T>(path, init);
  } catch (err) {
    if (!(err instanceof ApiError && err.status === 428)) throw err;
    await confirmWithPasskey();
    return call<T>(path, init);
  }
}

/** A short name for this device: "Chrome on Windows". */
export function deviceLabel(): string {
  const ua = navigator.userAgent;
  const browser = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome"
    : /Safari\//.test(ua) ? "Safari" : "Browser";
  const system = /iPhone|iPad/.test(ua) ? "iPhone" : /Android/.test(ua) ? "Android" : /Windows/.test(ua) ? "Windows"
    : /Mac OS X/.test(ua) ? "Mac" : /Linux/.test(ua) ? "Linux" : "a device";
  return `${browser} on ${system}`;
}

type Options = { id: string; options: Parameters<typeof startRegistration>[0]["optionsJSON"] };
type SignOptions = { id: string; options: Parameters<typeof startAuthentication>[0]["optionsJSON"] };

export async function signInWithPasskey() {
  const { id, options } = await call<SignOptions>("/auth/signin/options", { method: "POST" });
  const credential = await startAuthentication({ optionsJSON: options });
  return call("/auth/signin", { method: "POST", body: JSON.stringify({ id, credential }) });
}

export async function confirmWithPasskey() {
  const { id, options } = await call<SignOptions>("/auth/stepup/options", { method: "POST" });
  const credential = await startAuthentication({ optionsJSON: options });
  await call("/auth/stepup", { method: "POST", body: JSON.stringify({ id, credential }) });
}

export async function acceptInvite(secret: string) {
  const { id, options } = await call<Options>(`/invites/${encodeURIComponent(secret)}/options`, { method: "POST" });
  const credential = await startRegistration({ optionsJSON: options });
  return call(`/invites/${encodeURIComponent(secret)}`, {
    method: "POST",
    body: JSON.stringify({ id, credential, label: deviceLabel() }),
  });
}

export async function requestDevice(email: string) {
  const { id, options } = await call<Options>("/devices/request/options", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
  const credential = await startRegistration({ optionsJSON: options });
  return call<{ status: "pending" }>("/devices/request", {
    method: "POST",
    body: JSON.stringify({ id, credential, label: deviceLabel() }),
  });
}

/** The browser said no (cancelled the prompt, timed out, no passkey here) rather than the server. */
export function cancelledByBrowser(err: unknown): boolean {
  return err instanceof Error && ["NotAllowedError", "AbortError", "InvalidStateError"].includes(err.name);
}
