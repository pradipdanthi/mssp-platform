/**
 * Tier-1 AI SOC Triage Copilot — calls control-plane API only (never Ollama from browser).
 */
import { request } from "../api/client";

export type AiTriageVerdict =
  | "BENIGN_FALSE_POSITIVE"
  | "SUSPICIOUS"
  | "MALICIOUS";

export type AiTriageAction =
  | "AUTO_SUPPRESS"
  | "INVESTIGATE_HOST"
  | "ISOLATE_AGENT";

export type AiSuggestedSuppressionScope = {
  rule_id: string;
  process_path: string;
  justification: string;
};

export type AiTriageContextSummary = {
  device_type?: string;
  ti_hit?: boolean;
  related_alerts_count?: number;
  prior_fp_count?: number;
  prior_fp_same_rule?: number;
  prior_fp_same_process?: number;
  suppression_match?: boolean;
  active_suppression_count?: number;
  signature_status?: string;
  hash_reputation?: string;
  admin_activity_signal_count?: number;
  historical_fp_pressure?: string;
  pre_score_flags?: string[];
  queue_suggestion?: string | null;
};

export type AiPreScoreHints = {
  path_temp_or_userprofile?: boolean;
  known_windows_binary_unexpected_path?: boolean;
  encoded_powershell_or_cmdline_red_flags?: boolean;
  admin_user_signal?: boolean;
  process_basename?: string | null;
  flags?: string[];
};

export type AiTriageResult = {
  verdict: AiTriageVerdict;
  confidence: number;
  summary: string;
  recommended_action: AiTriageAction;
  suggested_suppression_scope: AiSuggestedSuppressionScope;
  cached?: boolean;
  content_hash?: string;
  model?: string | null;
  updated_at?: string | null;
  /** Compact enrichment strip for UI */
  context_summary?: AiTriageContextSummary | null;
  pre_score_hints?: AiPreScoreHints | null;
  action_rationale?: string | null;
  queue_suggestion?: "low_priority" | string | null;
  historical_fp_pressure?: string | null;
  enrichment?: {
    context_summary?: AiTriageContextSummary;
    pre_score_hints?: AiPreScoreHints;
    [key: string]: unknown;
  } | null;
};

export type AiTriageResponse = {
  alert_id: string;
  triage: AiTriageResult;
};

export function fetchCustomerAiTriage(
  shortCode: string,
  alertId: string,
  opts?: { force?: boolean }
): Promise<AiTriageResponse> {
  const q = opts?.force ? "?force=true" : "";
  return request<AiTriageResponse>(
    `/customer/alerts/${encodeURIComponent(shortCode)}/${encodeURIComponent(alertId)}/ai-triage${q}`,
    { method: "POST" }
  );
}

export function verdictBadgeClass(verdict: AiTriageVerdict): string {
  if (verdict === "BENIGN_FALSE_POSITIVE") return "ai-verdict-badge ai-verdict-benign";
  if (verdict === "MALICIOUS") return "ai-verdict-badge ai-verdict-malicious";
  return "ai-verdict-badge ai-verdict-suspicious";
}

export function verdictLabel(verdict: AiTriageVerdict): string {
  if (verdict === "BENIGN_FALSE_POSITIVE") return "False Positive / Benign";
  if (verdict === "MALICIOUS") return "Malicious";
  return "Suspicious";
}

export function actionLabel(action: AiTriageAction): string {
  if (action === "AUTO_SUPPRESS") return "Auto-suppress (create suppression rule)";
  if (action === "ISOLATE_AGENT") return "Isolate agent";
  return "Investigate host";
}

const HINT_LABELS: Record<string, string> = {
  path_temp_or_userprofile: "Temp/user profile path",
  known_windows_binary_unexpected_path: "LOLBin unexpected path",
  encoded_powershell_or_cmdline_red_flags: "Encoded/suspicious cmdline",
  admin_user_signal: "Admin/service user",
};

export function riskHintLabel(flag: string): string {
  return HINT_LABELS[flag] || flag.replace(/_/g, " ");
}
