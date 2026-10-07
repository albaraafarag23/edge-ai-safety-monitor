import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { ApiError, api, setUnauthorizedHandler } from "../api/client";
import type { User } from "../api/types";
import { FullPageSpinner } from "../components/ui";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth needs an AuthProvider");
  return ctx;
}

const ME = ["auth", "me"] as const;

/** Who is signed in, from GET /auth/me. The session itself is an HttpOnly cookie set by the backend. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const me = useQuery({
    queryKey: ME,
    queryFn: async () => {
      try {
        return await api.me();
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 5 * 60_000,
    refetchInterval: false,
    retry: 1,
  });

  const signedOut = useCallback(() => {
    qc.setQueryData(ME, null);
    // drop everything cached for the previous user
    qc.removeQueries({ predicate: (q) => q.queryKey[0] !== ME[0] });
  }, [qc]);

  useEffect(() => setUnauthorizedHandler(signedOut), [signedOut]);

  const login = useCallback(
    async (email: string, password: string) => {
      const user = await api.login(email, password);
      qc.setQueryData(ME, user);
      return user;
    },
    [qc],
  );

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      signedOut();
    }
  }, [signedOut]);

  return (
    <AuthContext.Provider value={{ user: me.data ?? null, loading: me.isPending, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

/** Renders its children only for a signed-in user; otherwise sends them to /login and back afterwards. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <FullPageSpinner />;
  if (!user) {
    const next = location.pathname + location.search;
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }
  return <>{children}</>;
}
