import { request } from "./client";

export type AlertRow = {
  id: string;
  alert_title?: string;
  title?: string;
  severity: string;
  status: string;
  event_time?: string | null;
  destination_host?: string | null;
  source_ip?: string | null;
  source_tool?: string | null;
  ai_verdict?: string | null;
  ai_confidence?: number | null;
  ai_containment_suggestion?: string | null;
  tenant_name?: string | null;
  short_code?: string | null;
};

export type IncidentRow = {
  id: string;
  incident_number: string;
  title: string;
  severity: string;
  status: string;
  opened_at?: string | null;
  tenant_name?: string | null;
  short_code?: string | null;
};

export type ActivityItem = {
  id: string;
  kind: string;
  category: string;
  title: string;
  detail?: string;
  severity?: string;
  alert_id?: string | null;
  incident_id?: string | null;
  actor?: string;
  ts: string;
  source?: string;
};

export type StackNode = {
  id: string;
  label: string;
  layer: string;
  status: string;
  detail: string;
  pulse: number;
  metric?: string | null;
};

export type StackSkeleton = {
  generated_at?: string;
  kpis?: Record<string, number>;
  tool_activity_24h?: Record<string, number>;
  nodes: StackNode[];
  edges?: { from: string; to: string }[];
  layers?: string[];
};

export type EngineStreamRow = {
  id: string;
  lane?: string;
  kind?: string;
  severity?: string;
  title?: string;
  detail?: string;
  ts?: string;
  alert_id?: string;
  incident_id?: string;
};

export type EngineLane = {
  id: string;
  label: string;
  tool: string;
  vm: string;
  hostname: string;
  host: string;
  port: number;
  os: string;
  lane: string;
  status: string;
  reachable: boolean;
  latency_ms?: number | null;
  pulse_24h: number;
  stream: EngineStreamRow[];
  stream_count?: number;
};

export type EngineWall = {
  generated_at?: string;
  summary?: {
    engines_total: number;
    engines_online: number;
    engines_offline: number;
  };
  lanes: EngineLane[];
};

export type EdgeEvent = {
  id: string;
  tenant_short_code?: string | null;
  edge_hostname?: string | null;
  public_hostname?: string | null;
  event_type?: string | null;
  severity?: string | null;
  summary?: string | null;
  created_at?: string | null;
};

export function getOverview() {
  return request<{
    kpis: Record<string, number>;
    recent_alerts: AlertRow[];
    chat_enabled: boolean;
    stack?: Partial<StackSkeleton>;
  }>("/admin/soc-console/overview");
}

export function getStack() {
  return request<StackSkeleton>("/admin/soc-console/stack");
}

export function getEngines() {
  return request<EngineWall>("/admin/soc-console/engines");
}

export function getChatStatus() {
  return request<{
    enabled: boolean;
    provider: string;
    message: string;
    agent?: string;
    neural_tts?: boolean;
    server_stt?: boolean;
  }>("/admin/soc-console/status");
}

export function postStt(audioBase64: string) {
  return request<{
    ok: boolean;
    text?: string;
    reason?: string;
    provider?: string;
    duration_sec?: number;
  }>("/admin/soc-console/stt", {
    method: "POST",
    body: {
      audio_base64: audioBase64,
      content_type: "audio/wav",
    },
  });
}

export function postChat(
  message: string,
  opts?: {
    tenant_short_code?: string;
    alert_id?: string;
    apply_actions?: boolean;
    auto_approve?: boolean;
  }
) {
  return request<{
    answer: string;
    spoken_answer?: string;
    agent?: string;
    provider?: string;
    scope?: string;
    sources?: Record<string, number>;
    actions_applied?: { ok?: boolean; type?: string }[];
    proposed_actions?: Record<string, unknown>[];
    pending_approval?: { id?: string; summary?: string };
  }>("/admin/soc-console/chat", {
    method: "POST",
    body: {
      message,
      tenant_short_code: opts?.tenant_short_code || undefined,
      alert_id: opts?.alert_id || undefined,
      apply_actions: Boolean(opts?.apply_actions),
      auto_approve: Boolean(opts?.auto_approve),
    },
  });
}

/** Proactive Hi-Tia welcome: alerts + urgency + end-to-end stack (single spoken turn). */
export function getWakeBriefing() {
  return request<{
    answer: string;
    spoken_answer?: string;
    agent?: string;
    mode?: string;
    provider?: string;
  }>("/admin/soc-console/wake-briefing");
}

