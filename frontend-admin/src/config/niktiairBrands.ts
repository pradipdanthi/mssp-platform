/** Kevantic NikTiar™ capability labels — no upstream engine names in UI copy. */
export const NIKTIAR = {
  coreTelemetry: "NikTiar™ Core Telemetry",
  deepSightNdr: "NikTiar™ DeepSight NDR",
  aegisScanning: "NikTiar™ Aegis Scanning",
  apexOrchestrator: "NikTiar™ Apex Orchestrator",
  spectreForensics: "NikTiar™ Spectre Forensics",
  threatIntel: "NikTiar™ Threat Intelligence",
  managedDetection: "NikTiar™ Managed Detection",
  secureEdge: "NikTiar™ Secure Edge",
  waf: "NikTiar™ WAF",
  firewall: "NikTiar™ Firewall",
  ngfw: "NikTiar™ NGFW",
  urlFilter: "NikTiar™ URL Filter",
  rateLimit: "NikTiar™ Rate Limit",
  botDefense: "NikTiar™ Bot Defense",
  edgeEngine: "NikTiar™ Edge Engine",
  identityProtection: "NikTiar™ Identity Protection",
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
  secure_edge: NIKTIAR.secureEdge,
  coraza: NIKTIAR.waf,
  owasp: NIKTIAR.waf,
  owasp_crs: NIKTIAR.waf,
  modsecurity: NIKTIAR.waf,
  crowdsec: NIKTIAR.botDefense,
  caddy: NIKTIAR.edgeEngine,
  okta: NIKTIAR.identityProtection,
  entra: NIKTIAR.identityProtection,
  ad: NIKTIAR.identityProtection,
  active_directory: NIKTIAR.identityProtection,
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
