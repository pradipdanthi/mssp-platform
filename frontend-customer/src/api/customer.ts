import { request } from "./client";

// Customer portal API helpers — ONLY /customer/* paths. Never platform-admin routes.

export interface CustomerTenant {
  id: string;
  name: string;
  short_code: string;
  status?: string;
  sla_level?: string;
  business_criticality?: string;
  timezone?: string;
}

export interface SecuritySummary {
  appliances: number;
  online_appliances: number;
  open_incidents: number;
  high_or_critical_open_incidents: number;
  open_recommendations: number;
}

export interface ApplianceHealth {
  appliance_name: string;
  site_name: string;
  status: string;
  last_seen_at: string | null;
  health_status: string | null;
  cpu_percent: number | null;
  memory_percent: number | null;
  disk_percent: number | null;
  heartbeat_at: string | null;
}

export interface CustomerIncident {
  incident_number: string;
  title: string;
  severity: string;
  status: string;
  customer_visible_summary: string | null;
  business_impact?: string | null;
  customer_action_required: string | boolean | null;
  resolution_summary?: string | null;
  opened_at: string | null;
  resolved_at?: string | null;
  closed_at?: string | null;
}

export interface CustomerIncidentTimelineEvent {
  event_type: string;
  title: string;
  created_at: string | null;
}

export interface CustomerIncidentDetailResponse {
  tenant: CustomerTenant;
  incident: CustomerIncident;
  timeline: CustomerIncidentTimelineEvent[];
  related_alerts: CustomerAlert[];
}

export interface CustomerRecommendation {
  title: string;
  description: string | null;
  priority: string;
  category: string | null;
  status: string;
  due_at: string | null;
}

export interface MonthlyReport {
  report_month: string;
  status: string;
  executive_summary: string | null;
  metrics: unknown;
  published_at: string | null;
}

export interface CustomerDashboardResponse {
  tenant: CustomerTenant;
  security_summary: SecuritySummary;
  appliance_health: ApplianceHealth[];
  open_incidents: CustomerIncident[];
  recommendations: CustomerRecommendation[];
  monthly_reports: MonthlyReport[];
}

export interface CustomerIncidentsResponse {
  tenant: CustomerTenant;
  incidents: CustomerIncident[];
}

export interface CustomerAlert {
  alert_id: string;
  title: string;
  severity: string;
  status: string;
  source: string;
  summary: string | null;
  description: string | null;
  detected_at: string | null;
  hostname: string | null;
}

export interface CustomerAlertsResponse {
  tenant: CustomerTenant;
  alerts: CustomerAlert[];
}

export function getCustomerDashboard(shortCode: string): Promise<CustomerDashboardResponse> {
  return request<CustomerDashboardResponse>(`/customer/dashboard/${encodeURIComponent(shortCode)}`);
}

export function getCustomerIncidents(shortCode: string): Promise<CustomerIncidentsResponse> {
  return request<CustomerIncidentsResponse>(`/customer/incidents/${encodeURIComponent(shortCode)}`);
}

export function getCustomerIncidentDetail(
  shortCode: string,
  incidentNumber: string
): Promise<CustomerIncidentDetailResponse> {
  return request<CustomerIncidentDetailResponse>(
    `/customer/incidents/${encodeURIComponent(shortCode)}/${encodeURIComponent(incidentNumber)}`
  );
}

export function getCustomerAlerts(shortCode: string): Promise<CustomerAlertsResponse> {
  return request<CustomerAlertsResponse>(`/customer/alerts/${encodeURIComponent(shortCode)}`);
}

export interface CustomerAppliance {
  appliance_name: string;
  site_name: string;
  status: string;
  last_seen_at: string | null;
  health_status: string | null;
  cpu_percent: number | null;
  memory_percent: number | null;
  disk_percent: number | null;
  agent_version: string | null;
}

export interface CustomerProtectedAsset {
  asset_id: string;
  hostname: string | null;
  asset_type: string;
  criticality: string;
  status: string;
  os_name: string | null;
  owner: string | null;
  last_seen_at: string | null;
  appliance_name: string | null;
  site_name: string | null;
}

export interface CustomerAssetsResponse {
  tenant: CustomerTenant;
  appliances: CustomerAppliance[];
  assets: CustomerProtectedAsset[];
}

export function getCustomerAssets(shortCode: string): Promise<CustomerAssetsResponse> {
  return request<CustomerAssetsResponse>(`/customer/assets/${encodeURIComponent(shortCode)}`);
}

export interface CustomerReport {
  report_id: string;
  report_month: string;
  status: string;
  title: string;
  summary: string | null;
  created_at: string | null;
  published_at: string | null;
}

export interface CustomerReportsResponse {
  tenant: CustomerTenant;
  reports: CustomerReport[];
}

export function getCustomerReports(shortCode: string): Promise<CustomerReportsResponse> {
  return request<CustomerReportsResponse>(`/customer/reports/${encodeURIComponent(shortCode)}`);
}
