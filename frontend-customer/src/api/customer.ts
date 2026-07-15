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
  customer_action_required: boolean;
  resolution_summary?: string | null;
  opened_at: string | null;
  resolved_at?: string | null;
  closed_at?: string | null;
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

export function getCustomerDashboard(shortCode: string): Promise<CustomerDashboardResponse> {
  return request<CustomerDashboardResponse>(`/customer/dashboard/${encodeURIComponent(shortCode)}`);
}

export function getCustomerIncidents(shortCode: string): Promise<CustomerIncidentsResponse> {
  return request<CustomerIncidentsResponse>(`/customer/incidents/${encodeURIComponent(shortCode)}`);
}
