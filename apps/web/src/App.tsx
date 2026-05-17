import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "@/auth/AuthProvider";
import { RequireAuth } from "@/auth/RequireAuth";
import { AppShell } from "@/components/AppShell";
import { AccountScreen } from "@/screens/AccountScreen";
import { AuthCallbackScreen } from "@/screens/AuthCallbackScreen";
import { ChannelsScreen } from "@/screens/ChannelsScreen";
import { CreateMonitorScreen } from "@/screens/CreateMonitorScreen";
import { FailuresScreen } from "@/screens/FailuresScreen";
import { LoginScreen } from "@/screens/LoginScreen";
import { MonitorDetailScreen } from "@/screens/MonitorDetailScreen";
import { MonitorsScreen } from "@/screens/MonitorsScreen";
import { OverviewScreen } from "@/screens/OverviewScreen";
import { RunDetailScreen } from "@/screens/RunDetailScreen";

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginScreen />} />
          <Route path="/auth/callback" element={<AuthCallbackScreen />} />

          <Route
            element={
              <RequireAuth>
                <AppShell />
              </RequireAuth>
            }
          >
            <Route index element={<OverviewScreen />} />
            <Route path="monitors" element={<MonitorsScreen />} />
            <Route path="monitors/new" element={<CreateMonitorScreen />} />
            <Route
              path="monitors/:id"
              element={<MonitorDetailScreen />}
            />
            <Route path="failures" element={<FailuresScreen />} />
            <Route path="runs/:id" element={<RunDetailScreen />} />
            <Route path="channels" element={<ChannelsScreen />} />
            <Route path="account" element={<AccountScreen />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
