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
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
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
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
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
  enabled_services?: string[] | null;
}

export interface AppliancesListResponse {
  appliances: Appliance[];
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
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
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
}

export interface AlertDetail extends Alert {
  tenant_id: string;
  appliance_id: string | null;
  appliance_name: string | null;
  asset_id: string | null;
  asset_hostname: string | null;
  asset_type?: string | null;
  asset_os_name?: string | null;
  asset_ip?: string | null;
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
  asset_criticality?: string | null;
  asset_location?: string | null;
  asset_owner?: string | null;
  display_ip_address?: string | null;
  display_operating_system?: string | null;
  display_mac_address?: string | null;
  mac_address_status?: string | null;
  wazuh_rule_id?: string | null;
  wazuh_agent_id?: string | null;
}

export interface AlertDetailResponse {
  alert: AlertDetail;
}

export interface AlertTriageUpdate {
  status?: "new" | "triaged" | "incident_created" | "false_positive" | "closed";
  customer_visible?: boolean;
  ai_plain_summary?: string | null;
  ai_recommended_action?: string | null;
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
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
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
  primary_alert?: AlertDetail | null;
  timeline: IncidentTimelineEvent[];
  comments: IncidentComment[];
}

export interface IncidentTriageUpdate {
  status?: "open" | "in_progress" | "waiting_customer" | "resolved" | "closed";
  assigned_to_user_id?: string | null;
  customer_visible_summary?: string | null;
  customer_action_required?: string | null;
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
  q?: string;
  page?: number;
  page_size?: number;
  source_platform?: string;
  tenant_short_code?: string;
  scope?: string;
}

