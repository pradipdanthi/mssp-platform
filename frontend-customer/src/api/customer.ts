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
}

export function getCustomerNotifications(
  shortCode: string
): Promise<CustomerNotificationsResponse> {
  return request<CustomerNotificationsResponse>(
    `/customer/notifications/${encodeURIComponent(shortCode)}`
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
}

export function getCustomerRecommendations(
  shortCode: string
): Promise<CustomerRecommendationsResponse> {
  return request<CustomerRecommendationsResponse>(
    `/customer/recommendations/${encodeURIComponent(shortCode)}`
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

const OPEN_INCIDENT_STATUSES = new Set(["open", "in_progress", "waiting_customer"]);
const OPEN_RECOMMENDATION_STATUSES = new Set(["open", "in_progress"]);
const HIGH_CRITICAL_SEVERITIES = new Set(["high", "critical"]);

export async function getCustomerDashboardV2(
  shortCode: string
): Promise<CustomerDashboardV2Response> {
  const [incidentsRes, alertsRes, recommendationsRes, assetsRes, reportsRes] =
    await Promise.all([
      getCustomerIncidents(shortCode),
      getCustomerAlerts(shortCode),
      getCustomerRecommendations(shortCode),
      getCustomerAssets(shortCode),
      getCustomerReports(shortCode),
    ]);

  const tenant =
    incidentsRes.tenant ??
    alertsRes.tenant ??
    recommendationsRes.tenant ??
    assetsRes.tenant ??
    reportsRes.tenant;

  const openIncidents = incidentsRes.incidents.filter((i) =>
    OPEN_INCIDENT_STATUSES.has(i.status)
  );
  const highCriticalAlerts = alertsRes.alerts.filter((a) =>
    HIGH_CRITICAL_SEVERITIES.has(a.severity)
  );
  const openRecommendations = recommendationsRes.recommendations.filter((r) =>
    OPEN_RECOMMENDATION_STATUSES.has(r.status)
  );
  const appliancesOnline = assetsRes.appliances.filter((a) => a.status === "online");
  const appliancesOther = assetsRes.appliances.filter((a) => a.status !== "online");

  return {
    tenant,
    kpis: {
      open_incidents: openIncidents.length,
      high_critical_alerts: highCriticalAlerts.length,
      open_recommendations: openRecommendations.length,
      assets_monitored: assetsRes.assets.length,
      appliances_online: appliancesOnline.length,
      appliances_other: appliancesOther.length,
    },
    recent_incidents: incidentsRes.incidents.slice(0, 5),
    recent_recommendations: recommendationsRes.recommendations.slice(0, 5),
    recent_alerts: alertsRes.alerts.slice(0, 5),
    latest_report: reportsRes.reports.length > 0 ? reportsRes.reports[0] : null,
    recent_appliances: assetsRes.appliances.slice(0, 5),
  };
}
