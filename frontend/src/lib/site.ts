import { useQuery } from "@tanstack/react-query";

/**
 * Where the console lives. Empty (the default) when this build *is* the console (Docker / nginx).
 * Set VITE_CONSOLE_URL when building the product page alone for static hosting (Cloudflare Pages):
 * sign-in links then go to that address, and the page shows whether the live demo is up.
 */
export const CONSOLE_URL = (import.meta.env.VITE_CONSOLE_URL ?? "").replace(/\/+$/, "");
export const IS_STATIC_SITE = CONSOLE_URL !== "";

export type DemoStatus = "checking" | "online" | "offline";

/** Whether the console's backend answers (public /health; the backend allows cross-origin reads). */
export function useDemoStatus(): DemoStatus {
  const health = useQuery({
    queryKey: ["demo-health"],
    queryFn: async () => {
      // first ask this site (a Cloudflare function checks the console: works on every network), then the console
      // itself (when the function isn't deployed, e.g. a local build)
      const viaSite = await fetch("/demo-health", { cache: "no-store", signal: AbortSignal.timeout(8000) }).catch(() => null);
      if (viaSite?.headers.get("content-type")?.includes("application/json")) {
        if (!viaSite.ok) throw new Error(String(viaSite.status));
        return true;
      }
      const res = await fetch(`${CONSOLE_URL}/api/health`, { cache: "no-store", signal: AbortSignal.timeout(8000) });
      if (!res.ok) throw new Error(String(res.status));
      return true;
    },
    retry: 1,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
  if (health.isPending) return "checking";
  return health.isSuccess ? "online" : "offline";
}
