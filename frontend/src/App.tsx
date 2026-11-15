import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";
import { AppShell } from "./components/Layout";
import { RequireAuth } from "./lib/auth";
import { CONSOLE_URL, IS_STATIC_SITE } from "./lib/site";
import { Landing } from "./pages/Landing";

// Console pages load when they are first opened, so the product page (most visitors) downloads only itself.
const page = <K extends string>(name: K, load: () => Promise<Record<K, () => ReactNode>>) =>
  lazy(() => load().then((m) => ({ default: m[name] })));
const Account = page("Account", () => import("./pages/Account"));
const Analytics = page("Analytics", () => import("./pages/Analytics"));
const Cameras = page("Cameras", () => import("./pages/Cameras"));
const People = page("People", () => import("./pages/People"));
const IncidentDetail = page("IncidentDetail", () => import("./pages/IncidentDetail"));
const Incidents = page("Incidents", () => import("./pages/Incidents"));
const Login = page("Login", () => import("./pages/Login"));
const NotFound = page("NotFound", () => import("./pages/NotFound"));
const Notifications = page("Notifications", () => import("./pages/Notifications"));
const Overview = page("Overview", () => import("./pages/Overview"));
const Rules = page("Rules", () => import("./pages/Rules"));
const Users = page("Users", () => import("./pages/Users"));

/** While a page's code arrives (a fraction of a second): the paper background, no flash of anything else. */
function Loading({ children }: { children: ReactNode }) {
  return <Suspense fallback={<div className="min-h-[60vh] bg-paper" aria-busy="true" />}>{children}</Suspense>;
}

// links from before the console moved under /app
function LegacyIncident() {
  const { id = "" } = useParams();
  return <Navigate to={`/app/incidents/${id}`} replace />;
}

// On the static product page, anything but "/" belongs to the console
function ToConsole() {
  const { pathname, search } = useLocation();
  useEffect(() => window.location.replace(`${CONSOLE_URL}${pathname}${search}`), [pathname, search]);
  return null;
}

export function App() {
  if (IS_STATIC_SITE) {
    return (
      <Routes>
        <Route index element={<Landing />} />
        <Route path="*" element={<ToConsole />} />
      </Routes>
    );
  }
  return (
    <Loading>
    <Routes>
      <Route index element={<Landing />} />
      <Route path="login" element={<Login />} />
      <Route path="incidents" element={<Navigate to="/app/incidents" replace />} />
      <Route path="incidents/:id" element={<LegacyIncident />} />

      <Route
        path="app"
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<Overview />} />
        <Route path="cameras" element={<Cameras />} />
        <Route path="incidents" element={<Incidents />} />
        <Route path="incidents/:id" element={<IncidentDetail />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="notifications" element={<Notifications />} />
        <Route path="rules" element={<Rules />} />
        <Route path="people" element={<People />} />
        <Route path="users" element={<Users />} />
        <Route path="account" element={<Account />} />
        <Route path="*" element={<NotFound />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </Loading>
  );
}
