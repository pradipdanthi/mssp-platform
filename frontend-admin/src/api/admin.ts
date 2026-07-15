import { request } from "./client";

// The shapes below mirror the SQL column lists in
// backend-api/app/api/routes/admin.py exactly (KB-018 planning read that
// file to confirm every field name/type). That file is read-only for this
// module - these types describe it, they do not change it.

export interface DashboardOverview {
  total_tenants: number;
  active_tenants: number;
  total_appliances: number;
  online_appliances: number;
  offline_appliances: number;
  protected_assets: number;
  total_alerts: number;
  high_or_critical_alerts: number;
  new_alerts: number;
  total_incidents: number;
  open_incidents: number;
  open_recommendations: number;
  notifications_sent: number;
}

export interface SeverityBreakdownRow {
  severity: string;
  count: number;
}

export interface TenantRiskRow {
  name: string;
  short_code: string;
  sla_level: string;
  business_criticality: string;
  appliances: number;
  online_appliances: number;
  alerts: number;
  high_or_critical_alerts: number;
  incidents: number;
  open_incidents: number;
}

export interface DashboardResponse {
  overview: DashboardOverview;
  severity_breakdown: SeverityBreakdownRow[];
  tenant_risk_summary: TenantRiskRow[];
}

export interface Tenant {
  id: string;
  name: string;
  short_code: string;
  status: string;
  sla_level: string;
  business_criticality: string;
  timezone: string;
  created_at: string;
  appliances: number;
  protected_assets: number;
  incidents: number;
}

export interface TenantsListResponse {
  tenants: Tenant[];
}

export interface AdminUser {
  id: string;
  tenant_id: string | null;
  user_type: string;
  role: string;
  full_name: string;
  email: string;
  phone: string | null;
  status: string;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
  // Intentionally no password / password_hash field - the backend never
  // returns one, and this type must not invent a place to render it.
}

export interface UsersListResponse {
  users: AdminUser[];
}

export interface Appliance {
  id: string;
  tenant_name: string;
  short_code: string;
  appliance_name: string;
  site_name: string;
  status: string;
  agent_version: string | null;
  config_version: string | null;
  update_status: string | null;
  local_ip: string | null;
  last_source_ip: string | null;
  last_seen_at: string | null;
  health_status: string | null;
  cpu_percent: number | null;
  memory_percent: number | null;
  disk_percent: number | null;
  heartbeat_at: string | null;
}

export interface AppliancesListResponse {
  appliances: Appliance[];
}

export interface Alert {
  id: string;
  tenant_name: string;
  short_code: string;
  external_alert_id: string | null;
  source_tool: string | null;
  severity: string;
  alert_title: string;
  source_ip: string | null;
  destination_ip: string | null;
  destination_host: string | null;
  ai_plain_summary: string | null;
  ai_likely_attack_type: string | null;
  customer_visible: boolean;
  status: string;
  created_at: string;
}

export interface AlertsListResponse {
  alerts: Alert[];
}

export interface Incident {
  id: string;
  tenant_name: string;
  short_code: string;
  incident_number: string;
  title: string;
  severity: string;
  status: string;
  assigned_to: string | null;
  customer_visible_summary: string | null;
  customer_action_required: boolean;
  opened_at: string | null;
  created_at: string;
}

export interface IncidentsListResponse {
  incidents: Incident[];
}

export function getDashboard(): Promise<DashboardResponse> {
  return request<DashboardResponse>("/admin/dashboard");
}

export function getTenants(): Promise<TenantsListResponse> {
  return request<TenantsListResponse>("/admin/tenants");
}

export function getUsers(): Promise<UsersListResponse> {
  return request<UsersListResponse>("/admin/users");
}

export function getAppliances(): Promise<AppliancesListResponse> {
  return request<AppliancesListResponse>("/admin/appliances");
}

export function getAlerts(): Promise<AlertsListResponse> {
  return request<AlertsListResponse>("/admin/alerts");
}

export function getIncidents(): Promise<IncidentsListResponse> {
  return request<IncidentsListResponse>("/admin/incidents");
}
