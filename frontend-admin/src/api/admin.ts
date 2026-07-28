import { downloadAuthenticated, request } from "./client";

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
  deployment_mode: TenantDeploymentMode;
  cloud_provider: TenantCloudProvider | null;
  primary_contact_name?: string | null;
  primary_contact_email?: string | null;
  primary_contact_phone?: string | null;
  country?: string | null;
  city?: string | null;
  industry?: string | null;
  contract_reference?: string | null;
  licensed_endpoints?: number | null;
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
  source_user?: string | null;
  ai_plain_summary: string | null;
  ai_likely_attack_type: string | null;
  customer_visible: boolean;
  status: string;
  created_at: string;
  /** KB-082 derived taxonomy (additive). */
  asset_category?: string;
  device_type?: string;
  asset_category_label?: string;
  contextual?: Record<string, unknown>;
}

export type AlertTaxonomyCounts = Record<string, number>;

export interface AlertTaxonomySummaryResponse {
  counts: AlertTaxonomyCounts;
  tree: unknown[];
  labels: Record<string, string>;
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
  asset_category?: string;
}

function withFilters(path: string, filters?: TriageListFilters): string {
  const params = new URLSearchParams();
  if (filters?.status) params.set("status", filters.status);
  if (filters?.severity) params.set("severity", filters.severity);
  if (filters?.tenant_id) params.set("tenant_id", filters.tenant_id);
  if (filters?.asset_category) params.set("asset_category", filters.asset_category);
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

export function getDashboard(): Promise<DashboardResponse> {
  return request<DashboardResponse>("/admin/dashboard");
}

export function getTenants(): Promise<TenantsListResponse> {
  return request<TenantsListResponse>("/admin/tenants");
}

/** KB-072: Wazuh/TheHive engine binding for a tenant. */
export interface TenantEngineBinding {
  tenant_id: string;
  wazuh_agent_group: string;
  wazuh_group_status: string;
  wazuh_last_error: string | null;
  wazuh_provisioned_at: string | null;
  thehive_org_name: string;
  thehive_tenant_tag: string;
  thehive_org_status: string;
  thehive_last_error: string | null;
  thehive_provisioned_at: string | null;
  last_provision_attempt_at: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

/** KB-065/KB-074/KB-075: full tenant detail (notes + profile + contract). */
export interface TenantOnboardResult {
  entitlements_saved: boolean;
  portal_user_created: boolean;
  portal_user_email: string | null;
  portal_user_error: string | null;
  service_readiness: Record<string, string>;
  next_steps: string[];
}

export interface TenantDetail extends Tenant {
  notes: string | null;
  updated_at: string;
  secondary_contact_name?: string | null;
  secondary_contact_email?: string | null;
  secondary_contact_phone?: string | null;
  billing_email?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  state_region?: string | null;
  postal_code?: string | null;
  website?: string | null;
  legal_name?: string | null;
  tax_id?: string | null;
  contract_reference?: string | null;
  contract_start_date?: string | null;
  contract_end_date?: string | null;
  licensed_endpoints?: number | null;
  data_residency?: string | null;
  preferred_language?: string | null;
  company_size?: string | null;
  engine_binding?: TenantEngineBinding | null;
  entitlements?: TenantEntitlements | null;
  onboard_result?: TenantOnboardResult | null;
}

export type TenantStatus = "onboarding" | "active" | "inactive" | "suspended";
export type TenantSlaLevel = "standard" | "business" | "premium" | "24x7";
export type TenantCriticality = "low" | "medium" | "high" | "critical";
export type TenantDeploymentMode =
  | "cloud"
  | "cloud_appliance"
  | "on_prem_direct"
  | "on_prem_appliance"
  | "hybrid";
export type TenantCloudProvider = "aws" | "azure" | "gcp" | "other";

export interface TenantEntitlementsOnCreate {
  wazuh_siem: boolean;
  wazuh_retention_days: number;
  thehive_mode: string;
  greenbone_enabled: boolean;
  greenbone_cadence: string;
  shuffle_mode: string;
  zeek_enabled: boolean;
  misp_enabled: boolean;
  velociraptor_enabled: boolean;
  roadmap_notes?: string | null;
}

export interface PortalAdminOnCreate {
  email: string;
  full_name: string;
  password: string;
  phone?: string | null;
}

export interface TenantCreateRequest {
  name: string;
  short_code: string;
  status?: TenantStatus;
  sla_level?: TenantSlaLevel;
  business_criticality?: TenantCriticality;
  timezone?: string;
  notes?: string | null;
  deployment_mode?: TenantDeploymentMode;
  cloud_provider?: TenantCloudProvider | null;
  primary_contact_name: string;
  primary_contact_email: string;
  primary_contact_phone?: string | null;
  secondary_contact_name?: string | null;
  secondary_contact_email?: string | null;
  secondary_contact_phone?: string | null;
  billing_email?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state_region?: string | null;
  postal_code?: string | null;
  country: string;
  website?: string | null;
  industry?: string | null;
  legal_name?: string | null;
  tax_id?: string | null;
  contract_reference?: string | null;
  contract_start_date?: string | null;
  contract_end_date?: string | null;
  licensed_endpoints?: number | null;
  data_residency?: string | null;
  preferred_language?: string | null;
  company_size?: string | null;
  entitlements?: TenantEntitlementsOnCreate;
  /** Required for every new customer onboard. */
  portal_admin: PortalAdminOnCreate;
}

export interface TenantUpdateRequest {
  name?: string;
  status?: TenantStatus;
  sla_level?: TenantSlaLevel;
  business_criticality?: TenantCriticality;
  timezone?: string;
  notes?: string | null;
  deployment_mode?: TenantDeploymentMode;
  cloud_provider?: TenantCloudProvider | null;
  primary_contact_name?: string | null;
  primary_contact_email?: string | null;
  primary_contact_phone?: string | null;
  secondary_contact_name?: string | null;
  secondary_contact_email?: string | null;
  secondary_contact_phone?: string | null;
  billing_email?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state_region?: string | null;
  postal_code?: string | null;
  country?: string | null;
  website?: string | null;
  industry?: string | null;
  legal_name?: string | null;
  tax_id?: string | null;
  contract_reference?: string | null;
  contract_start_date?: string | null;
  contract_end_date?: string | null;
  licensed_endpoints?: number | null;
  data_residency?: string | null;
  preferred_language?: string | null;
  company_size?: string | null;
}

export function getTenantDetail(tenantId: string): Promise<TenantDetail> {
  return request<TenantDetail>(`/admin/tenants/${encodeURIComponent(tenantId)}`);
}

export function createTenant(payload: TenantCreateRequest): Promise<TenantDetail> {
  return request<TenantDetail>("/admin/tenants", { method: "POST", body: payload });
}

export function updateTenant(
  tenantId: string,
  payload: TenantUpdateRequest
): Promise<TenantDetail> {
  return request<TenantDetail>(`/admin/tenants/${encodeURIComponent(tenantId)}`, {
    method: "PATCH",
    body: payload,
  });
}

export function getTenantEngineBinding(tenantId: string): Promise<TenantEngineBinding> {
  return request<TenantEngineBinding>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/engine-binding`
  );
}

export function provisionTenantEngines(tenantId: string): Promise<TenantEngineBinding> {
  return request<TenantEngineBinding>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/engine-provision`,
    { method: "POST" }
  );
}

export function backfillTenantEngineBindings(): Promise<{ count: number; message: string }> {
  return request<{ count: number; message: string }>("/admin/tenants/engine-provision/backfill", {
    method: "POST",
  });
}

export function getUsers(): Promise<UsersListResponse> {
  return request<UsersListResponse>("/admin/users");
}

export type PlatformRole =
  | "platform_admin"
  | "soc_manager"
  | "soc_analyst"
  | "customer_admin"
  | "customer_viewer";

export type UserStatus = "active" | "inactive" | "locked";

export interface UserCreateRequest {
  email: string;
  full_name: string;
  password: string;
  role: PlatformRole;
  tenant_id?: string | null;
  phone?: string | null;
  status?: UserStatus;
}

export interface UserUpdateRequest {
  full_name?: string;
  phone?: string | null;
  status?: UserStatus;
}

export interface UserPasswordUpdateRequest {
  new_password: string;
}

export function createUser(payload: UserCreateRequest): Promise<AdminUser> {
  return request<AdminUser>("/admin/users", { method: "POST", body: payload });
}

export function updateUser(userId: string, payload: UserUpdateRequest): Promise<AdminUser> {
  return request<AdminUser>(`/admin/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    body: payload,
  });
}

export function updateUserPassword(
  userId: string,
  payload: UserPasswordUpdateRequest
): Promise<AdminUser> {
  return request<AdminUser>(`/admin/users/${encodeURIComponent(userId)}/password`, {
    method: "PATCH",
    body: payload,
  });
}

export function getAppliances(): Promise<AppliancesListResponse> {
  return request<AppliancesListResponse>("/admin/appliances");
}

export function getAlerts(filters?: TriageListFilters): Promise<AlertsListResponse> {
  return request<AlertsListResponse>(withFilters("/admin/alerts", filters));
}

export function getAlertTaxonomySummary(
  filters?: Pick<TriageListFilters, "status" | "severity" | "tenant_id">
): Promise<AlertTaxonomySummaryResponse> {
  return request<AlertTaxonomySummaryResponse>(
    withFilters("/admin/alerts/taxonomy-summary", filters)
  );
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

export interface AdminRecommendation {
  id: string;
  tenant_name: string;
  short_code: string;
  title: string;
  priority: string;
  category: string;
  status: string;
  customer_visible: boolean;
  due_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface RecommendationsListResponse {
  recommendations: AdminRecommendation[];
}

export interface AdminNotification {
  id: string;
  tenant_name: string;
  short_code: string;
  notification_type: string;
  status: string;
  provider: string | null;
  message_preview: string;
  sent_at: string | null;
  delivered_at: string | null;
  created_at: string;
}

export interface NotificationsListResponse {
  notifications: AdminNotification[];
}

export function getRecommendations(): Promise<RecommendationsListResponse> {
  return request<RecommendationsListResponse>("/admin/recommendations");
}

export type RecommendationPriority = "low" | "medium" | "high" | "critical";
export type RecommendationStatus =
  | "open"
  | "in_progress"
  | "accepted_risk"
  | "completed"
  | "dismissed";

export interface RecommendationDetail extends AdminRecommendation {
  tenant_id: string;
  description: string;
  related_alert_id: string | null;
  related_incident_id: string | null;
  updated_at: string;
}

export interface RecommendationCreateRequest {
  tenant_id: string;
  title: string;
  description: string;
  priority?: RecommendationPriority;
  category?: string;
  status?: RecommendationStatus;
  customer_visible?: boolean;
  due_at?: string | null;
}

export interface RecommendationUpdateRequest {
  title?: string;
  description?: string;
  priority?: RecommendationPriority;
  category?: string;
  status?: RecommendationStatus;
  customer_visible?: boolean;
  due_at?: string | null;
}

export function getRecommendationDetail(id: string): Promise<RecommendationDetail> {
  return request<RecommendationDetail>(`/admin/recommendations/${encodeURIComponent(id)}`);
}

export function createRecommendation(
  payload: RecommendationCreateRequest
): Promise<RecommendationDetail> {
  return request<RecommendationDetail>("/admin/recommendations", {
    method: "POST",
    body: payload,
  });
}

export function updateRecommendation(
  id: string,
  payload: RecommendationUpdateRequest
): Promise<RecommendationDetail> {
  return request<RecommendationDetail>(`/admin/recommendations/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: payload,
  });
}

