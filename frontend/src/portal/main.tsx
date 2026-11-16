/** The portal's screens (portal.html). Same look and components as the console; its server is portal/main.py. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { LanguageProvider } from "../lib/i18n";
import "../index.css";
import { Shell } from "./shell";
import { Companies, Company } from "./pages/Companies";
import { Approvals, MyDevices } from "./pages/Devices";
import { Boxes, Home, SecurityLog } from "./pages/Home";
import { AcceptInvite, NewDevice, SignIn } from "./pages/SignIn";

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 15_000, refetchOnWindowFocus: true } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <LanguageProvider>
          <Routes>
            <Route path="signin" element={<SignIn />} />
            <Route path="new-device" element={<NewDevice />} />
            <Route path="invite/:secret" element={<AcceptInvite />} />
            <Route element={<Shell />}>
              <Route index element={<Home />} />
              <Route path="companies" element={<Companies />} />
              <Route path="companies/:id" element={<Company />} />
              <Route path="boxes" element={<Boxes />} />
              <Route path="approvals" element={<Approvals />} />
              <Route path="log" element={<SecurityLog />} />
              <Route path="devices" element={<MyDevices />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </LanguageProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
