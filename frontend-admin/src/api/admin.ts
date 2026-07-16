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

export interface AlertDetail extends Alert {
  tenant_id: string;
  appliance_id: string | null;
  appliance_name: string | null;
  asset_id: string | null;
  asset_hostname: string | null;
  alert_description: string | null;
  event_time: string | null;
  source_user: string | null;
  raw_event: Record<string, unknown>;
  ai_technical_summary: string | null;
  ai_business_impact: string | null;
  ai_recommended_action: string | null;
  ai_false_positive_score: number | null;
  mitre_mapping: Record<string, unknown>;
  updated_at: string;
}

export interface AlertDetailResponse {
  alert: AlertDetail;
}

export interface AlertTriageUpdate {
  status?: "new" | "triaged" | "incident_created" | "false_positive" | "closed";
  customer_visible?: boolean;
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
  customer_action_required: string | null;
  opened_at: string | null;
  created_at: string;
}

export interface IncidentsListResponse {
  incidents: Incident[];
}

export interface IncidentTimelineEvent {
  id: string;
  event_type: string;
  visibility: "internal" | "customer";
  title: string;
  details: string | null;
  created_by_user_id: string | null;
  created_by: string | null;
  created_at: string;
}

export interface IncidentComment {
  id: string;
  visibility: "internal" | "customer";
  comment_text: string;
  created_by_user_id: string | null;
  created_by: string | null;
  created_at: string;
}

export interface IncidentDetail extends Incident {
  tenant_id: string;
  primary_alert_id: string | null;
  assigned_to_user_id: string | null;
  business_impact: string | null;
  customer_action_required: string | null;
  resolution_summary: string | null;
  internal_notes: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  updated_at: string;
}

export interface IncidentDetailResponse {
  incident: IncidentDetail;
  timeline: IncidentTimelineEvent[];
  comments: IncidentComment[];
}

export interface IncidentTriageUpdate {
  status?: "open" | "in_progress" | "waiting_customer" | "resolved" | "closed";
  assigned_to_user_id?: string | null;
  customer_visible_summary?: string | null;
}

export interface IncidentCommentCreate {
  comment_text: string;
  visibility: "internal" | "customer";
}

export interface IncidentCommentResponse {
  comment: IncidentComment;
}

export interface TriageListFilters {
  status?: string;
  severity?: string;
  tenant_id?: string;
}

function withFilters(path: string, filters?: TriageListFilters): string {
  const params = new URLSearchParams();
  if (filters?.status) params.set("status", filters.status);
  if (filters?.severity) params.set("severity", filters.severity);
  if (filters?.tenant_id) params.set("tenant_id", filters.tenant_id);
  const query = params.toString();
  return query ? `${path}?${query}` : path;
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

export function getAlerts(filters?: TriageListFilters): Promise<AlertsListResponse> {
  return request<AlertsListResponse>(withFilters("/admin/alerts", filters));
}

export function getAlertDetail(alertId: string): Promise<AlertDetailResponse> {
  return request<AlertDetailResponse>(`/admin/alerts/${encodeURIComponent(alertId)}`);
}

export function updateAlertTriage(
  alertId: string,
  update: AlertTriageUpdate
): Promise<AlertDetailResponse> {
  return request<AlertDetailResponse>(`/admin/alerts/${encodeURIComponent(alertId)}`, {
    method: "PATCH",
    body: update,
  });
}

export function getIncidents(filters?: TriageListFilters): Promise<IncidentsListResponse> {
  return request<IncidentsListResponse>(withFilters("/admin/incidents", filters));
}

export function getIncidentDetail(incidentId: string): Promise<IncidentDetailResponse> {
  return request<IncidentDetailResponse>(`/admin/incidents/${encodeURIComponent(incidentId)}`);
}

export function updateIncidentTriage(
  incidentId: string,
  update: IncidentTriageUpdate
): Promise<IncidentDetailResponse> {
  return request<IncidentDetailResponse>(`/admin/incidents/${encodeURIComponent(incidentId)}`, {
    method: "PATCH",
    body: update,
  });
}

export function addIncidentComment(
  incidentId: string,
  comment: IncidentCommentCreate
): Promise<IncidentCommentResponse> {
  return request<IncidentCommentResponse>(
    `/admin/incidents/${encodeURIComponent(incidentId)}/comments`,
    { method: "POST", body: comment }
  );
}