export function getNotifications(): Promise<NotificationsListResponse> {
  return request<NotificationsListResponse>("/admin/notifications");
}

export interface AdminReport {
  id: string;
  tenant_id: string;
  tenant_name: string;
  short_code: string;
  report_month: string;
  title: string;
  status: string;
  summary_preview?: string | null;
  published_at: string | null;
  created_at: string;
}

export interface ReportsListResponse {
  reports: AdminReport[];
}

export interface ReportSections {
  schema_version?: number;
  generated_at?: string | null;
  period?: Record<string, unknown>;
  cover?: Record<string, unknown>;
  posture?: Record<string, unknown>;
  detection?: Record<string, unknown>;
  incidents?: {
    opened?: number;
    closed?: number;
    still_open?: number;
    by_severity_opened?: Record<string, number>;
    notable?: Array<Record<string, string | null>>;
  };
  recommendations?: {
    open_count?: number;
    completed_count?: number;
    items?: Array<Record<string, string | null>>;
  };
  notifications?: Record<string, unknown>;
  narrative?: {
    period_highlights?: string;
    trends?: string;
    next_month_focus?: string;
    leadership_asks?: string;
  };
  deferred_kpis_note?: string;
}

export interface ReportDetail {
  id: string;
  tenant_id: string;
  tenant_name: string;
  short_code: string;
  report_month: string;
  title: string;
  status: string;
  executive_summary: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
  sections?: ReportSections | null;
}

