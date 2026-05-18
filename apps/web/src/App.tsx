import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "@/auth/AuthProvider";
import { RequireAuth } from "@/auth/RequireAuth";
import { AppShell } from "@/components/AppShell";
import { AccountScreen } from "@/screens/AccountScreen";
import { ApiKeysScreen } from "@/screens/ApiKeysScreen";
import { AuthCallbackScreen } from "@/screens/AuthCallbackScreen";
import { ChannelsScreen } from "@/screens/ChannelsScreen";
import { CreateMonitorScreen } from "@/screens/CreateMonitorScreen";
import { FailuresScreen } from "@/screens/FailuresScreen";
import { LandingScreen } from "@/screens/LandingScreen";
import { LegalPage } from "@/screens/LegalPage";
import { LoginScreen } from "@/screens/LoginScreen";
import { MonitorDetailScreen } from "@/screens/MonitorDetailScreen";
import { MonitorsScreen } from "@/screens/MonitorsScreen";
import { OverviewScreen } from "@/screens/OverviewScreen";
import { RunDetailScreen } from "@/screens/RunDetailScreen";
import { StatusPageScreen } from "@/screens/StatusPageScreen";

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public marketing + legal pages. The landing page itself
              redirects authenticated users to /overview, so signed-in
              visitors never see it. */}
          <Route path="/" element={<LandingScreen />} />
          <Route path="/privacy" element={<LegalPage doc="privacy" />} />
          <Route path="/terms" element={<LegalPage doc="terms" />} />
          <Route path="/login" element={<LoginScreen />} />
          <Route path="/auth/callback" element={<AuthCallbackScreen />} />

          {/* Authenticated dashboard. The shell loads the account on
              mount and gates everything behind the terms modal until
              the user has accepted the current published version. */}
          <Route
            element={
              <RequireAuth>
                <AppShell />
              </RequireAuth>
            }
          >
            <Route path="overview" element={<OverviewScreen />} />
            <Route path="monitors" element={<MonitorsScreen />} />
            <Route path="monitors/new" element={<CreateMonitorScreen />} />
            <Route path="monitors/:id" element={<MonitorDetailScreen />} />
            <Route path="failures" element={<FailuresScreen />} />
            <Route path="runs/:id" element={<RunDetailScreen />} />
            <Route path="channels" element={<ChannelsScreen />} />
            <Route path="account" element={<AccountScreen />} />
            <Route path="api-keys" element={<ApiKeysScreen />} />
            <Route path="status-page" element={<StatusPageScreen />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
