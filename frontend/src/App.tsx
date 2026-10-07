import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { IncidentDetail } from "./pages/IncidentDetail";
import { Incidents } from "./pages/Incidents";
import { NotFound } from "./pages/NotFound";
import { Overview } from "./pages/Overview";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="incidents" element={<Incidents />} />
        <Route path="incidents/:id" element={<IncidentDetail />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
