import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { useBrand } from "./config/BrandContext";
import ProtectedRoute from "./components/ProtectedRoute";
import EntitlementGate from "./components/EntitlementGate";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import AlertsPage from "./pages/AlertsPage";
import AlertDetailPage from "./pages/AlertDetailPage";
import IncidentsPage from "./pages/IncidentsPage";
import IncidentDetailPage from "./pages/IncidentDetailPage";
import AssetsPage from "./pages/AssetsPage";
import AssetDetailPage from "./pages/AssetDetailPage";
import ApplianceDetailPage from "./pages/ApplianceDetailPage";
import ReportsPage from "./pages/ReportsPage";
import ReportDetailPage from "./pages/ReportDetailPage";
import RecommendationsPage from "./pages/RecommendationsPage";
import RecommendationDetailPage from "./pages/RecommendationDetailPage";
import NotificationsPage from "./pages/NotificationsPage";
import AccountPage from "./pages/AccountPage";
import UsersPage from "./pages/UsersPage";
import AuditLogsPage from "./pages/AuditLogsPage";
import AuditLogDetailPage from "./pages/AuditLogDetailPage";
import VulnerabilitiesPage from "./pages/VulnerabilitiesPage";
import CompliancePage from "./pages/CompliancePage";
import EasmPage from "./pages/EasmPage";
import ItdrPage from "./pages/ItdrPage";
import NdrPage from "./pages/NdrPage";
import ThreatIntelPage from "./pages/ThreatIntelPage";
import ThreatLensPage from "./pages/ThreatLensPage";
import ForensicsPage from "./pages/ForensicsPage";
import ServicesPage from "./pages/ServicesPage";

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
        path="/incidents/:incidentNumber"
        element={
          <ProtectedRoute>
            <IncidentDetailPage />
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
        path="/assets/:assetId"
        element={
          <ProtectedRoute>
            <AssetDetailPage />
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
        path="/reports"
        element={
          <ProtectedRoute>
            <ReportsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/reports/:reportId"
        element={
          <ProtectedRoute>
            <ReportDetailPage />
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
        path="/recommendations/:recommendationId"
        element={
          <ProtectedRoute>
            <RecommendationDetailPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/services"
        element={
          <ProtectedRoute>
            <ServicesPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/vulnerabilities"
        element={
          <ProtectedRoute>
            <EntitlementGate require="vulnerability_management">
              <VulnerabilitiesPage />
            </EntitlementGate>
          </ProtectedRoute>
        }
      />
      <Route
        path="/vulnerability"
        element={
          <ProtectedRoute>
            <EntitlementGate require="vulnerability_management">
              <VulnerabilitiesPage />
            </EntitlementGate>
          </ProtectedRoute>
        }
      />
      <Route
        path="/compliance"
        element={
          <ProtectedRoute>
            <EntitlementGate require="continuous_compliance">
              <CompliancePage />
            </EntitlementGate>
          </ProtectedRoute>
        }
      />
      <Route
        path="/easm"
        element={
          <ProtectedRoute>
            <EntitlementGate require="external_attack_surface">
              <EasmPage />
            </EntitlementGate>
          </ProtectedRoute>
        }
      />
      <Route
        path="/itdr"
        element={
          <ProtectedRoute>
            <EntitlementGate require="cloud_identity_protection">
              <ItdrPage />
            </EntitlementGate>
          </ProtectedRoute>
        }
      />
      <Route
        path="/ndr"
        element={
          <ProtectedRoute>
            <EntitlementGate require="network_detection">
              <NdrPage />
            </EntitlementGate>
          </ProtectedRoute>
        }
      />
      <Route
        path="/network"
        element={
          <ProtectedRoute>
            <EntitlementGate require="network_detection">
              <NdrPage />
            </EntitlementGate>
          </ProtectedRoute>
        }
      />
      <Route
        path="/threat-intel"
        element={
          <ProtectedRoute>
            <EntitlementGate require="threat_intelligence">
              <ThreatIntelPage />
            </EntitlementGate>
          </ProtectedRoute>
        }
      />
      <Route
        path="/threatlens"
        element={
          <ProtectedRoute>
            <EntitlementGate require="threatlens">
              <ThreatLensPage />
            </EntitlementGate>
          </ProtectedRoute>
        }
      />
      <Route
        path="/forensics"
        element={
          <ProtectedRoute>
            <EntitlementGate require="endpoint_forensics">
              <ForensicsPage />
            </EntitlementGate>
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
        path="/users"
        element={
          <ProtectedRoute>
            <UsersPage />
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
        path="/account"
        element={
          <ProtectedRoute>
            <AccountPage />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<RootRedirect />} />
    </Routes>
  );
}