export type CommandCenterPayload = {
  generated_at?: string;
  agent?: string;
  version?: string;
  system_status?: string;
  chat_enabled?: boolean;
  voice?: {
    server_stt?: boolean;
    neural_tts?: boolean;
    wake_phrase?: string;
    free_hand?: boolean;
  };
  core?: {
    name?: string;
    status?: string;
    provider?: string;
    memory_note?: string;
  };
  gauges?: Record<string, number | null | undefined>;
  kpis?: {
    alerts?: number;
    incidents?: number;
    events?: number;
    vulnerabilities?: number;
    patch_gaps?: number;
    customers?: number;
  };
  urgency?: Record<string, number>;
  needs_attention?: string[];
  priority?: string;
  top_alerts?: {
    id: string;
    title?: string;
    severity?: string;
    status?: string;
    short_code?: string;
    tenant_name?: string;
    host?: string;
  }[];
  top_incidents?: {
    id: string;
    incident_number?: string;
    title?: string;
    severity?: string;
    status?: string;
    short_code?: string;
  }[];
  agents?: {
    id: string;
    label?: string;
    vm?: string;
    status?: string;
    reachable?: boolean;
    latency_ms?: number | null;
    pulse_24h?: number;
  }[];
  proxmox_named?: Record<string, Record<string, unknown>>;
  compliance?: Record<string, unknown>;
  wake_preview?: { spoken?: string; answer?: string };
  quick_commands?: { id: string; label: string; prompt: string }[];
  activity?: { id?: string; title?: string; detail?: string; severity?: string; ts?: string; kind?: string }[];
  approvals?: ApprovalItem[];
  pending_approvals?: number;
  routines?: RoutineItem[];
  routines_ran_now?: { id?: string; name?: string; spoken_answer?: string }[];
};

export type ApprovalItem = {
  id: string;
  status?: string;
  created_at?: string;
  summary?: string;
  question?: string;
  answer_excerpt?: string;
  actions?: Record<string, unknown>[];
};

export type RoutineItem = {
  id: string;
  name?: string;
  description?: string;
  enabled?: boolean;
  hour_local?: number;
  minute_local?: number;
  timezone?: string;
  last_run_at?: string | null;
  last_spoken?: string | null;
  last_priority?: string | null;
};

/** Jarvis-adapted Command Center home payload for Tia. */
export function getCommandCenter() {
  return request<CommandCenterPayload>("/admin/soc-console/command-center");
}

export function decideApproval(approvalId: string, decision: "approve" | "decline") {
  return request<{ approval: ApprovalItem }>(`/admin/soc-console/approvals/${approvalId}/decide`, {
    method: "POST",
    body: { decision },
  });
}

export function listRoutines() {
  return request<{ routines: RoutineItem[]; ran_now?: string[] }>("/admin/soc-console/routines");
}

export function patchRoutine(
  routineId: string,
  patch: { enabled?: boolean; hour_local?: number; minute_local?: number; timezone?: string }
) {
  return request<{ routine: RoutineItem }>(`/admin/soc-console/routines/${routineId}`, {
    method: "PATCH",
    body: patch,
  });
}

export function runRoutine(routineId: string) {
  return request<{
    routine: RoutineItem;
    briefing?: { spoken_answer?: string; answer?: string; priority?: string };
  }>(`/admin/soc-console/routines/${routineId}/run`, { method: "POST" });
}

export function speakTia(text: string) {
  return request<{
    available: boolean;
    reason?: string;
    audio_base64?: string;
    content_type?: string;
    provider?: string;
  }>("/admin/soc-console/speak", {
    method: "POST",
    body: { text },
  });
}

export function getQueue(params?: { severity?: string; status?: string; q?: string }) {
  const sp = new URLSearchParams();
  if (params?.severity) sp.set("severity", params.severity);
  if (params?.status) sp.set("status", params.status);
  if (params?.q) sp.set("q", params.q);
  sp.set("limit", "100");
  const qs = sp.toString();
  return request<{ alerts: AlertRow[]; incidents: IncidentRow[] }>(
    `/admin/soc-console/queue${qs ? `?${qs}` : ""}`
  );
}

