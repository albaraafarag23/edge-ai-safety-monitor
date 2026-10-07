import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { AppShell } from "./components/Layout";
import { RequireAuth } from "./lib/auth";
import { Cameras } from "./pages/Cameras";
import { IncidentDetail } from "./pages/IncidentDetail";
import { Incidents } from "./pages/Incidents";
import { Landing } from "./pages/Landing";
import { Login } from "./pages/Login";
import { NotFound } from "./pages/NotFound";
import { Notifications } from "./pages/Notifications";
import { Overview } from "./pages/Overview";

// links from before the console moved under /app
function LegacyIncident() {
  const { id = "" } = useParams();
  return <Navigate to={`/app/incidents/${id}`} replace />;
}

export function App() {
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
        <Route path="notifications" element={<Notifications />} />
        <Route path="*" element={<NotFound />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
