import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { API_BASE } from "../api/client";
import { keys } from "../api/queries";
import type { Incident } from "../api/types";

type ConnectionState = "connecting" | "live" | "offline";

interface Toast {
  id: number;
  incident: Incident;
}

interface LiveContextValue {
  connection: ConnectionState;
  toasts: Toast[];
  dismiss: (id: number) => void;
}

const LiveContext = createContext<LiveContextValue>({ connection: "connecting", toasts: [], dismiss: () => {} });

export const useLive = () => useContext(LiveContext);

const TOAST_SEVERITIES = new Set(["CRITICAL", "HIGH"]);
const TOAST_MS = 8000;

/**
 * Subscribes to the backend's Server-Sent Events and keeps cached data fresh:
 * a new incident, report or status change invalidates the affected queries.
 * EventSource reconnects on its own after a dropped connection.
 */
export function LiveProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);

  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);

  useEffect(() => {
    const source = new EventSource(`${API_BASE}/events`);
    source.onopen = () => setConnection("live");
    source.onerror = () => setConnection(source.readyState === EventSource.CLOSED ? "offline" : "connecting");

    source.addEventListener("incident", (e) => {
      const incident = JSON.parse((e as MessageEvent).data) as Incident;
      qc.invalidateQueries({ queryKey: keys.incidents });
      qc.invalidateQueries({ queryKey: ["stats"] });
      qc.invalidateQueries({ queryKey: keys.filters });
      if (TOAST_SEVERITIES.has(incident.severity)) {
        const id = nextId.current++;
        setToasts((t) => [...t.slice(-3), { id, incident }]);
        window.setTimeout(() => dismiss(id), TOAST_MS);
      }
    });
    source.addEventListener("report", (e) => {
      const { event_id } = JSON.parse((e as MessageEvent).data) as { event_id: string };
      qc.invalidateQueries({ queryKey: keys.report(event_id) });
      qc.invalidateQueries({ queryKey: keys.incidents });
    });
    source.addEventListener("status", () => {
      qc.invalidateQueries({ queryKey: keys.incidents });
      qc.invalidateQueries({ queryKey: ["stats"] });
    });

    return () => source.close();
  }, [qc, dismiss]);

  return <LiveContext.Provider value={{ connection, toasts, dismiss }}>{children}</LiveContext.Provider>;
}
