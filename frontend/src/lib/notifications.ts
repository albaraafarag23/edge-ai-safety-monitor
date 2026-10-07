import { useCallback, useSyncExternalStore } from "react";
import type { Incident } from "../api/types";
import { humanize } from "./format";

/**
 * Per-browser notification settings and "read up to" time, kept in localStorage.
 * (Read state isn't shared between devices; moving it to the backend is a later step.)
 */
export interface NotificationPrefs {
  desktop: boolean; // browser notifications for HIGH / CRITICAL incidents
  sound: boolean; // short chime for HIGH / CRITICAL incidents
  lastSeen: string | null; // ISO time; incidents received after it are unread
}

const KEY = "sm.notifications";
const DEFAULTS: NotificationPrefs = { desktop: false, sound: false, lastSeen: null };
const listeners = new Set<() => void>();
let cached: NotificationPrefs | null = null;

function read(): NotificationPrefs {
  if (cached) return cached;
  try {
    cached = { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) ?? "{}") };
  } catch {
    cached = { ...DEFAULTS };
  }
  return cached!;
}

export function updatePrefs(change: Partial<NotificationPrefs>) {
  cached = { ...read(), ...change };
  try {
    localStorage.setItem(KEY, JSON.stringify(cached));
  } catch {
    // storage blocked (private mode): settings last until the tab closes
  }
  listeners.forEach((l) => l());
}

export function getPrefs() {
  return read();
}

export function useNotificationPrefs(): [NotificationPrefs, (change: Partial<NotificationPrefs>) => void] {
  const prefs = useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    read,
    read,
  );
  return [prefs, useCallback(updatePrefs, [])];
}

export function isUnread(incident: Incident, lastSeen: string | null): boolean {
  return !lastSeen || new Date(incident.received_at) > new Date(lastSeen);
}

export const desktopSupported = () => typeof window !== "undefined" && "Notification" in window;

/** Asks the browser for permission; returns whether desktop notifications can be shown. */
export async function enableDesktop(): Promise<boolean> {
  if (!desktopSupported()) return false;
  const permission = Notification.permission === "default" ? await Notification.requestPermission() : Notification.permission;
  const ok = permission === "granted";
  updatePrefs({ desktop: ok });
  return ok;
}

/** Desktop notification and/or chime for a new incident, as the user's settings allow. */
export function alertIncident(incident: Incident, onClick: () => void) {
  const prefs = read();
  if (prefs.desktop && desktopSupported() && Notification.permission === "granted") {
    const where = incident.location !== "NOT SPECIFIED" ? ` · ${incident.location}` : "";
    const n = new Notification(`${incident.severity}: ${humanize(incident.event_type)}`, {
      body: `${incident.camera_id}${where}`,
      tag: incident.event_id,
    });
    n.onclick = () => {
      window.focus();
      onClick();
      n.close();
    };
  }
  if (prefs.sound) chime();
}

function chime() {
  try {
    const ctx = new AudioContext();
    const gain = ctx.createGain();
    gain.connect(ctx.destination);
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.2, ctx.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.6);
    for (const [freq, start] of [
      [880, 0],
      [660, 0.18],
    ]) {
      const osc = ctx.createOscillator();
      osc.frequency.value = freq;
      osc.connect(gain);
      osc.start(ctx.currentTime + start);
      osc.stop(ctx.currentTime + start + 0.4);
    }
    window.setTimeout(() => ctx.close(), 1000);
  } catch {
    // audio blocked until the user interacts with the page
  }
}
