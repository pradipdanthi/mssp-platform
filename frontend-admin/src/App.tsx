import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { useBrand } from "./config/BrandContext";
import ProtectedRoute from "./components/ProtectedRoute";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import TenantsPage from "./pages/TenantsPage";
import UsersPage from "./pages/UsersPage";
import AppliancesPage from "./pages/AppliancesPage";
import ApplianceDetailPage from "./pages/ApplianceDetailPage";
import AlertsPage from "./pages/AlertsPage";
import IncidentsPage from "./pages/IncidentsPage";
import AlertDetailPage from "./pages/AlertDetailPage";
import IncidentDetailPage from "./pages/IncidentDetailPage";
import RecommendationsPage from "./pages/RecommendationsPage";
import VulnerabilitiesPage from "./pages/VulnerabilitiesPage";
import NotificationsPage from "./pages/NotificationsPage";
import ReportsPage from "./pages/ReportsPage";
import AssetsPage from "./pages/AssetsPage";
import AuditLogsPage from "./pages/AuditLogsPage";
import AuditLogDetailPage from "./pages/AuditLogDetailPage";
import ServiceCatalogPage from "./pages/ServiceCatalogPage";
import ServiceRequestsPage from "./pages/ServiceRequestsPage";
import RetrospectiveHuntsPage from "./pages/RetrospectiveHuntsPage";
import ThreatIntelAdminPage from "./pages/ThreatIntelAdminPage";
import AiAssistantPage from "./pages/AiAssistantPage";
import CompliancePage from "./pages/CompliancePage";

function RootRedirect() {
  const { token, loading } = useAuth();
  const brand = useBrand();
  if (loading) {
    return <div className="app-loading">Loading {brand.portalName}...</div>;
  }
  return <Navigate to={token ? "/dashboard" : "/login"} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<RootRedirect />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <DashboardPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/tenants"
        element={
          <ProtectedRoute>
            <TenantsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/users"
        element={
          <ProtectedRoute>
            <UsersPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/appliances"
        element={
          <ProtectedRoute>
            <AppliancesPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/appliances/:applianceId"
        element={
          <ProtectedRoute>
            <ApplianceDetailPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/alerts"
        element={
          <ProtectedRoute>
            <AlertsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/alerts/:alertId"
        element={
          <ProtectedRoute>
            <AlertDetailPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/incidents"
        element={
          <ProtectedRoute>
            <IncidentsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/incidents/:incidentId"
        element={
          <ProtectedRoute>
            <IncidentDetailPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/vulnerabilities"
        element={
          <ProtectedRoute>
            <VulnerabilitiesPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/compliance"
        element={
          <ProtectedRoute>
            <CompliancePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/recommendations"
        element={
          <ProtectedRoute>
            <RecommendationsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/notifications"
        element={
          <ProtectedRoute>
            <NotificationsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/reports"
        element={
          <ProtectedRoute>
            <ReportsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/assets"
        element={
          <ProtectedRoute>
            <AssetsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/audit"
        element={
          <ProtectedRoute>
            <AuditLogsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/audit/:auditId"
        element={
          <ProtectedRoute>
            <AuditLogDetailPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/services"
        element={
          <ProtectedRoute>
            <ServiceCatalogPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/service-requests"
        element={
          <ProtectedRoute>
            <ServiceRequestsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/retrospective-hunts"
        element={
          <ProtectedRoute>
            <RetrospectiveHuntsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/threat-intel"
        element={
          <ProtectedRoute>
            <ThreatIntelAdminPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/ai-assistant"
        element={
          <ProtectedRoute>
            <AiAssistantPage />
          </ProtectedRoute>
        }
      />
      {/* Unknown routes redirect safely rather than showing a raw 404. */}
      <Route path="*" element={<RootRedirect />} />
    </Routes>
  );
}