export type ReportStatus = "draft" | "published" | "archived";

export interface ReportCreateRequest {
  tenant_id: string;
  report_month: string;
  executive_summary?: string | null;
  status?: ReportStatus;
  period_highlights?: string | null;
  trends?: string | null;
  next_month_focus?: string | null;
  leadership_asks?: string | null;
}

export interface ReportUpdateRequest {
  executive_summary?: string | null;
  status?: ReportStatus;
  period_highlights?: string | null;
  trends?: string | null;
  next_month_focus?: string | null;
  leadership_asks?: string | null;
}

export function getReports(): Promise<ReportsListResponse> {
  return request<ReportsListResponse>("/admin/reports");
}

export function getReportDetail(id: string): Promise<ReportDetail> {
  return request<ReportDetail>(`/admin/reports/${encodeURIComponent(id)}`);
}

export function createReport(payload: ReportCreateRequest): Promise<ReportDetail> {
  return request<ReportDetail>("/admin/reports", { method: "POST", body: payload });
}

export function updateReport(id: string, payload: ReportUpdateRequest): Promise<ReportDetail> {
  return request<ReportDetail>(`/admin/reports/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: payload,
  });
}

export function refreshReportMetrics(id: string): Promise<ReportDetail> {
  return request<ReportDetail>(`/admin/reports/${encodeURIComponent(id)}/refresh-metrics`, {
    method: "POST",
  });
}

export function downloadReportPdf(id: string): Promise<void> {
  return downloadAuthenticated(
    `/admin/reports/${encodeURIComponent(id)}/download.pdf`,
    `report-${id}.pdf`
  );
}

export function downloadReportXlsx(id: string): Promise<void> {
  return downloadAuthenticated(
    `/admin/reports/${encodeURIComponent(id)}/download.xlsx`,
    `report-${id}.xlsx`
  );
}

export interface AdminAsset {
  id: string;
  tenant_name: string;
  short_code: string;
  hostname: string | null;
  ip_address: string | null;
  asset_type: string;
  criticality: string;
  status: string;
  appliance_name: string | null;
  last_seen_at: string | null;
  created_at: string;
}

export interface AssetsListResponse {
  assets: AdminAsset[];
}

export type AssetType =
  | "server"
  | "workstation"
  | "firewall"
  | "network_device"
  | "application"
  | "database"
  | "other";
export type AssetCriticality = "low" | "medium" | "high" | "critical";
export type AssetStatus = "active" | "inactive" | "unknown";

export interface AssetDetail {
  id: string;
  tenant_id: string;
  tenant_name: string;
  short_code: string;
  appliance_id: string | null;
  appliance_name: string | null;
  hostname: string | null;
  ip_address: string | null;
  asset_type: string;
  os_name: string | null;
  criticality: string;
  owner: string | null;
  status: string;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AssetCreateRequest {
  tenant_id: string;
  hostname?: string | null;
  asset_type?: AssetType;
  criticality?: AssetCriticality;
  status?: AssetStatus;
  os_name?: string | null;
  owner?: string | null;
}

export interface AssetUpdateRequest {
  hostname?: string | null;
  asset_type?: AssetType;
  criticality?: AssetCriticality;
  status?: AssetStatus;
  os_name?: string | null;
  owner?: string | null;
}

export function getAssets(): Promise<AssetsListResponse> {
  return request<AssetsListResponse>("/admin/assets");
}

export function getAssetDetail(id: string): Promise<AssetDetail> {
  return request<AssetDetail>(`/admin/assets/${encodeURIComponent(id)}`);
}

export function createAsset(payload: AssetCreateRequest): Promise<AssetDetail> {
  return request<AssetDetail>("/admin/assets", { method: "POST", body: payload });
}

export function updateAsset(id: string, payload: AssetUpdateRequest): Promise<AssetDetail> {
  return request<AssetDetail>(`/admin/assets/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: payload,
  });
}

