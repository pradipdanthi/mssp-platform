/** Kevantic NikTiar™ capability labels — no upstream engine names in customer UI. */
export const NIKTIAR = {
  coreTelemetry: "NikTiar™ Core Telemetry",
  deepSightNdr: "NikTiar™ DeepSight NDR",
  aegisScanning: "NikTiar™ Aegis Scanning",
  apexOrchestrator: "NikTiar™ Apex Orchestrator",
  spectreForensics: "NikTiar™ Spectre Forensics",
  threatIntel: "NikTiar™ Threat Intelligence",
  managedDetection: "NikTiar™ Managed Detection",
} as const;

const SOURCE_LABELS: Record<string, string> = {
  wazuh: NIKTIAR.coreTelemetry,
  fluentbit: NIKTIAR.coreTelemetry,
  "fluent-bit": NIKTIAR.coreTelemetry,
  fluent_bit: NIKTIAR.coreTelemetry,
  endpoint_kernel: NIKTIAR.coreTelemetry,
  endpoint_audit_exec: NIKTIAR.coreTelemetry,
  endpoint_process_create: NIKTIAR.coreTelemetry,
  suricata: NIKTIAR.deepSightNdr,
  zeek: NIKTIAR.deepSightNdr,
  nuclei: NIKTIAR.aegisScanning,
  vuls: NIKTIAR.aegisScanning,
  greenbone: NIKTIAR.aegisScanning,
  openvas: NIKTIAR.aegisScanning,
  shuffle: NIKTIAR.apexOrchestrator,
  thehive: NIKTIAR.apexOrchestrator,
  velociraptor: NIKTIAR.spectreForensics,
  misp: NIKTIAR.threatIntel,
  manual: NIKTIAR.managedDetection,
  platform: NIKTIAR.managedDetection,
  mssp_control: NIKTIAR.managedDetection,
};

export function niktiairSourceLabel(source: string | null | undefined): string {
  const raw = (source || "").trim();
  if (!raw) return "—";
  if (/niktiar/i.test(raw)) return raw;
  const key = raw.toLowerCase();
  return SOURCE_LABELS[key] ?? NIKTIAR.managedDetection;
}
