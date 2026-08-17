/** Admin appliance fleet list - relative heartbeat, version, resources, service labels. */

export type HeartbeatFreshness = "never" | "fresh" | "warn" | "stale";

const SERVICE_SHORT_LABELS: Record<string, string> = {
  "svc-01": "Log",
  "svc-02": "IR",
  "svc-03": "Auto",
  "svc-04": "VMaaS",
  "svc-05": "CaaS",
  "svc-06": "NDR",
  "svc-07": "Intel",
  "svc-08": "DFIR",
  "svc-09": "EASM",
  "svc-10": "ITDR",
};

const SERVICE_FULL_LABELS: Record<string, string> = {
  "svc-01": "Log & Event Monitoring",
  "svc-02": "Incident Response (local worker)",
  "svc-03": "Security Automation",
  "svc-04": "Vulnerability Management",
  "svc-05": "Continuous Compliance",
  "svc-06": "Network Detection",
  "svc-07": "Threat Intelligence",
  "svc-08": "Forensics & Deception",
  "svc-09": "External Attack Surface",
  "svc-10": "Identity Threat Detection",
};

export function pickHeartbeatTimestamp(
  lastSeenAt: string | null | undefined,
  heartbeatAt: string | null | undefined
): string | null {
  return lastSeenAt || heartbeatAt || null;
}

export function heartbeatFreshness(iso: string | null | undefined): HeartbeatFreshness {
  if (!iso) return "never";
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return "never";
  const ageSec = (Date.now() - ms) / 1000;
  if (ageSec <= 120) return "fresh";
  if (ageSec <= 300) return "warn";
  return "stale";
}

export function formatRelativeHeartbeat(iso: string | null | undefined): string {
  if (!iso) return "Never";
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return "Unknown";

  const ageSec = Math.max(0, Math.floor((Date.now() - ms) / 1000));
  if (ageSec < 45) return "Just now";
  if (ageSec < 90) return "1m ago";
  if (ageSec < 3600) return String(Math.floor(ageSec / 60)) + "m ago";
  if (ageSec < 86400) return String(Math.floor(ageSec / 3600)) + "h ago";
  return String(Math.floor(ageSec / 86400)) + "d ago";
}

export function formatHeartbeatTitle(iso: string | null | undefined): string {
  if (!iso) return "No heartbeat recorded";
  return iso;
}

export function formatApplianceVersion(
  configVersion: string | null | undefined,
  gitCommit: string | null | undefined,
  agentVersion: string | null | undefined
): { primary: string; secondary: string | null; title: string } {
  const primary = (configVersion || gitCommit || agentVersion || "-").trim();
  const parts: string[] = [];
  if (configVersion) parts.push("Config " + configVersion);
  if (gitCommit) parts.push("Image " + gitCommit);
  if (agentVersion) parts.push("Agent " + agentVersion);
  let secondary: string | null = null;
  if (gitCommit && configVersion && gitCommit !== configVersion) {
    secondary = gitCommit.length > 10 ? gitCommit.slice(0, 10) : gitCommit;
  } else if (agentVersion && agentVersion !== primary) {
    secondary = "Agent " + agentVersion;
  }
  return {
    primary: primary.length > 18 ? primary.slice(0, 16) + "..." : primary,
    secondary,
    title: parts.length ? parts.join(" | ") : "Version not reported yet",
  };
}

export function formatResourcePercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return String(Math.round(Number(value))) + "%";
}

export function resourceStressClass(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return "";
  const n = Number(value);
  if (n >= 95) return "appliance-resource--critical";
  if (n >= 85) return "appliance-resource--warn";
  return "";
}

export function serviceShortLabel(serviceId: string): string {
  const key = serviceId.trim().toLowerCase();
  return SERVICE_SHORT_LABELS[key] || serviceId.replace(/^svc-/i, "");
}

export function serviceFullLabel(serviceId: string): string {
  const key = serviceId.trim().toLowerCase();
  return SERVICE_FULL_LABELS[key] || serviceId;
}

export const CATALOGUE_SERVICE_IDS = [
  "svc-01",
  "svc-02",
  "svc-03",
  "svc-04",
  "svc-05",
  "svc-06",
  "svc-07",
  "svc-08",
  "svc-09",
  "svc-10",
] as const;

export function sortServiceIds(services: string[] | null | undefined): string[] {
  return [...(services || [])].sort((a, b) => a.localeCompare(b));
}

export function catalogueServiceStatus(enabled: string[] | null | undefined): Array<{
  id: string;
  label: string;
  full: string;
  active: boolean;
}> {
  const on = new Set((enabled || []).map((s) => s.trim().toLowerCase()));
  return CATALOGUE_SERVICE_IDS.map((id) => ({
    id,
    label: serviceShortLabel(id),
    full: serviceFullLabel(id),
    active: on.has(id),
  }));
}
