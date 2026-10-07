import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";
import { AppShell } from "./components/Layout";
import { RequireAuth } from "./lib/auth";
import { CONSOLE_URL, IS_STATIC_SITE } from "./lib/site";
import { Account } from "./pages/Account";
import { Analytics } from "./pages/Analytics";
import { Cameras } from "./pages/Cameras";
import { IncidentDetail } from "./pages/IncidentDetail";
import { Incidents } from "./pages/Incidents";
import { Landing } from "./pages/Landing";
import { Login } from "./pages/Login";
import { NotFound } from "./pages/NotFound";
import { Notifications } from "./pages/Notifications";
import { Overview } from "./pages/Overview";
import { Users } from "./pages/Users";

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
        <Route path="users" element={<Users />} />
        <Route path="account" element={<Account />} />
        <Route path="*" element={<NotFound />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
