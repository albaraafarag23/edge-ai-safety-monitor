import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "./client";
import type { IncidentQuery, IncidentStatus } from "./types";

// Query keys in one place so live events can invalidate exactly what changed.
export const keys = {
  incidents: ["incidents"] as const,
  incidentList: (q: IncidentQuery) => ["incidents", "list", q] as const,
  incident: (id: string) => ["incidents", "detail", id] as const,
  report: (id: string) => ["reports", id] as const,
  stats: (hours: number) => ["stats", hours] as const,
  filters: ["filters"] as const,
  cameras: ["cameras"] as const,
};

export const useIncidents = (q: IncidentQuery) =>
  useQuery({ queryKey: keys.incidentList(q), queryFn: () => api.incidents(q), placeholderData: keepPreviousData });

export const useIncident = (id: string) => useQuery({ queryKey: keys.incident(id), queryFn: () => api.incident(id) });

export const useReport = (id: string) =>
  useQuery({
    queryKey: keys.report(id),
    queryFn: () => api.report(id),
    // a 404 just means the report isn't written yet; a live "report" event refetches it
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 2,
  });

export const useStats = (hours: number) => useQuery({ queryKey: keys.stats(hours), queryFn: () => api.stats(hours) });

export const useFilterOptions = () =>
  useQuery({ queryKey: keys.filters, queryFn: api.filters, staleTime: 60_000 });

// camera status (online, fps) changes by itself, so this one polls
export const useCameras = () =>
  useQuery({ queryKey: keys.cameras, queryFn: api.cameras, refetchInterval: 5_000, staleTime: 2_000 });

export function useSetStatus(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ status, note }: { status: IncidentStatus; note?: string }) => api.setStatus(id, status, note),
    onSuccess: (incident) => {
      qc.setQueryData(keys.incident(id), incident);
      qc.invalidateQueries({ queryKey: keys.incidents });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}