export function getActivity(limit = 80) {
  return request<{ items: ActivityItem[]; count: number; kpis?: Record<string, number> }>(
    `/admin/soc-console/activity?limit=${limit}`
  );
}

export type TriageListFilters = {
  page?: number;
  page_size?: number;
  status?: string;
  severity?: string;
  tenant_id?: string;
  q?: string;
};

function withFilters(path: string, filters?: TriageListFilters): string {
  const sp = new URLSearchParams();
  if (filters?.page) sp.set("page", String(filters.page));
  if (filters?.page_size) sp.set("page_size", String(filters.page_size));
  if (filters?.status) sp.set("status", filters.status);
  if (filters?.severity) sp.set("severity", filters.severity);
  if (filters?.tenant_id) sp.set("tenant_id", filters.tenant_id);
  if (filters?.q) sp.set("q", filters.q);
  const qs = sp.toString();
  return qs ? `${path}?${qs}` : path;
}

export function getAlerts(filters?: TriageListFilters) {
  return request<{ alerts: AlertRow[]; total?: number }>(
    withFilters("/admin/alerts", { page: 1, page_size: 100, ...filters })
  );
}

export type AlertDetail = AlertRow & {
  customer_visible?: boolean;
  ai_plain_summary?: string | null;
  ai_recommended_action?: string | null;
  tenant_name?: string | null;
  short_code?: string | null;
  internal_notes?: string | null;
};

export type AlertTriageUpdate = {
  status?: "new" | "triaged" | "incident_created" | "false_positive" | "closed";
  customer_visible?: boolean;
  ai_plain_summary?: string | null;
  ai_recommended_action?: string | null;
};

export function getAlertDetail(alertId: string) {
  return request<{ alert: AlertDetail }>(`/admin/alerts/${encodeURIComponent(alertId)}`);
}

export function updateAlertTriage(alertId: string, update: AlertTriageUpdate) {
  return request<{ alert: AlertDetail }>(`/admin/alerts/${encodeURIComponent(alertId)}`, {
    method: "PATCH",
    body: update,
  });
}

export function getIncidents(filters?: TriageListFilters) {
  return request<{ incidents: IncidentRow[]; total?: number }>(
    withFilters("/admin/incidents", { page: 1, page_size: 100, ...filters })
  );
}

export type IncidentDetail = IncidentRow & {
  assigned_to?: string | null;
  assigned_to_user_id?: string | null;
  customer_visible_summary?: string | null;
  customer_action_required?: string | null;
  tenant_name?: string | null;
};

export type IncidentTriageUpdate = {
  status?: "open" | "in_progress" | "waiting_customer" | "resolved" | "closed";
  assigned_to_user_id?: string | null;
  customer_visible_summary?: string | null;
  customer_action_required?: string | null;
};

export type IncidentComment = {
  id: string;
  comment_text?: string;
  visibility?: string;
  created_at?: string;
  author?: string | null;
  created_by?: string | null;
};

export function getIncidentDetail(incidentId: string) {
  return request<{
    incident: IncidentDetail;
    comments?: IncidentComment[];
    primary_alert?: AlertDetail | null;
  }>(`/admin/incidents/${encodeURIComponent(incidentId)}`);
}

export function updateIncidentTriage(incidentId: string, update: IncidentTriageUpdate) {
  return request<{ incident: IncidentDetail }>(
    `/admin/incidents/${encodeURIComponent(incidentId)}`,
    { method: "PATCH", body: update }
  );
}

export function addIncidentComment(
  incidentId: string,
  comment: { comment_text: string; visibility?: "internal" | "customer" }
) {
  return request<{ comment: IncidentComment }>(
    `/admin/incidents/${encodeURIComponent(incidentId)}/comments`,
    { method: "POST", body: comment }
  );
}

export type TenantRiskRow = {
  name: string;
  short_code: string;
  sla_level?: string | null;
  business_criticality?: string | null;
  appliances?: number;
  online_appliances?: number;
  alerts?: number;
  high_or_critical_alerts?: number;
  incidents?: number;
  open_incidents?: number;
};

export function getAdminDashboard(tenantId?: string) {
  const qs = tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : "";
  return request<{
    overview: Record<string, number>;
    severity_breakdown?: { severity: string; count: number }[];
    tenant_risk_summary?: TenantRiskRow[];
  }>(`/admin/dashboard${qs}`);
}