export interface AuditLog {
  id: string;
  tenant_name: string | null;
  short_code: string | null;
  actor_email: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  source_ip: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface AuditLogsListResponse {
  audit_logs: AuditLog[];
}

export function getAuditLogs(): Promise<AuditLogsListResponse> {
  return request<AuditLogsListResponse>("/admin/audit-logs");
}

export interface AuditEventCreateRequest {
  action: string;
  entity_type: string;
  entity_id?: string | null;
  tenant_id?: string | null;
  details?: Record<string, unknown>;
}

export function postAuditEvent(payload: AuditEventCreateRequest): Promise<{ audit_event: unknown }> {
  return request<{ audit_event: unknown }>("/admin/audit-events", {
    method: "POST",
    body: payload,
  });
}

/** KB-071: per-tenant service entitlement matrix. */
export interface TenantEntitlements {
  tenant_id: string;
  wazuh_siem: boolean;
  wazuh_retention_days: number;
  thehive_mode: string;
  greenbone_enabled: boolean;
  greenbone_cadence: string;
  shuffle_mode: string;
  zeek_enabled: boolean;
  misp_enabled: boolean;
  velociraptor_enabled: boolean;
  roadmap_notes: string | null;
  updated_at: string | null;
}

export type TenantEntitlementsUpdate = Partial<
  Omit<TenantEntitlements, "tenant_id" | "updated_at">
>;

export function getTenantEntitlements(tenantId: string): Promise<TenantEntitlements> {
  return request<TenantEntitlements>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/entitlements`
  );
}

export function putTenantEntitlements(
  tenantId: string,
  payload: TenantEntitlementsUpdate
): Promise<TenantEntitlements> {
  return request<TenantEntitlements>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/entitlements`,
    { method: "PUT", body: payload }
  );
}

