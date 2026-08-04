import type { TenantEntitlements } from "../api/admin";

export type ServiceCatalogStatus = "included" | "active" | "available" | "requested";

/** Keys accepted by the consultation-request API. */
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

export type ScopeField = "endpoints" | "domains" | "m365_seats" | "notes";

export type ServiceCatalogItem = {
  id: string;
  serviceKey: ConsultationServiceKey;
  name: string;
  statusHint: "included" | "active" | "available";
  pricing: string;
  competitorValue: string;
  achieves: string;
  whereItFits: string;
  features: string[];
  learnMorePath?: string;
  /** Extra portal deep-links shown when the service is included/active. */
  extraLinks?: { label: string; path: string }[];
  requestable: boolean;
  scopeFields: ScopeField[];
};

/** Customer-safe 10-card portfolio (no third-party engine brand names). */
export const SERVICE_CATALOG: ServiceCatalogItem[] = [
  {
    id: "log_event_monitoring",
    serviceKey: "log_event_monitoring",
    name: "Log & Event Monitoring",
    statusHint: "included",
    pricing: "Included in Core Plan",
    competitorValue: "Competitor value: ~$4.00 / endpoint / month",
    achieves:
      "Ingests, normalizes, and analyzes 24/7 endpoint, server, and system event logs across your infrastructure — with Junexis Data Lake retention.",
    whereItFits:
      "Sits at the core SIEM/telemetry layer. Eliminates security blind spots and translates obscure log lines into actionable business risk insights.",
    features: [
      "24/7 real-time telemetry ingest (endpoint, Windows, and Linux audit sources)",
      "Zero-Cloud-Tax Data Retention (up to 365+ days local/cloud Parquet via Junexis Data Lake)",
      "Automated alert translation into plain-English business impact summaries",
      "Correlation against global MITRE ATT&CK detection rulesets",
      "Universal across Edge Appliance (Modes 2/4) and cloud-direct (Modes 1/3) deployments",
    ],
    learnMorePath: "/alerts",
    requestable: false,
    scopeFields: ["notes"],
  },
  {
    id: "incident_response",
    serviceKey: "incident_response",
    name: "Incident Response & Casework",
    statusHint: "included",
    pricing: "Included in Core Plan",
    competitorValue: "Competitor value: ~$1,500 / month SOC retainer",
    achieves:
      "Delivers end-to-end incident investigation, forensic timeline tracking, and SOC casework management with AI executive summaries.",
    whereItFits:
      "Sits at the SOC management layer. Bridges the gap between technical detection and executive oversight when suspicious activity occurs.",
    features: [
      "AI Executive Summary on every incident (What Happened · Business Impact · Action Taken)",
      "Interactive process-tree views showing full attack lineage",
      "Real-time SOC analyst collaboration and incident stage tracking",
      "Exportable, audit-ready evidence logs for leadership and legal teams",
      "Direct escalation channel between customer IT and SOC engineers",
    ],
    learnMorePath: "/incidents",
    requestable: false,
    scopeFields: ["notes"],
  },
  {
    id: "security_automation",
    serviceKey: "security_automation",
    name: "Security Automation & Containment",
    statusHint: "available",
    pricing: "Available — request consulting",
    competitorValue: "Competitor value: ~$2,000 / month SOAR engine",
    achieves:
      "Executes automated active-response playbooks to isolate infected hosts and stop malicious processes within milliseconds.",
    whereItFits:
      "Sits at the active-response layer. Stops ransomware propagation and insider threats before lateral movement occurs across the LAN.",
    features: [
      "One-click endpoint network isolation using OS-native firewalls",
      "Real-time remote process termination by PID or binary name",
      "Automated malicious file-hash blocking across connected endpoints",
      "Background state verification to confirm containment completed",
    ],
    requestable: true,
    scopeFields: ["endpoints", "notes"],
  },
  {
    id: "vulnerability_management",
    serviceKey: "vulnerability_management",
    name: "Vulnerability Management (VMaaS)",
    statusHint: "available",
    pricing: "$4.00 / device / month",
    competitorValue: "Competitor avg: $6.50–$9.00 / device / month",
    achieves:
      "Continuously scans internal networks and assets for software flaws, outdated packages, and unpatched CVEs.",
    whereItFits:
      "Sits at the vulnerability-management layer. Helps IT Operations prioritize server patching based on real exploit severity.",
    features: [
      "Automated scheduled scanning of internal IP blocks and servers",
      "Prioritized CVE scoring matched with CVSS risk ratings",
      "Clear, step-by-step remediation guidance for sysadmins",
      "Granular asset targeting — scan critical servers or selected subnets",
    ],
    learnMorePath: "/vulnerabilities",
    requestable: true,
    scopeFields: ["endpoints", "notes"],
  },
  {
    id: "continuous_compliance",
    serviceKey: "continuous_compliance",
    name: "Continuous Compliance & Hardening (CaaS)",
    statusHint: "available",
    pricing: "$3.50 / device / month",
    competitorValue: "Competitor avg: $5.00–$8.00 / device / month",
    achieves:
      "Audits operating-system configurations against gold-standard security benchmarks and regulatory frameworks.",
    whereItFits:
      "Sits at the governance & compliance layer. Designed for CISOs and compliance officers to pass ISO 27001, PCI-DSS, and CIS audits with less friction.",
    features: [
      "Continuous OS security configuration assessment via endpoint agents",
      "Real-time executive compliance readiness scorecards (%) in the portal",
      "Benchmarked against CIS Benchmarks, ISO 27001, PCI-DSS, and NIST CSF",
      "One-click downloadable PDF audit-readiness reports for auditors and boards",
    ],
    learnMorePath: "/compliance",
    requestable: true,
    scopeFields: ["endpoints", "notes"],
  },
  {
    id: "network_detection_response",
    serviceKey: "network_detection_response",
    name: "Network Detection & Response (NDR)",
    statusHint: "available",
    pricing: "$250.00 / network sensor / month",
    competitorValue: "Uncapped data ingestion — no per-GB fees",
    achieves:
      "Provides deep packet inspection and network behavioral monitoring across local subnets and boundary choke points.",
    whereItFits:
      "Sits at the network-edge layer. Catches zero-day threats, C2 beaconing, and lateral movement that endpoint-only agents miss.",
    features: [
      "Dual-engine network monitoring: signature detection plus behavioral metadata",
      "Uncapped network telemetry ingestion without per-gigabyte bandwidth fees",
      "Encrypted TLS certificate fingerprinting and DNS anomaly tracking",
      "East-west lateral movement detection across LAN traffic",
    ],
    learnMorePath: "/ndr",
    requestable: true,
    scopeFields: ["endpoints", "notes"],
  },
  {
    id: "threat_intelligence",
    serviceKey: "threat_intelligence",
    name: "Threat Intelligence & Enrichment",
    statusHint: "available",
    pricing: "$150.00 / tenant / month",
    competitorValue: "Flat tenant fee",
    achieves:
      "Contextualizes alerts with live threat feeds and enables 90-day Junexis Retrospective Engine sweeps when new IOCs appear.",
    whereItFits:
      "Sits at the enrichment layer. Reduces alert fatigue by filtering known-benign traffic and highlighting true high-risk attacks.",
    features: [
      "Automated indicator matching against curated open and commercial threat feeds (incl. STIX 2.1 / TAXII)",
      "90-Day Retrospective Threat Hunting — instant zero-day retro-sweeps via Junexis Retrospective Engine",
      "Works for Edge Appliance tenants (local Parquet) and cloud-direct tenants (Junexis Data Lake)",
      "Automatic mapping of every alert to exact MITRE ATT&CK techniques",
      "Early-warning alerts when active campaigns target your vertical",
    ],
    learnMorePath: "/threat-intel",
    extraLinks: [{ label: "Open ThreatLens sweeps", path: "/threatlens" }],
    requestable: true,
    scopeFields: ["notes"],
  },
  {
    id: "endpoint_forensics_deception",
    serviceKey: "endpoint_forensics_deception",
    name: "Endpoint Forensics & Deception Hunting",
    statusHint: "available",
    pricing: "$5.00 / endpoint / month",
    competitorValue: "Per-endpoint advanced response",
    achieves:
      "Combines deception tripwires, deep forensic triage, and Junexis ThreatLens AI-assisted IOC extraction from advisories.",
    whereItFits:
      "Sits at the proactive & advanced-response layer. Traps sophisticated attackers early and collects legal-grade evidence.",
    features: [
      "Junexis ThreatLens — AI-assisted IOC extraction & advisory / PDF / URL analysis",
      "Stealthy deployment of zero-overhead deception tripwires (decoy credentials, fake shares)",
      "Instant automated host isolation when an attacker touches a canary trap",
      "One-click remote triage collection (RAM, MFT, process memory)",
      "Secure pre-signed download links for forensic package archives",
    ],
    requestable: true,
    scopeFields: ["endpoints", "notes"],
    learnMorePath: "/forensics",
    extraLinks: [{ label: "Open ThreatLens", path: "/threatlens" }],
  },
  {
    id: "external_attack_surface",
    serviceKey: "external_attack_surface",
    name: "External Attack Surface Management (EASM)",
    statusHint: "available",
    pricing: "$199.00 / primary domain / month",
    competitorValue: "Zero agents required",
    achieves:
      "Continuously monitors your public internet perimeter (domains, subdomains, public IPs) through the eyes of an external attacker.",
    whereItFits:
      "Sits at the external-boundary layer. Helps prevent breaches before attackers discover exposed assets.",
    features: [
      "24/7 automated discovery of public subdomains, exposed cloud assets, and open ports",
      "Proactive alerts for expiring TLS certificates and misconfigured web services",
      "Vulnerability scanning on public-facing web applications",
      "Shadow-IT discovery for unauthorized cloud deployments",
    ],
    learnMorePath: "/easm",
    requestable: true,
    scopeFields: ["domains", "notes"],
  },
  {
    id: "cloud_identity_protection",
    serviceKey: "cloud_identity_protection",
    name: "Cloud & Identity Protection (ITDR)",
    statusHint: "available",
    pricing: "$3.00 / user seat / month",
    competitorValue: "Microsoft 365 / Entra ID / AWS",
    achieves:
      "Extends threat monitoring into SaaS identity providers to help prevent cloud account takeovers.",
    whereItFits:
      "Sits at the SaaS & identity layer. Protects remote workers and cloud infrastructure where many modern breaches originate.",
    features: [
      "Detection of impossible-travel logins and MFA fatigue / bypass attempts",
      "Real-time alerts for rogue admin creation and privilege escalation",
      "Automated flagging of dangerous inbox auto-forwarding rules",
      "Centralized dashboard unifying cloud identity events with on-premise alerts",
    ],
    learnMorePath: "/itdr",
    requestable: true,
    scopeFields: ["m365_seats", "notes"],
  },
];

