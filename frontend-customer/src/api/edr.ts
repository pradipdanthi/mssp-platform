import { request } from "./client";

export type EdrActionType =
  | "ISOLATE_HOST"
  | "KILL_PROCESS"
  | "COLLECT_FORENSICS"
  | "BLOCK_HASH";

export interface ProcessTreeNode {
  pid?: number | null;
  parent_pid?: number | null;
  process_name?: string | null;
  command_line?: string | null;
  user?: string | null;
  hash_sha256?: string | null;
  child_processes: ProcessTreeNode[];
}

export interface ProcessTreeResponse {
  incident_id?: string | null;
  alert_id?: string | null;
  root?: ProcessTreeNode | null;
  events_considered: number;
  message?: string | null;
}

export interface EdrDeepDive {
  incident_number: string;
  endpoint: Record<string, unknown>;
  mitre: { tactics: string[]; techniques: { id: string; name: string }[] };
  process_tree: ProcessTreeResponse;
  recent_actions: EdrActionRow[];
}

export interface EdrActionRow {
  execution_id: string;
  status: "pending" | "executed" | "failed";
  action_type: EdrActionType;
  result_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface EdrMetricsSummary {
  mean_time_to_contain_seconds?: number | null;
  telemetry_events_processed: number;
  isolated_endpoints_count: number;
}

export function getEdrDeepDive(
  incidentNumber: string,
  tenantShortCode?: string
): Promise<EdrDeepDive> {
  const params = new URLSearchParams({ incident_number: incidentNumber });
  if (tenantShortCode) params.set("tenant_short_code", tenantShortCode);
  return request(`/v1/edr/incidents/deep-dive?${params.toString()}`);
}

export function executeEdrAction(body: {
  action_type: EdrActionType;
  tenant_short_code: string;
  incident_number?: string;
  agent_id?: string;
  pid?: number;
  file_hash_sha256?: string;
  confirm_isolation?: boolean;
}): Promise<{ execution_id: string; status: string; message: string }> {
  return request("/v1/edr/actions/execute", { method: "POST", body: JSON.stringify(body) });
}

export function getEdrActionStatus(
  executionId: string,
  tenantShortCode?: string
): Promise<EdrActionRow> {
  const params = new URLSearchParams();
  if (tenantShortCode) params.set("tenant_short_code", tenantShortCode);
  const q = params.toString();
  return request(`/v1/edr/actions/${executionId}${q ? `?${q}` : ""}`);
}

export function getEdrMetrics(tenantShortCode?: string): Promise<EdrMetricsSummary> {
  const params = new URLSearchParams();
  if (tenantShortCode) params.set("tenant_short_code", tenantShortCode);
  const q = params.toString();
  return request(`/v1/edr/metrics/summary${q ? `?${q}` : ""}`);
}