export type ApplianceStatus =
  | "registered"
  | "online"
  | "offline"
  | "maintenance"
  | "retired";

export interface ApplianceUpdateRequest {
  appliance_name?: string;
  site_name?: string;
  status?: ApplianceStatus;
}

export function updateAppliance(
  applianceId: string,
  payload: ApplianceUpdateRequest
): Promise<Appliance> {
  return request<Appliance>(`/admin/appliances/${encodeURIComponent(applianceId)}`, {
    method: "PATCH",
    body: payload,
  });
}

/** KB-069: Admin vulnerability findings (Greenbone normalized). */
export interface AdminVulnerability {
  id: string;
  tenant_id: string;
  tenant_name: string;
  short_code: string;
  protected_asset_id: string | null;
  asset_hostname: string | null;
  source_platform: string;
  external_finding_id: string | null;
  cve_id: string | null;
  title: string;
  severity: string;
  status: string;
  recommendation_id: string | null;
  first_seen_at: string;
  last_seen_at: string;
  created_at: string;
  nvt_oid?: string | null;
  customer_safe_summary?: string | null;
  remediation_summary?: string | null;
  internal_notes?: string | null;
  updated_at?: string;
}

export interface VulnerabilitiesListResponse {
  vulnerabilities: AdminVulnerability[];
}