export function getCatalogItem(serviceKey: ConsultationServiceKey): ServiceCatalogItem | undefined {
  return SERVICE_CATALOG.find((item) => item.serviceKey === serviceKey);
}

/** Short admin UI hint — first sentence of achieves (catalog is source of truth). */
export function catalogShortHint(serviceKey: ConsultationServiceKey): string {
  const item = getCatalogItem(serviceKey);
  if (!item) return "";
  const text = item.achieves.trim();
  const stop = text.search(/[.!?]\s/);
  return stop >= 0 ? text.slice(0, stop + 1) : text;
}

export function catalogDisplayName(serviceKey: ConsultationServiceKey): string {
  return getCatalogItem(serviceKey)?.name ?? serviceKey.replace(/_/g, " ");
}

export function resolveServiceStatus(
  item: ServiceCatalogItem,
  ent: TenantEntitlements | null,
  openRequestKeys: Set<string>
): ServiceCatalogStatus {
  if (openRequestKeys.has(item.serviceKey)) return "requested";

  switch (item.serviceKey) {
    case "log_event_monitoring":
      return ent?.wazuh_siem === false ? "available" : "included";
    case "incident_response":
      return ent?.thehive_mode === "off" ? "available" : "included";
    case "security_automation":
      return ent?.shuffle_mode && ent.shuffle_mode !== "off" ? "active" : "available";
    case "vulnerability_management":
      return ent?.greenbone_enabled ? "active" : "available";
    case "continuous_compliance":
      return ent?.continuous_compliance_enabled ? "active" : "available";
    case "external_attack_surface":
      return ent?.external_attack_surface_enabled ? "active" : "available";
    case "cloud_identity_protection":
      return ent?.cloud_identity_protection_enabled ? "active" : "available";
    case "network_detection_response":
      return ent?.zeek_enabled ? "active" : "available";
    case "threat_intelligence":
      return ent?.misp_enabled ? "active" : "available";
    case "endpoint_forensics_deception":
      return ent?.velociraptor_enabled ? "active" : "available";
    default:
      return item.statusHint === "included" || item.statusHint === "active"
        ? item.statusHint
        : "available";
  }
}

export function statusLabel(status: ServiceCatalogStatus): string {
  switch (status) {
    case "included":
      return "INCLUDED";
    case "active":
      return "ACTIVE";
    case "requested":
      return "REQUESTED";
    default:
      return "AVAILABLE";
  }
}

export function formatScopeSummary(row: {
  endpoint_count?: number | null;
  m365_seat_count?: number | null;
  target_domains?: string[];
  scope_notes?: string;
}): string {
  const parts: string[] = [];
  if (row.endpoint_count != null) parts.push(`${row.endpoint_count} endpoints`);
  if (row.m365_seat_count != null) parts.push(`${row.m365_seat_count} seats`);
  if (row.target_domains && row.target_domains.length)
    parts.push(row.target_domains.slice(0, 3).join(", ") + (row.target_domains.length > 3 ? "…" : ""));
  if (!parts.length && row.scope_notes) parts.push(row.scope_notes.slice(0, 80));
  return parts.join(" · ") || "—";
}
