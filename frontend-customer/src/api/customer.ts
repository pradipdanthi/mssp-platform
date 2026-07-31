import { downloadAuthenticated, request } from "./client";

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
  hostname?: string | null;
  asset_category?: string | null;
  asset_category_label?: string | null;
  device_type?: string | null;
  operating_system?: string | null;
  recommended_action?: string | null;
  likely_attack_type?: string | null;
  criticality?: string | null;
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
  primary_alert?: CustomerAlert | null;
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
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
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
  asset_category?: string | null;
  asset_category_label?: string | null;
  device_type?: string | null;
  operating_system?: string | null;
  business_impact?: string | null;
  recommended_action?: string | null;
  likely_attack_type?: string | null;
  criticality?: string | null;
}

export interface CustomerAlertsResponse {
  tenant: CustomerTenant;
  alerts: CustomerAlert[];
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
}

export interface CustomerListFilters {
  status?: string;
  severity?: string;
  q?: string;
  page?: number;
  page_size?: number;
}

function withCustomerListFilters(path: string, filters?: CustomerListFilters): string {
  const params = new URLSearchParams();
  if (filters?.status) params.set("status", filters.status);
  if (filters?.severity) params.set("severity", filters.severity);
  if (filters?.q) params.set("q", filters.q);
  if (filters?.page != null) params.set("page", String(filters.page));
  if (filters?.page_size != null) params.set("page_size", String(filters.page_size));
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

export function getCustomerDashboard(shortCode: string): Promise<CustomerDashboardResponse> {
  return request<CustomerDashboardResponse>(`/customer/dashboard/${encodeURIComponent(shortCode)}`);
}

export function getCustomerIncidents(
  shortCode: string,
  filters?: CustomerListFilters
): Promise<CustomerIncidentsResponse> {
  return request<CustomerIncidentsResponse>(
    withCustomerListFilters(`/customer/incidents/${encodeURIComponent(shortCode)}`, filters)
  );
}

export function getCustomerIncidentDetail(
  shortCode: string,
  incidentNumber: string
): Promise<CustomerIncidentDetailResponse> {
  return request<CustomerIncidentDetailResponse>(
    `/customer/incidents/${encodeURIComponent(shortCode)}/${encodeURIComponent(incidentNumber)}`
  );
}

export function getCustomerAlerts(
  shortCode: string,
  filters?: CustomerListFilters
): Promise<CustomerAlertsResponse> {
  return request<CustomerAlertsResponse>(
    withCustomerListFilters(`/customer/alerts/${encodeURIComponent(shortCode)}`, filters)
  );
}

export interface CustomerAlertDetailResponse {
  tenant: CustomerTenant;
  alert: CustomerAlert;
}

export function getCustomerAlertDetail(
  shortCode: string,
  alertId: string
): Promise<CustomerAlertDetailResponse> {
  return request<CustomerAlertDetailResponse>(
    `/customer/alerts/${encodeURIComponent(shortCode)}/${encodeURIComponent(alertId)}`
  );
}

export interface CustomerAppliance {
  appliance_id: string;
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
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
}

export function getCustomerAssets(
  shortCode: string,
  filters?: CustomerListFilters
): Promise<CustomerAssetsResponse> {
  return request<CustomerAssetsResponse>(
    withCustomerListFilters(`/customer/assets/${encodeURIComponent(shortCode)}`, filters)
  );
}

export interface CustomerAssetDetailResponse {
  tenant: CustomerTenant;
  asset: CustomerProtectedAsset;
}

export function getCustomerAssetDetail(
  shortCode: string,
  assetId: string
): Promise<CustomerAssetDetailResponse> {
  return request<CustomerAssetDetailResponse>(
    `/customer/assets/${encodeURIComponent(shortCode)}/${encodeURIComponent(assetId)}`
  );
}

export interface CustomerApplianceLinkedAsset {
  asset_id: string;
  hostname: string | null;
  asset_type: string;
  criticality: string;
  status: string;
  last_seen_at: string | null;
}

export interface CustomerApplianceDetail {
  appliance_id: string;
  appliance_name: string;
  site_name: string;
  status: string;
  last_seen_at: string | null;
  health_status: string | null;
  cpu_percent: number | null;
  memory_percent: number | null;
  disk_percent: number | null;
  agent_version: string | null;
  config_version: string | null;
  update_status: string | null;
  latest_heartbeat_at: string | null;
  protected_assets_count: number;
  protected_assets: CustomerApplianceLinkedAsset[];
}

export interface CustomerApplianceDetailResponse {
  tenant: CustomerTenant;
  appliance: CustomerApplianceDetail;
}

export function getCustomerApplianceDetail(
  shortCode: string,
  applianceId: string
): Promise<CustomerApplianceDetailResponse> {
  return request<CustomerApplianceDetailResponse>(
    `/customer/appliances/${encodeURIComponent(shortCode)}/${encodeURIComponent(applianceId)}`
  );
}

export interface CustomerReport {
  report_id: string;
  report_month: string;
  status: string;
  title: string;
  summary: string | null;
  created_at: string | null;
  published_at: string | null;
  sections?: Record<string, unknown> | null;
}

export interface CustomerReportsResponse {
  tenant: CustomerTenant;
  reports: CustomerReport[];
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
}

export function getCustomerReports(
  shortCode: string,
  filters?: CustomerListFilters
): Promise<CustomerReportsResponse> {
  return request<CustomerReportsResponse>(
    withCustomerListFilters(`/customer/reports/${encodeURIComponent(shortCode)}`, filters)
  );
}

export interface CustomerReportDetailResponse {
  tenant: CustomerTenant;
  report: CustomerReport;
}

export function getCustomerReportDetail(
  shortCode: string,
  reportId: string
): Promise<CustomerReportDetailResponse> {
  return request<CustomerReportDetailResponse>(
    `/customer/reports/${encodeURIComponent(shortCode)}/${encodeURIComponent(reportId)}`
  );
}

export function downloadCustomerReportPdf(shortCode: string, reportId: string): Promise<void> {
  return downloadAuthenticated(
    `/customer/reports/${encodeURIComponent(shortCode)}/${encodeURIComponent(reportId)}/download.pdf`,
    `report-${reportId}.pdf`
  );
}

export function downloadCustomerReportXlsx(shortCode: string, reportId: string): Promise<void> {
  return downloadAuthenticated(
    `/customer/reports/${encodeURIComponent(shortCode)}/${encodeURIComponent(reportId)}/download.xlsx`,
    `report-${reportId}.xlsx`
  );
}

/** KB-086: download endpoint monitoring agent installer for this tenant. */
export function downloadCustomerAgentPackage(
  shortCode: string,
  osType: "windows" | "linux" | "all"
): Promise<void> {
  return downloadAuthenticated(
    `/customer/agent-packages/${encodeURIComponent(shortCode)}/${osType}`,
    `mssp-agent-${osType}.zip`
  );
}

export interface CustomerLinuxInstallCommand {
  short_code: string;
  one_liner: string;
  script_url: string;
  help?: string;
}

export function getCustomerLinuxInstallCommand(
  shortCode: string
): Promise<CustomerLinuxInstallCommand> {
  return request<CustomerLinuxInstallCommand>(
    `/customer/agent-install/${encodeURIComponent(shortCode)}/linux`
  );
}

export interface CustomerNotification {
  notification_id: string;
  notification_type: string;
  status: string;
  message_body: string;
  sent_at: string | null;
  delivered_at: string | null;
  created_at: string | null;
}

export interface CustomerNotificationsResponse {
  tenant: CustomerTenant;
  notifications: CustomerNotification[];
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
}

export function getCustomerNotifications(
  shortCode: string,
  filters?: CustomerListFilters
): Promise<CustomerNotificationsResponse> {
  return request<CustomerNotificationsResponse>(
    withCustomerListFilters(`/customer/notifications/${encodeURIComponent(shortCode)}`, filters)
  );
}

export interface CustomerRecommendationItem {
  recommendation_id: string;
  title: string;
  description: string;
  priority: string;
  category: string;
  status: string;
  due_at: string | null;
  completed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CustomerRecommendationsResponse {
  tenant: CustomerTenant;
  recommendations: CustomerRecommendationItem[];
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
}

export function getCustomerRecommendations(
  shortCode: string,
  filters?: CustomerListFilters
): Promise<CustomerRecommendationsResponse> {
  return request<CustomerRecommendationsResponse>(
    withCustomerListFilters(`/customer/recommendations/${encodeURIComponent(shortCode)}`, filters)
  );
}

export interface CustomerRecommendationDetailResponse {
  tenant: CustomerTenant;
  recommendation: CustomerRecommendationItem;
}

export function getCustomerRecommendationDetail(
  shortCode: string,
  recommendationId: string
): Promise<CustomerRecommendationDetailResponse> {
  return request<CustomerRecommendationDetailResponse>(
    `/customer/recommendations/${encodeURIComponent(shortCode)}/${encodeURIComponent(recommendationId)}`
  );
}

/** KB-028: client-side dashboard composition — only /customer/* dedicated APIs. */
export interface CustomerDashboardV2Kpis {
  open_incidents: number;
  high_critical_alerts: number;
  open_recommendations: number;
  assets_monitored: number;
  appliances_online: number;
  appliances_other: number;
}

export interface CustomerDashboardV2Response {
  tenant: CustomerTenant;
  kpis: CustomerDashboardV2Kpis;
  recent_incidents: CustomerIncident[];
  recent_recommendations: CustomerRecommendationItem[];
  recent_alerts: CustomerAlert[];
  latest_report: CustomerReport | null;
  recent_appliances: CustomerAppliance[];
}

export async function getCustomerDashboardV2(
  shortCode: string
): Promise<CustomerDashboardV2Response> {
  const [
    openIncidentsRes,
    recentIncidentsRes,
    urgentAlertsRes,
    recentAlertsRes,
    recommendationsRes,
    openRecsRes,
    inProgressRecsRes,
    assetsRes,
    reportsRes,
  ] = await Promise.all([
    getCustomerIncidents(shortCode, { status: "open", page: 1, page_size: 5 }),
    getCustomerIncidents(shortCode, { page: 1, page_size: 5 }),
    getCustomerAlerts(shortCode, { severity: "urgent", page: 1, page_size: 5 }),
    getCustomerAlerts(shortCode, { page: 1, page_size: 5 }),
    getCustomerRecommendations(shortCode, { page: 1, page_size: 5 }),
    getCustomerRecommendations(shortCode, { status: "open", page: 1, page_size: 1 }),
    getCustomerRecommendations(shortCode, { status: "in_progress", page: 1, page_size: 1 }),
    getCustomerAssets(shortCode, { page: 1, page_size: 1 }),
    getCustomerReports(shortCode, { page: 1, page_size: 5 }),
  ]);

  const tenant =
    recentIncidentsRes.tenant ??
    recentAlertsRes.tenant ??
    recommendationsRes.tenant ??
    assetsRes.tenant ??
    reportsRes.tenant;

  const appliancesOnline = assetsRes.appliances.filter((a) => a.status === "online");
  const appliancesOther = assetsRes.appliances.filter((a) => a.status !== "online");

  return {
    tenant,
    kpis: {
      open_incidents: openIncidentsRes.total ?? openIncidentsRes.incidents.length,
      high_critical_alerts: urgentAlertsRes.total ?? urgentAlertsRes.alerts.length,
      open_recommendations: (openRecsRes.total ?? 0) + (inProgressRecsRes.total ?? 0),
      assets_monitored: assetsRes.total ?? assetsRes.assets.length,
      appliances_online: appliancesOnline.length,
      appliances_other: appliancesOther.length,
    },
    recent_incidents: recentIncidentsRes.incidents.slice(0, 5),
    recent_recommendations: recommendationsRes.recommendations.slice(0, 5),
    recent_alerts: recentAlertsRes.alerts.slice(0, 5),
    latest_report: reportsRes.reports.length > 0 ? reportsRes.reports[0] : null,
    recent_appliances: assetsRes.appliances.slice(0, 5),
  };
}

/** KB-071: customer-facing service entitlements (never /admin). */
export interface CustomerEntitlements {
  tenant_id: string;
  log_monitoring_enabled: boolean;
  log_retention_days: number;
  incident_response: string;
    vulnerability_management_enabled: boolean;
  vulnerability_scan_cadence: string;
  continuous_compliance_enabled?: boolean;
  external_attack_surface_enabled?: boolean;
  cloud_identity_protection_enabled?: boolean;
  security_automation: string;
  network_traffic_analysis_enabled?: boolean;
  threat_intelligence_enabled?: boolean;
  endpoint_forensics_enabled?: boolean;
  updated_at?: string | null;
}

export function getCustomerEntitlements(shortCode: string): Promise<CustomerEntitlements> {
  return request<CustomerEntitlements>(
    `/customer/entitlements/${encodeURIComponent(shortCode)}`
  );
}

/** KB-079: customer-safe vulnerability service summary (no raw scanner output). */
export interface VulnerabilityServiceSummary {
  tenant: { short_code: string; name: string };
  service_active: boolean;
  cadence: string;
  published_open_recommendations: number;
  last_scan_activity_at: string | null;
}

export function getVulnerabilityServiceSummary(
  shortCode: string
): Promise<VulnerabilityServiceSummary> {
  return request<VulnerabilityServiceSummary>(
    `/customer/vulnerabilities/${encodeURIComponent(shortCode)}/summary`
  );
}

/** VMaaS — MSSP Internal Vulnerability Scanner (customer-safe). */
export interface VmaasSummary {
  tenant: { short_code: string; name: string };
  critical_cves: number;
  high_risk_vulnerabilities: number;
  medium_count: number;
  low_count: number;
  open_findings: number;
  unpatched_assets: number;
  average_cvss_score: number;
  posture_score: number;
  top_vulnerable_hosts: { host: string; open_findings: number; high_critical: number }[];
  has_data: boolean;
  scanner_label?: string;
  last_scan?: {
    status?: string;
    findings_count?: number;
    risk_score?: number;
    completed_at?: string | null;
  } | null;
}

export interface VmaasFinding {
  id: string;
  asset_host: string;
  cve_id?: string | null;
  title: string;
  cvss_score?: number | null;
  severity: string;
  vulnerable_package_or_port?: string | null;
  description: string;
  remediation: string;
  status: string;
}

export function getVmaasSummary(shortCode: string): Promise<VmaasSummary> {
  return request(`/customer/vmaas/${encodeURIComponent(shortCode)}/summary`);
}

export function getVmaasFindings(
  shortCode: string,
  opts?: { severity?: string; status?: string; cve_id?: string; page?: number; page_size?: number }
): Promise<{
  findings: VmaasFinding[];
  pagination: { page: number; page_size: number; total_items: number; total_pages: number };
}> {
  const params = new URLSearchParams();
  if (opts?.severity) params.set("severity", opts.severity);
  if (opts?.status) params.set("status", opts.status);
  if (opts?.cve_id) params.set("cve_id", opts.cve_id);
  if (opts?.page) params.set("page", String(opts.page));
  if (opts?.page_size) params.set("page_size", String(opts.page_size));
  const q = params.toString() ? `?${params.toString()}` : "";
  return request(`/customer/vmaas/${encodeURIComponent(shortCode)}/findings${q}`);
}

export function requestVmaasScan(
  shortCode: string,
  payload?: { target_range?: string }
): Promise<{ scan_status: string; findings_count?: number; summary?: VmaasSummary }> {
  return request(`/customer/vmaas/${encodeURIComponent(shortCode)}/scan`, {
    method: "POST",
    body: payload || {},
  });
}

/** Network Detection & Response (NDR) — customer-safe. */
export interface NdrSummary {
  tenant: { short_code: string; name: string };
  active_network_sensors: number;
  total_sensors: number;
  high_risk_network_alerts: number;
  monitored_flows: number;
  monitored_bytes: number;
  protocol_anomaly_count: number;
  lateral_movement_count?: number;
  c2_beaconing_count?: number;
  port_scan_count?: number;
  open_events: number;
  has_data: boolean;
  engine_label?: string;
}

export interface NdrEvent {
  id: string;
  source_endpoint_label: string;
  destination_endpoint_label: string;
  source_port?: number | null;
  destination_port?: number | null;
  protocol: string;
  event_category: string;
  severity: string;
  signature_title: string;
  mitre_technique?: string | null;
  flow_bytes?: number;
  summary: string;
  remediation: string;
  detected_at?: string;
}

export interface NdrSensor {
  id: string;
  sensor_name: string;
  sensor_status: string;
  sensor_type_label: string;
  capture_interface?: string | null;
  flows_observed: number;
  bytes_observed: number;
  last_heartbeat?: string | null;
}

export function getNdrSummary(shortCode: string): Promise<NdrSummary> {
  return request(`/customer/ndr/${encodeURIComponent(shortCode)}/summary`);
}

export function getNdrEvents(
  shortCode: string,
  opts?: {
    severity?: string;
    event_category?: string;
    protocol?: string;
    page?: number;
    page_size?: number;
  }
): Promise<{
  events: NdrEvent[];
  pagination: { page: number; page_size: number; total_items: number; total_pages: number };
}> {
  const params = new URLSearchParams();
  if (opts?.severity) params.set("severity", opts.severity);
  if (opts?.event_category) params.set("event_category", opts.event_category);
  if (opts?.protocol) params.set("protocol", opts.protocol);
  if (opts?.page) params.set("page", String(opts.page));
  if (opts?.page_size) params.set("page_size", String(opts.page_size));
  const q = params.toString() ? `?${params.toString()}` : "";
  return request(`/customer/ndr/${encodeURIComponent(shortCode)}/events${q}`);
}

export function getNdrSensors(shortCode: string): Promise<{ sensors: NdrSensor[] }> {
  return request(`/customer/ndr/${encodeURIComponent(shortCode)}/sensors`);
}

/** Continuous Compliance & Hardening (CaaS) — customer-safe. */
export interface ComplianceFrameworkScore {
  score_percentage: number;
  passed_checks: number;
  failed_checks: number;
  total_checks: number;
}

export interface ComplianceSummary {
  tenant: { short_code: string; name: string };
  overall_score_percentage: number;
  passed_checks: number;
  failed_checks: number;
  total_checks: number;
  agent_count: number;
  policy_count: number;
  framework_scores: Record<string, ComplianceFrameworkScore>;
  last_evaluated_at?: string | null;
  last_synced_at?: string | null;
  sync_status?: string;
  has_data: boolean;
  message?: string | null;
}

export interface ComplianceEvaluation {
  id: string;
  endpoint_name: string;
  policy_id: string;
  title: string;
  description?: string;
  pass_count: number;
  fail_count: number;
  total_checks: number;
  score: number;
  compliance_frameworks: string[];
  last_evaluated_at?: string | null;
  updated_at?: string | null;
}

export interface ComplianceCheckItem {
  id: string;
  check_id: string;
  rule_title: string;
  status: string;
  severity: string;
  rationale: string;
  remediation: string;
  compliance_frameworks: string[];
  policy_title?: string;
  endpoint_name?: string;
  updated_at?: string | null;
}

export function getComplianceSummary(
  shortCode: string,
  refresh = false
): Promise<ComplianceSummary> {
  const q = refresh ? "?refresh=true" : "";
  return request<ComplianceSummary>(
    `/customer/compliance/${encodeURIComponent(shortCode)}/summary${q}`
  );
}

export function getComplianceEvaluations(
  shortCode: string
): Promise<{ tenant: { short_code: string; name: string }; evaluations: ComplianceEvaluation[] }> {
  return request(
    `/customer/compliance/${encodeURIComponent(shortCode)}/evaluations`
  );
}

export function getComplianceChecks(
  shortCode: string,
  opts?: { status?: string; framework?: string; page?: number; page_size?: number }
): Promise<{
  checks: ComplianceCheckItem[];
  pagination: {
    page: number;
    page_size: number;
    total_items: number;
    total_pages: number;
  };
}> {
  const params = new URLSearchParams();
  if (opts?.status) params.set("status", opts.status);
  if (opts?.framework) params.set("framework", opts.framework);
  if (opts?.page) params.set("page", String(opts.page));
  if (opts?.page_size) params.set("page_size", String(opts.page_size));
  const q = params.toString() ? `?${params.toString()}` : "";
  return request(`/customer/compliance/${encodeURIComponent(shortCode)}/checks${q}`);
}

export function getComplianceReportUrl(shortCode: string): string {
  return `/api/customer/compliance/${encodeURIComponent(shortCode)}/report`;
}

/** External Attack Surface Management (EASM) — customer-safe. */
export interface EasmSummary {
  tenant: { short_code: string; name: string };
  total_external_assets: number;
  primary_domains: number;
  subdomains: number;
  public_ips: number;
  open_public_ports: number;
  expiring_ssl_certificates: number;
  perimeter_vulnerabilities: number;
  open_findings: number;
  high_critical_findings: number;
  has_data: boolean;
  scanner_label?: string;
  last_scan?: {
    scan_status?: string;
    target_domain?: string;
    completed_at?: string | null;
    ssl_status?: string | null;
  } | null;
}

export interface EasmAsset {
  id: string;
  domain_or_ip: string;
  asset_type: string;
  discovery_source_label: string;
  first_seen?: string;
  last_seen?: string;
  status: string;
}

export interface EasmFinding {
  id: string;
  asset_name: string;
  finding_type: string;
  severity: string;
  title: string;
  description: string;
  remediation: string;
  created_at?: string;
}

export function getEasmSummary(shortCode: string): Promise<EasmSummary> {
  return request(`/customer/easm/${encodeURIComponent(shortCode)}/summary`);
}

export function getEasmAssets(shortCode: string): Promise<{ assets: EasmAsset[] }> {
  return request(`/customer/easm/${encodeURIComponent(shortCode)}/assets`);
}

export function getEasmFindings(
  shortCode: string,
  opts?: { severity?: string; page?: number; page_size?: number }
): Promise<{
  findings: EasmFinding[];
  pagination: { page: number; page_size: number; total_items: number; total_pages: number };
}> {
  const params = new URLSearchParams();
  if (opts?.severity) params.set("severity", opts.severity);
  if (opts?.page) params.set("page", String(opts.page));
  if (opts?.page_size) params.set("page_size", String(opts.page_size));
  const q = params.toString() ? `?${params.toString()}` : "";
  return request(`/customer/easm/${encodeURIComponent(shortCode)}/findings${q}`);
}

export function registerEasmDomain(
  shortCode: string,
  payload: { domain_or_ip: string; notes?: string; start_scan?: boolean }
): Promise<{ asset: EasmAsset; scan?: unknown }> {
  return request(`/customer/easm/${encodeURIComponent(shortCode)}/domains`, {
    method: "POST",
    body: payload,
  });
}

/** Cloud & Identity Threat Protection (ITDR) — customer-safe. */
export interface ItdrSummary {
  tenant: { short_code: string; name: string };
  monitored_cloud_seats: number;
  connected_providers: number;
  identity_threat_alerts: number;
  suspicious_logins: number;
  risky_mail_rules: number;
  impossible_travel?: number;
  mfa_bypass_attempts?: number;
  rogue_admin_assignments?: number;
  high_critical_findings: number;
  identity_posture_score: number;
  last_synced_at?: string | null;
  has_data: boolean;
  engine_label?: string;
}

export interface ItdrEvent {
  id: string;
  user_principal_name: string;
  event_type: string;
  severity: string;
  location_country?: string | null;
  location_city?: string | null;
  title: string;
  summary: string;
  remediation: string;
  detected_at?: string;
}

export interface ItdrConfig {
  id: string;
  provider_label: string;
  tenant_domain: string;
  display_name?: string | null;
  status: string;
  monitored_seat_count: number;
  last_synced_at?: string | null;
}

export function getItdrSummary(shortCode: string): Promise<ItdrSummary> {
  return request(`/customer/itdr/${encodeURIComponent(shortCode)}/summary`);
}

export function getItdrEvents(
  shortCode: string,
  opts?: { severity?: string; event_type?: string; user?: string; page?: number; page_size?: number }
): Promise<{
  events: ItdrEvent[];
  pagination: { page: number; page_size: number; total_items: number; total_pages: number };
}> {
  const params = new URLSearchParams();
  if (opts?.severity) params.set("severity", opts.severity);
  if (opts?.event_type) params.set("event_type", opts.event_type);
  if (opts?.user) params.set("user", opts.user);
  if (opts?.page) params.set("page", String(opts.page));
  if (opts?.page_size) params.set("page_size", String(opts.page_size));
  const q = params.toString() ? `?${params.toString()}` : "";
  return request(`/customer/itdr/${encodeURIComponent(shortCode)}/events${q}`);
}

export function getItdrConfigs(shortCode: string): Promise<{ configs: ItdrConfig[] }> {
  return request(`/customer/itdr/${encodeURIComponent(shortCode)}/configs`);
}

export function connectItdrProvider(
  shortCode: string,
  payload: {
    provider?: string;
    tenant_domain: string;
    display_name?: string;
    monitored_seat_count?: number;
    run_sync?: boolean;
  }
): Promise<{ config: { id: string; tenant_domain: string; status: string }; sync?: unknown }> {
  return request(`/customer/itdr/${encodeURIComponent(shortCode)}/connect`, {
    method: "POST",
    body: payload,
  });
}

/** KB-076: customer service upgrade / interest request. */
export type ServiceUpgradeServiceKey =
  | "vulnerability_management"
  | "network_traffic_analysis"
  | "threat_intelligence"
  | "endpoint_forensics"
  | "security_automation"
  | "other";

export interface ServiceUpgradeRequestPayload {
  service_key?: ServiceUpgradeServiceKey;
  preferred_cadence: "weekly" | "monthly" | "quarterly" | "unsure";
  scan_scope: string[];
  approximate_assets?: number | null;
  environments: string[];
  urgency: "exploring" | "planning" | "needed_soon" | "urgent";
  compliance_drivers: string[];
  requirements_summary: string;
  preferred_contact: "email" | "phone" | "either";
  contact_phone?: string | null;
  requested_asset_ids?: string[];
}

export interface ServiceUpgradeRequest {
  id: string;
  tenant_id: string;
  tenant_name?: string | null;
  short_code?: string | null;
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
  created_at: string;
  requested_by_name?: string | null;
  requested_asset_ids?: string[];
  requested_assets?: Array<{
    id: string;
    hostname: string | null;
    asset_type: string;
    os_name: string | null;
  }>;
}

export function createServiceUpgradeRequest(
  shortCode: string,
  payload: ServiceUpgradeRequestPayload
): Promise<ServiceUpgradeRequest> {
  return request<ServiceUpgradeRequest>(
    `/customer/service-upgrade-requests/${encodeURIComponent(shortCode)}`,
    { method: "POST", body: payload }
  );
}

export function listServiceUpgradeRequests(
  shortCode: string
): Promise<{ requests: ServiceUpgradeRequest[] }> {
  return request<{ requests: ServiceUpgradeRequest[] }>(
    `/customer/service-upgrade-requests/${encodeURIComponent(shortCode)}`
  );
}

/** Service Catalog consultation / upgrade requests (email + ticket pipeline). */
export type ConsultationServiceKey =
  | "log_event_monitoring"
  | "incident_response"
  | "security_automation"
  | "vulnerability_management"
  | "continuous_compliance"
  | "network_detection_response"
  | "threat_intelligence"
  | "endpoint_forensics_deception"
  | "external_attack_surface"
  | "cloud_identity_protection"
  | "other";

export type ConsultationRequestStatus =
  | "PENDING_CONSULTATION"
  | "UNDER_REVIEW"
  | "APPROVED"
  | "PROVISIONED"
  | "DECLINED"
  | "CLOSED";

export interface ConsultationRequestPayload {
  service_key: ConsultationServiceKey;
  service_name: string;
  pricing_tier?: string | null;
  endpoint_count?: number | null;
  m365_seat_count?: number | null;
  target_domains?: string[];
  scope_notes?: string;
  contact_name?: string | null;
  contact_email?: string | null;
}

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
  email_dispatched_at?: string | null;
  created_at: string;
  updated_at?: string | null;
  requested_by_name?: string | null;
}

export function createConsultationRequest(
  shortCode: string,
  payload: ConsultationRequestPayload
): Promise<ConsultationRequest> {
  return request<ConsultationRequest>(
    `/customer/service-consultation-requests/${encodeURIComponent(shortCode)}`,
    { method: "POST", body: payload }
  );
}

export function listConsultationRequests(
  shortCode: string
): Promise<{ requests: ConsultationRequest[] }> {
  return request<{ requests: ConsultationRequest[] }>(
    `/customer/service-consultation-requests/${encodeURIComponent(shortCode)}`
  );
}
