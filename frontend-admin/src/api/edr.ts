import { request } from "./client";

export type EdrActionType =
  | "ISOLATE_HOST"
  | "UNISOLATE_HOST"
  | "KILL_PROCESS"
  | "COLLECT_FORENSICS"
  | "BLOCK_HASH";

export type EdrActionStatus =
  | "pending"
  | "executing"
  | "success"
  | "failed"
  | "verified"
  | "executed";

export interface ProcessTreeNode {
  pid?: number | null;
  parent_pid?: number | null;
  process_guid?: string | null;
  parent_process_guid?: string | null;
  process_name?: string | null;
  parent_process_name?: string | null;
  command_line?: string | null;
  parent_command_line?: string | null;
  user?: string | null;
  hash_md5?: string | null;
  hash_sha256?: string | null;
  signed_status?: string | null;
  mitre_techniques?: string[];
  event_time?: string | null;
  child_processes: ProcessTreeNode[];
}

export interface EdrActionRow {
  execution_id: string;
  status: EdrActionStatus;
  action_type: EdrActionType;
  result_message?: string | null;
  status_detail?: string | null;
  verified_at?: string | null;
  download_url?: string | null;
  forensic_artifact_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ForensicArtifact {
  artifact_id: string;
  status: string;
  file_name?: string | null;
  file_size_bytes?: number | null;
  sha256?: string | null;
  download_url?: string | null;
  created_at: string;
}

export interface EdrDeepDive {
  incident_number: string;
  endpoint: Record<string, unknown>;
  mitre: { tactics: string[]; techniques: { id: string; name: string }[] };
  process_tree: { root?: ProcessTreeNode | null; message?: string | null };
  recent_actions: EdrActionRow[];
  forensic_artifacts?: ForensicArtifact[];
}

export interface EdrMetricsSummary {
  mean_time_to_contain_seconds?: number | null;
  telemetry_events_processed: number;
  isolated_endpoints_count: number;
}

export function getEdrDeepDive(incidentNumber: string, tenantShortCode: string): Promise<EdrDeepDive> {
  const params = new URLSearchParams({
    incident_number: incidentNumber,
    tenant_short_code: tenantShortCode,
  });
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
  retry_of_execution_id?: string;
}): Promise<{
  execution_id: string;
  status: string;
  message: string;
  upload_url?: string | null;
  forensic_artifact_id?: string | null;
}> {
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

export function statusBadgeLabel(status: string, actionType?: string): string {
  const s = status.toLowerCase();
  if (s === "executing" || s === "pending") return "Executing…";
  if (s === "failed") return "Failed";
  if (actionType === "ISOLATE_HOST" && (s === "verified" || s === "success" || s === "executed"))
    return "Isolated";
  if (actionType === "UNISOLATE_HOST" && (s === "verified" || s === "success" || s === "executed"))
    return "Restored";
  if (s === "verified") return "Verified";
  if (s === "success" || s === "executed") return "Success";
  return status;
}