export function getVulnerabilities(params?: {
  source_platform?: string;
  tenant_short_code?: string;
}): Promise<VulnerabilitiesListResponse> {
  const qs = new URLSearchParams();
  if (params?.source_platform) qs.set("source_platform", params.source_platform);
  if (params?.tenant_short_code) qs.set("tenant_short_code", params.tenant_short_code);
  const q = qs.toString();
  return request<VulnerabilitiesListResponse>(
    `/admin/vulnerabilities${q ? `?${q}` : ""}`
  );
}

export function getVulnerabilityDetail(id: string): Promise<AdminVulnerability> {
  return request<AdminVulnerability>(`/admin/vulnerabilities/${encodeURIComponent(id)}`);
}

export interface VulnerabilityPromoteResponse {
  vulnerability_id: string;
  recommendation_id: string;
  created: boolean;
  customer_visible: boolean;
}

export function promoteVulnerabilityRecommendation(
  id: string,
  payload: { customer_visible?: boolean; title?: string; description?: string } = {}
): Promise<VulnerabilityPromoteResponse> {
  return request<VulnerabilityPromoteResponse>(
    `/admin/vulnerabilities/${encodeURIComponent(id)}/promote-recommendation`,
    { method: "POST", body: payload }
  );
}

/** KB-076: customer service upgrade / interest requests. */
export interface ServiceUpgradeRequestRow {
  id: string;
  tenant_id: string;
  tenant_name?: string | null;
  short_code?: string | null;
  requested_by_name?: string | null;
  service_key: string;
  preferred_cadence: string;
  scan_scope: string[];
  approximate_assets: number | null;
  environments: string[];
  urgency: string;
  compliance_drivers: string[];
  requirements_summary: string;
  preferred_contact: string;
  contact_phone: string | null;
  status: string;
  admin_notes?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface ApproveServiceUpgradeResponse {
  message: string;
  entitlements_updated: boolean;
  next_steps: string[];
  request: ServiceUpgradeRequestRow;
}

export function getServiceUpgradeRequests(): Promise<{ requests: ServiceUpgradeRequestRow[] }> {
  return request<{ requests: ServiceUpgradeRequestRow[] }>("/admin/service-upgrade-requests");
}

export function patchServiceUpgradeRequest(
  id: string,
  body: { status?: string; admin_notes?: string | null }
): Promise<ServiceUpgradeRequestRow> {
  return request<ServiceUpgradeRequestRow>(`/admin/service-upgrade-requests/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body,
  });
}

export function approveServiceUpgradeRequest(id: string): Promise<ApproveServiceUpgradeResponse> {
  return request<ApproveServiceUpgradeResponse>(
    `/admin/service-upgrade-requests/${encodeURIComponent(id)}/approve-enable`,
    { method: "POST" }
  );
}

export function declineServiceUpgradeRequest(id: string): Promise<ServiceUpgradeRequestRow> {
  return request<ServiceUpgradeRequestRow>(
    `/admin/service-upgrade-requests/${encodeURIComponent(id)}/decline`,
    { method: "POST" }
  );
}