export function getEdgeEvents() {
  return request<{ events: EdgeEvent[]; count: number }>(
    "/admin/secure-edge/events?limit=100"
  );
}

export function getTenants() {
  return request<{
    tenants: { id: string; name: string; short_code: string; status?: string }[];
  }>("/admin/tenants?page_size=200");
}

export type PatchGapRow = {
  id: string;
  check_id?: string | null;
  rule_title?: string | null;
  status?: string | null;
  severity?: string | null;
  rationale?: string | null;
  remediation?: string | null;
  policy_id?: string | null;
  policy_title?: string | null;
  agent_name?: string | null;
  tenant_name?: string | null;
  short_code?: string | null;
  tenant_id?: string | null;
  updated_at?: string | null;
};

export function getPatchGaps(params?: {
  tenant_id?: string;
  short_code?: string;
  q?: string;
  page?: number;
  page_size?: number;
}) {
  const sp = new URLSearchParams();
  if (params?.tenant_id) sp.set("tenant_id", params.tenant_id);
  if (params?.short_code) sp.set("short_code", params.short_code);
  if (params?.q) sp.set("q", params.q);
  if (params?.page) sp.set("page", String(params.page));
  sp.set("page_size", String(params?.page_size ?? 50));
  return request<{
    items: PatchGapRow[];
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
  }>(`/admin/compliance/patch-gaps?${sp.toString()}`);
}

export type AdminVulnerability = {
  id: string;
  title?: string | null;
  cve_id?: string | null;
  severity?: string | null;
  status?: string | null;
  source_platform?: string | null;
  host?: string | null;
  tenant_name?: string | null;
  short_code?: string | null;
  cvss_score?: number | null;
  detected_at?: string | null;
};

export function getVulnerabilities(params?: {
  tenant_id?: string;
  tenant_short_code?: string;
  status?: string;
  page_size?: number;
}) {
  const sp = new URLSearchParams();
  if (params?.tenant_id) sp.set("tenant_id", params.tenant_id);
  if (params?.tenant_short_code) sp.set("tenant_short_code", params.tenant_short_code);
  if (params?.status) sp.set("status", params.status);
  sp.set("page", "1");
  sp.set("page_size", String(params?.page_size ?? 50));
  return request<{ vulnerabilities: AdminVulnerability[]; total?: number }>(
    `/admin/vulnerabilities?${sp.toString()}`
  );
}

/** Fetch-based SSE (supports Authorization header). */
export async function openActivityStream(
  token: string,
  handlers: {
    onSnapshot?: (items: ActivityItem[], kpis?: Record<string, number>) => void;
    onActivity?: (items: ActivityItem[]) => void;
    onKpis?: (kpis: Record<string, number>) => void;
    onStack?: (stack: StackSkeleton) => void;
    onEngines?: (wall: EngineWall) => void;
    onError?: (err: string) => void;
  },
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch("/api/admin/soc-console/activity/stream", {
    headers: {
      Accept: "text/event-stream",
      Authorization: `Bearer ${token}`,
    },
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`SSE failed HTTP ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const chunks = buf.split("\n\n");
    buf = chunks.pop() || "";
    for (const chunk of chunks) {
      const lines = chunk.split("\n");
      let event = "message";
      let data = "";
      for (const line of lines) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      try {
        const parsed = JSON.parse(data) as {
          type?: string;
          items?: ActivityItem[];
          kpis?: Record<string, number>;
          stack?: StackSkeleton;
          engines?: EngineWall;
          detail?: string;
        };
        if (event === "snapshot" || parsed.type === "snapshot") {
          handlers.onSnapshot?.(parsed.items || [], parsed.kpis);
        } else if (event === "activity" || parsed.type === "activity") {
          handlers.onActivity?.(parsed.items || []);
        } else if (event === "kpis" || parsed.type === "kpis") {
          if (parsed.kpis) handlers.onKpis?.(parsed.kpis);
        } else if (event === "stack" || parsed.type === "stack") {
          if (parsed.stack) handlers.onStack?.(parsed.stack);
        } else if (event === "engines" || parsed.type === "engines") {
          if (parsed.engines) handlers.onEngines?.(parsed.engines);
        } else if (event === "error") {
          handlers.onError?.(parsed.detail || "stream error");
        }
      } catch {
        /* ignore malformed keepalive */
      }
    }
  }
}
