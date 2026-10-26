import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { OpsProvider } from "./state/OpsContext";
import { ToastProvider } from "./parity/components/soc/ToastProvider";
import LoginPage from "./pages/LoginPage";
import OpsWorkspace from "./pages/OpsWorkspace";
import SocShell from "./components/SocShell";
import ParityScroll from "./components/ParityScroll";
import CustomersWall from "./pages/CustomersWall";
import CustomerMonitorShell from "./pages/CustomerMonitorShell";
import CustomerMonitor from "./pages/CustomerMonitor";
import PatchGapsPage from "./pages/PatchGapsPage";
import AlertsPage from "./parity/pages/AlertsPage";
import AlertDetailPage from "./parity/pages/AlertDetailPage";
import IncidentsPage from "./parity/pages/IncidentsPage";
import IncidentDetailPage from "./parity/pages/IncidentDetailPage";
import VulnerabilitiesPage from "./parity/pages/VulnerabilitiesPage";
import SecureEdgePage from "./parity/pages/SecureEdgePage";

function Private({ children }: { children: React.ReactNode }) {
  const { token, loading } = useAuth();
  if (loading) return <div className="login-wrap muted">Loading…</div>;
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function LegacyCustomerRedirect() {
  const { shortCode } = useParams<{ shortCode: string }>();
  return <Navigate to={`/monitor/${encodeURIComponent(shortCode || "")}`} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      {/* Standalone customer console — nested triage, no global feed/chat */}
      <Route
        path="/monitor/:shortCode"
        element={
          <Private>
            <ToastProvider>
              <CustomerMonitorShell />
            </ToastProvider>
          </Private>
        }
      >
        <Route index element={<CustomerMonitor />} />
        <Route
          path="alerts"
          element={
            <ParityScroll>
              <AlertsPage />
            </ParityScroll>
          }
        />
        <Route
          path="alerts/:alertId"
          element={
            <ParityScroll>
              <AlertDetailPage />
            </ParityScroll>
          }
        />
        <Route
          path="incidents"
          element={
            <ParityScroll>
              <IncidentsPage />
            </ParityScroll>
          }
        />
        <Route
          path="incidents/:incidentId"
          element={
            <ParityScroll>
              <IncidentDetailPage />
            </ParityScroll>
          }
        />
        <Route
          path="vulnerabilities"
          element={
            <ParityScroll>
              <VulnerabilitiesPage />
            </ParityScroll>
          }
        />
        <Route
          path="patch-gaps"
          element={
            <ParityScroll>
              <PatchGapsPage />
            </ParityScroll>
          }
        />
      </Route>
      <Route path="/customers/:shortCode" element={<LegacyCustomerRedirect />} />

      <Route
        path="/"
        element={
          <Private>
            <OpsProvider>
              <ToastProvider>
                <SocShell />
              </ToastProvider>
            </OpsProvider>
          </Private>
        }
      >
        <Route index element={<OpsWorkspace />} />
        <Route
          path="alerts"
          element={
            <ParityScroll>
              <AlertsPage />
            </ParityScroll>
          }
        />
        <Route
          path="alerts/:alertId"
          element={
            <ParityScroll>
              <AlertDetailPage />
            </ParityScroll>
          }
        />
        <Route
          path="incidents"
          element={
            <ParityScroll>
              <IncidentsPage />
            </ParityScroll>
          }
        />
        <Route
          path="incidents/:incidentId"
          element={
            <ParityScroll>
              <IncidentDetailPage />
            </ParityScroll>
          }
        />
        <Route
          path="vulnerabilities"
          element={
            <ParityScroll>
              <VulnerabilitiesPage />
            </ParityScroll>
          }
        />
        <Route
          path="events"
          element={
            <ParityScroll>
              <SecureEdgePage />
            </ParityScroll>
          }
        />
        <Route
          path="patch-gaps"
          element={
            <ParityScroll>
              <PatchGapsPage />
            </ParityScroll>
          }
        />
        <Route path="customers" element={<CustomersWall />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