function withFilters(path: string, filters?: TriageListFilters): string {
  const params = new URLSearchParams();
  if (filters?.status) params.set("status", filters.status);
  if (filters?.severity) params.set("severity", filters.severity);
  if (filters?.tenant_id) params.set("tenant_id", filters.tenant_id);
  if (filters?.asset_category) params.set("asset_category", filters.asset_category);
  if (filters?.q) params.set("q", filters.q);
  if (filters?.page != null) params.set("page", String(filters.page));
  if (filters?.page_size != null) params.set("page_size", String(filters.page_size));
  if (filters?.source_platform) params.set("source_platform", filters.source_platform);
  if (filters?.tenant_short_code) params.set("tenant_short_code", filters.tenant_short_code);
  if (filters?.scope) params.set("scope", filters.scope);
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

export function getDashboard(): Promise<DashboardResponse> {
  return request<DashboardResponse>("/admin/dashboard");
}

export function getTenants(filters?: TriageListFilters): Promise<TenantsListResponse> {
  return request<TenantsListResponse>(withFilters("/admin/tenants", filters));
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

export function getTenantUsers(tenantId: string): Promise<UsersListResponse> {
  return request<UsersListResponse>(`/admin/tenants/${encodeURIComponent(tenantId)}/users`);
}

export function createTenantCustomerUser(
  tenantId: string,
  payload: Omit<UserCreateRequest, "tenant_id" | "status"> & { role: "customer_admin" | "customer_viewer" }
): Promise<AdminUser> {
  return request<AdminUser>(`/admin/tenants/${encodeURIComponent(tenantId)}/users`, {
    method: "POST",
    body: payload,
  });
}

export type TenantCustomerUserUpdate = {
  full_name?: string;
  phone?: string | null;
  role?: "customer_admin" | "customer_viewer";
  status?: UserStatus;
};

export function updateTenantCustomerUser(
  tenantId: string,
  userId: string,
  payload: TenantCustomerUserUpdate
): Promise<AdminUser> {
  return request<AdminUser>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/users/${encodeURIComponent(userId)}`,
    { method: "PATCH", body: payload }
  );
}

export function updateTenantCustomerUserPassword(
  tenantId: string,
  userId: string,
  payload: UserPasswordUpdateRequest
): Promise<{ status: string }> {
  return request<{ status: string }>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/users/${encodeURIComponent(userId)}/password`,
    { method: "PATCH", body: payload }
  );
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

export function getUsers(filters?: TriageListFilters): Promise<UsersListResponse> {
  return request<UsersListResponse>(withFilters("/admin/users", filters));
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

export function getAppliances(filters?: TriageListFilters): Promise<AppliancesListResponse> {
  return request<AppliancesListResponse>(withFilters("/admin/appliances", filters));
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
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
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
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
}

export function getRecommendations(filters?: TriageListFilters): Promise<RecommendationsListResponse> {
  return request<RecommendationsListResponse>(withFilters("/admin/recommendations", filters));
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

export function getNotifications(filters?: TriageListFilters): Promise<NotificationsListResponse> {
  return request<NotificationsListResponse>(withFilters("/admin/notifications", filters));
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
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
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

export function getReports(filters?: TriageListFilters): Promise<ReportsListResponse> {
  return request<ReportsListResponse>(withFilters("/admin/reports", filters));
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

export function downloadTenantAgentPackage(
  tenantId: string,
  osType: "windows" | "linux" | "all",
  shortCode?: string
): Promise<void> {
  const code = (shortCode || "tenant").toLowerCase().replace(/[^a-z0-9_-]/g, "");
  return downloadAuthenticated(
    `/admin/tenants/${encodeURIComponent(tenantId)}/agent-packages/${osType}`,
    `mssp-agent-${code}-${osType}.zip`
  );
}

export interface LinuxInstallCommandResponse {
  tenant_id?: string;
  tenant_name?: string;
  short_code: string;
  one_liner: string;
  script_url: string;
  wazuh_agent_group?: string;
  help?: string;
  rotated?: boolean;
}

export function getTenantLinuxInstallCommand(
  tenantId: string
): Promise<LinuxInstallCommandResponse> {
  return request<LinuxInstallCommandResponse>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/agent-install/linux`
  );
}

export function rotateTenantLinuxInstallCommand(
  tenantId: string
): Promise<LinuxInstallCommandResponse> {
  return request<LinuxInstallCommandResponse>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/agent-install/linux/rotate`,
    { method: "POST" }
  );
}

export interface AdminAsset {
  id: string;
  tenant_name: string;
  short_code: string;
  hostname: string | null;
  ip_address: string | null;
  asset_type: string;
  os_name?: string | null;
  criticality: string;
  status: string;
  appliance_name: string | null;
  last_seen_at: string | null;
  created_at: string;
}

export interface AssetsListResponse {
  assets: AdminAsset[];
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
}

export type AssetType =
  | "server"
  | "workstation"
  | "firewall"
  | "switch"
  | "load_balancer"
  | "network_device"
  | "application"
  | "database"
  | "other";
export type AssetCriticality = "low" | "medium" | "high" | "critical";
export type AssetStatus = "active" | "inactive" | "unknown";

export const ASSET_TYPE_LABELS: Record<AssetType, string> = {
  server: "Server",
  workstation: "Workstation",
  firewall: "Firewall",
  switch: "Switch",
  load_balancer: "Load balancer",
  network_device: "Network device",
  application: "Application",
  database: "Database",
  other: "Other",
};

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

export function getAssets(filters?: TriageListFilters): Promise<AssetsListResponse> {
  return request<AssetsListResponse>(withFilters("/admin/assets", filters));
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
  actor_role?: string | null;
  action: string;
  action_label?: string | null;
  summary?: string | null;
  portal?: string | null;
  entity_type: string;
  entity_id: string | null;
  resource_type?: string | null;
  resource_id?: string | null;
  source_ip: string | null;
  action_status?: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
  timestamp?: string;
}

export interface AuditLogsListResponse {
  audit_logs: AuditLog[];
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
}

export function getAuditLogs(params?: {
  tenant_short_code?: string;
  actor_email?: string;
  action_type?: string;
  q?: string;
  page?: number;
  page_size?: number;
  limit?: number;
}): Promise<AuditLogsListResponse> {
  const q = new URLSearchParams();
  if (params?.tenant_short_code) q.set("tenant_short_code", params.tenant_short_code);
  if (params?.actor_email) q.set("actor_email", params.actor_email);
  if (params?.action_type) q.set("action_type", params.action_type);
  if (params?.q) q.set("q", params.q);
  if (params?.page) q.set("page", String(params.page));
  if (params?.page_size) q.set("page_size", String(params.page_size));
  if (params?.limit) q.set("limit", String(params.limit));
  const qs = q.toString();
  return request<AuditLogsListResponse>(`/admin/audit-logs${qs ? `?${qs}` : ""}`);
}

export function getAuditLogDetail(auditId: string): Promise<{ audit_log: AuditLog }> {
  return request<{ audit_log: AuditLog }>(`/admin/audit-logs/${encodeURIComponent(auditId)}`);
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
  continuous_compliance_enabled?: boolean;
  external_attack_surface_enabled?: boolean;
  cloud_identity_protection_enabled?: boolean;
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
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
}

export function getVulnerabilities(params?: {
  source_platform?: string;
  tenant_short_code?: string;
  status?: string;
  q?: string;
  page?: number;
  page_size?: number;
}): Promise<VulnerabilitiesListResponse> {
  return request<VulnerabilitiesListResponse>(
    withFilters("/admin/vulnerabilities", {
      source_platform: params?.source_platform,
      tenant_short_code: params?.tenant_short_code,
      status: params?.status,
      q: params?.q,
      page: params?.page,
      page_size: params?.page_size,
    })
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
  requested_asset_ids?: string[];
  requested_assets?: Array<{
    id: string;
    hostname: string | null;
    asset_type: string;
    os_name: string | null;
    ip_address?: string | null;
  }>;
}

export interface ApproveServiceUpgradeResponse {
  message: string;
  entitlements_updated: boolean;
  next_steps: string[];
  request: ServiceUpgradeRequestRow;
  covered_asset_ids?: string[];
  covered_count?: number;
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

export function approveServiceUpgradeRequest(
  id: string,
  body?: { asset_ids?: string[] }
): Promise<ApproveServiceUpgradeResponse> {
  return request<ApproveServiceUpgradeResponse>(
    `/admin/service-upgrade-requests/${encodeURIComponent(id)}/approve-enable`,
    { method: "POST", body: body ?? {} }
  );
}

export function declineServiceUpgradeRequest(id: string): Promise<ServiceUpgradeRequestRow> {
  return request<ServiceUpgradeRequestRow>(
    `/admin/service-upgrade-requests/${encodeURIComponent(id)}/decline`,
    { method: "POST" }
  );
}

export interface AssetServiceCoverageAsset {
  id: string;
  hostname: string | null;
  asset_type: string;
  os_name: string | null;
  status: string;
  ip_address: string | null;
  covered: boolean;
}

export interface AssetServiceCoverageResponse {
  tenant_id: string;
  service_key: string;
  covered_asset_ids: string[];
  assets: AssetServiceCoverageAsset[];
  entitlements_updated?: boolean;
  message?: string;
}

export function getTenantAssetServiceCoverage(
  tenantId: string,
  serviceKey = "vulnerability_management"
): Promise<AssetServiceCoverageResponse> {
  return request<AssetServiceCoverageResponse>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/asset-service-coverage?service_key=${encodeURIComponent(serviceKey)}`
  );
}

export function putTenantAssetServiceCoverage(
  tenantId: string,
  body: {
    service_key?: string;
    asset_ids: string[];
    enable_entitlement?: boolean;
    greenbone_cadence?: string;
  }
): Promise<AssetServiceCoverageResponse> {
  return request<AssetServiceCoverageResponse>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/asset-service-coverage`,
    { method: "PUT", body }
  );
}

/** Service Catalog consultation requests (global + on-behalf). */
export type ConsultationRequestStatus =
  | "PENDING_CONSULTATION"
  | "UNDER_REVIEW"
  | "APPROVED"
  | "PROVISIONED"
  | "DECLINED"
  | "CLOSED";

export interface ConsultationRequest {
  id: string;
  tenant_id: string;
  tenant_name?: string | null;
  short_code?: string | null;
  service_key: string;
  service_name: string;
  pricing_tier?: string | null;
  endpoint_count?: number | null;
  m365_seat_count?: number | null;
  target_domains: string[];
  scope_notes: string;
  contact_name?: string | null;
  contact_email?: string | null;
  status: ConsultationRequestStatus | string;
  admin_notes?: string | null;
  email_dispatched_at?: string | null;
  created_at: string;
  updated_at?: string | null;
  requested_by_name?: string | null;
}

export interface ConsultationCreatePayload {
  service_key: string;
  service_name: string;
  pricing_tier?: string | null;
  endpoint_count?: number | null;
  m365_seat_count?: number | null;
  target_domains?: string[];
  scope_notes?: string;
  contact_name?: string | null;
  contact_email?: string | null;
  tenant_short_code: string;
}

export function getConsultationSummary(): Promise<{
  pending_consultation: number;
  under_review: number;
  unreviewed_total: number;
  resend_configured: boolean;
}> {
  return request("/admin/service-consultation-requests/summary");
}

export function listConsultationRequests(status?: string): Promise<{ requests: ConsultationRequest[] }> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  return request(`/admin/service-consultation-requests${q}`);
}

export function patchConsultationRequest(
  requestId: string,
  payload: { status?: ConsultationRequestStatus; admin_notes?: string }
): Promise<ConsultationRequest> {
  return request(`/admin/service-consultation-requests/${encodeURIComponent(requestId)}`, {
    method: "PATCH",
    body: payload,
  });
}

export function createConsultationRequestOnBehalf(
  payload: ConsultationCreatePayload
): Promise<ConsultationRequest> {
  return request("/admin/service-consultation-requests", {
    method: "POST",
    body: payload,
  });
}

/** Junexis Retrospective Engine + appliance command tile */
export interface ApplianceCommandSummary {
  engine: string;
  appliances: {
    total: number;
    online: number;
    offline: number;
    disk_used_gb_total: number;
    log_ingest_rate_total: number;
  };
  hunts: {
    running: number;
    pending: number;
    last_24h: number;
  };
}

export interface RetrospectiveHuntJob {
  id: string;
  tenant_id: string;
  short_code?: string;
  tenant_name?: string;
  execution_mode: string;
  status: string;
  lookback_days?: number;
  matches_count?: number;
  source?: string;
  created_at?: string | null;
  completed_at?: string | null;
}

export function getApplianceCommandSummary(): Promise<ApplianceCommandSummary> {
  return request("/admin/appliances/command-summary");
}

export function getRetrospectiveHunts(opts?: {
  status?: string;
  tenant_id?: string;
  page?: number;
  page_size?: number;
}): Promise<{ jobs: RetrospectiveHuntJob[]; engine?: string }> {
  const params = new URLSearchParams();
  if (opts?.status) params.set("status", opts.status);
  if (opts?.tenant_id) params.set("tenant_id", opts.tenant_id);
  if (opts?.page) params.set("page", String(opts.page));
  if (opts?.page_size) params.set("page_size", String(opts.page_size));
  const q = params.toString() ? `?${params.toString()}` : "";
  return request(`/admin/retrospective-hunts${q}`);
}

/** Threat Intelligence & Enrichment — admin ops (STIX / TAXII / IOC console). */
export interface ThreatIntelTenantSummary {
  tenant_id?: string;
  short_code: string;
  tenant_name: string;
  ioc_count: number;
  malicious_count: number;
  campaign_count: number;
  last_ioc_seen?: string | null;
}

export interface ThreatIntelIoc {
  id?: string;
  ioc_value: string;
  ioc_type: string;
  reputation_status?: string | null;
  confidence_score?: number | null;
  threat_actor?: string | null;
  summary?: string | null;
  mitre_tactic?: string | null;
  last_seen_in_tenant?: string | null;
}

export interface ThreatIntelCampaign {
  id?: string;
  name: string;
  summary?: string | null;
  threat_actor?: string | null;
  status?: string | null;
}

export function getThreatIntelAdminSummary(): Promise<{ tenants: ThreatIntelTenantSummary[] }> {
  return request("/admin/threat-intel/summary");
}

export function syncThreatIntelTenant(tenantRef: string): Promise<Record<string, unknown>> {
  return request(`/admin/threat-intel/${encodeURIComponent(tenantRef)}/sync`, {
    method: "POST",
    body: {},
  });
}

export function getThreatIntelTenantIocs(
  tenantRef: string,
  opts?: { ioc_type?: string; reputation_status?: string; page_size?: number }
): Promise<{ iocs: ThreatIntelIoc[]; pagination?: Record<string, number> }> {
  const params = new URLSearchParams();
  if (opts?.ioc_type) params.set("ioc_type", opts.ioc_type);
  if (opts?.reputation_status) params.set("reputation_status", opts.reputation_status);
  if (opts?.page_size) params.set("page_size", String(opts.page_size));
  const q = params.toString() ? `?${params.toString()}` : "";
  return request(`/admin/threat-intel/${encodeURIComponent(tenantRef)}/iocs${q}`);
}

export function getThreatIntelTenantCampaigns(
  tenantRef: string
): Promise<{ campaigns: ThreatIntelCampaign[] }> {
  return request(`/admin/threat-intel/${encodeURIComponent(tenantRef)}/campaigns`);
}

export function ingestStixBundle(
  tenantRef: string,
  bundle: Record<string, unknown>
): Promise<Record<string, unknown>> {
  return request(`/admin/threat-intel/${encodeURIComponent(tenantRef)}/stix-ingest`, {
    method: "POST",
    body: { bundle },
  });
}

export function pullTaxiiFeed(
  tenantRef: string,
  payload: {
    api_root?: string;
    collection_id?: string;
    username?: string;
    password?: string;
    use_configured_feed?: boolean;
  }
): Promise<Record<string, unknown>> {
  return request(`/admin/threat-intel/${encodeURIComponent(tenantRef)}/taxii-pull`, {
    method: "POST",
    body: payload,
  });
}

