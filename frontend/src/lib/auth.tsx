import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { ApiError, api, setUnauthorizedHandler } from "../api/client";
import type { User } from "../api/types";
import { FullPageSpinner } from "../components/ui";
import { bilingual, useText } from "./i18n";
import { IS_STATIC_SITE } from "./site";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  unreachable: boolean; // the console's server didn't answer (not the same as signed out)
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
    // while the server is unreachable, keep asking, so the console comes back by itself
    refetchInterval: (q) => (q.state.status === "error" ? 5_000 : false),
    retry: 1,
    enabled: !IS_STATIC_SITE, // the static product page has no API of its own
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
    <AuthContext.Provider
      value={{ user: me.data ?? null, loading: me.isPending && !IS_STATIC_SITE, unreachable: me.isError && !me.data, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

const UNREACHABLE = bilingual(
  {
    title: "Can't reach the console right now",
    text: "The site computer may be restarting or offline. This page tries again every few seconds and carries on by itself.",
  },
  {
    title: "تعذّر الوصول إلى لوحة التحكم الآن",
    text: "ربما يُعاد تشغيل جهاز الموقع أو أنه غير متصل. تعيد هذه الصفحة المحاولة كل بضع ثوانٍ وتتابع تلقائيًا.",
  },
);

function Unreachable() {
  const t = useText(UNREACHABLE);
  return (
    <div className="flex min-h-screen items-center justify-center bg-paper px-6">
      <div className="max-w-md text-center">
        <span className="relative mx-auto flex h-3 w-3">
          <span className="radar absolute inset-0 rounded-full bg-amber-500" />
          <span className="relative h-3 w-3 rounded-full bg-amber-500" />
        </span>
        <h1 className="mt-6 font-serif text-3xl text-ink">{t.title}</h1>
        <p className="mt-3 text-ink/70">{t.text}</p>
      </div>
    </div>
  );
}

/** Renders its children only for a signed-in user; otherwise sends them to /login and back afterwards. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading, unreachable } = useAuth();
  const location = useLocation();
  if (loading) return <FullPageSpinner />;
  // a server restart must not look like being signed out: wait for it instead of showing the sign-in page
  if (!user && unreachable) return <Unreachable />;
  if (!user) {
    const next = location.pathname + location.search;
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }
  return <>{children}</>;
}
