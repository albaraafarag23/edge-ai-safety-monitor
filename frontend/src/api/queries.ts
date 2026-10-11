import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "./client";
import type { IncidentQuery, IncidentStatus, Role, RuleChange } from "./types";

// Query keys in one place so live events can invalidate exactly what changed.
export const keys = {
  incidents: ["incidents"] as const,
  incidentList: (q: IncidentQuery) => ["incidents", "list", q] as const,
  incident: (id: string) => ["incidents", "detail", id] as const,
  report: (id: string) => ["reports", id] as const,
  stats: (hours: number) => ["stats", hours] as const,
  filters: ["filters"] as const,
  cameras: ["cameras"] as const,
  users: ["users"] as const,
  rules: ["rules"] as const,
  zones: ["zones"] as const,
  analytics: (days: number) => ["analytics", days] as const,
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

export const useAnalytics = (days: number) =>
  useQuery({
    queryKey: keys.analytics(days),
    queryFn: () => api.analytics(days, Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"),
    placeholderData: keepPreviousData,
  });

export const useUsers = () => useQuery({ queryKey: keys.users, queryFn: api.users });

export function useUserMutations() {
  const qc = useQueryClient();
  const onSuccess = () => qc.invalidateQueries({ queryKey: keys.users });
  return {
    add: useMutation({ mutationFn: api.addUser, onSuccess }),
    update: useMutation({
      mutationFn: ({ id, ...change }: { id: number; name?: string; role?: Role; active?: boolean }) => api.updateUser(id, change),
      onSuccess,
    }),
    resetPassword: useMutation({ mutationFn: ({ id, password }: { id: number; password: string }) => api.resetPassword(id, password) }),
  };
}

export const useRules = () => useQuery({ queryKey: keys.rules, queryFn: api.rules });

export const useZones = () => useQuery({ queryKey: keys.zones, queryFn: api.zones });

export function useZoneMutations() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: keys.zones });
  return {
    draw: useMutation({
      mutationFn: ({ zoneId, polygon }: { zoneId: string; polygon: [number, number][] }) => api.drawZone(zoneId, polygon),
      onSettled: done,
    }),
    reset: useMutation({ mutationFn: (zoneId: string) => api.resetZone(zoneId), onSettled: done }),
  };
}

export function useChangeRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ ruleId, change }: { ruleId: string; change: RuleChange }) => api.changeRule(ruleId, change),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.rules }),
  });
}
