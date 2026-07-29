import type { CustomerEntitlements, ServiceUpgradeServiceKey } from "../api/customer";

export type ServiceCatalogStatus = "included" | "active" | "available" | "requested";

export type ServiceCatalogItem = {
  id: string;
  /** Matches upgrade API when requestable; null for always-included core services. */
  serviceKey: ServiceUpgradeServiceKey | null;
  name: string;
  summary: string;
  benefits: string[];
  learnMorePath?: string;
  requestable: boolean;
};

/** Customer-safe service catalog (no third-party engine brand names). */
export const SERVICE_CATALOG: ServiceCatalogItem[] = [
  {
    id: "log_monitoring",
    serviceKey: null,
    name: "Log & event monitoring",
    summary: "Continuous monitoring of endpoint and system events with SOC triage.",
    benefits: [
      "24×7 detection coverage for suspicious activity on monitored systems",
      "Alerts translated into plain-English business impact",
      "Retention aligned to your contracted package",
    ],
    learnMorePath: "/alerts",
    requestable: false,
  },
  {
    id: "incident_response",
    serviceKey: null,
    name: "Incident response & casework",
    summary: "Structured investigation and case tracking when something needs action.",
    benefits: [
      "Clear case status and recommended actions in your portal",
      "Evidence of SOC work for auditors and leadership",
      "Coordination channel when containment or recovery is needed",
    ],
    learnMorePath: "/incidents",
    requestable: false,
  },
  {
    id: "security_automation",
    serviceKey: "security_automation",
    name: "Security automation",
    summary: "Repeatable response playbooks that speed up containment and reduce manual effort.",
    benefits: [
      "Faster consistent response for common threats",
      "Less time spent on repetitive analyst tasks",
      "Controlled automation with human oversight where needed",
    ],
    requestable: true,
  },
  {
    id: "vulnerability_management",
    serviceKey: "vulnerability_management",
    name: "Vulnerability management",
    summary: "Scheduled scanning and prioritized remediation guidance for your estate.",
    benefits: [
      "Discover missing patches and weak configurations before attackers do",
      "Prioritized findings with business-friendly recommendations",
      "Cadence options (weekly / monthly / quarterly) matched to your risk appetite",
    ],
    learnMorePath: "/vulnerabilities",
    requestable: true,
  },
  {
    id: "network_traffic_analysis",
    serviceKey: "network_traffic_analysis",
    name: "Network monitoring",
    summary: "Visibility into network traffic patterns to catch lateral movement and misuse.",
    benefits: [
      "Spot unusual connections and data movement across your network",
      "Stronger coverage for servers, appliances, and east-west traffic",
      "Complements endpoint monitoring with network context",
    ],
    requestable: true,
  },
  {
    id: "threat_intelligence",
    serviceKey: "threat_intelligence",
    name: "Threat intelligence",
    summary: "Context on active threats relevant to your industry and environment.",
    benefits: [
      "Earlier warning when campaigns target organizations like yours",
      "Enrichment that helps the SOC prioritize real risk",
      "Shared indicators that improve detection quality over time",
    ],
    requestable: true,
  },
  {
    id: "endpoint_forensics",
    serviceKey: "endpoint_forensics",
    name: "Endpoint forensics & hunting",
    summary: "Deep investigation on endpoints when an incident needs stronger evidence.",
    benefits: [
      "Collect forensic artifacts without relying on end-user screenshots",
      "Hunt for stealthy activity across critical systems",
      "Support legal / compliance evidence needs after serious incidents",
    ],
    requestable: true,
  },
];

export function resolveServiceStatus(
  item: ServiceCatalogItem,
  ent: CustomerEntitlements | null,
  openRequestKeys: Set<string>
): ServiceCatalogStatus {
  if (!item.requestable || !item.serviceKey) {
    // Core package services.
    if (item.id === "log_monitoring") {
      return ent?.log_monitoring_enabled === false ? "available" : "included";
    }
    if (item.id === "incident_response") {
      return ent?.incident_response === "not_included" ? "available" : "included";
    }
    return "included";
  }

  const key = item.serviceKey;
  if (key === "vulnerability_management" && ent?.vulnerability_management_enabled) return "active";
  if (key === "network_traffic_analysis" && ent?.network_traffic_analysis_enabled) return "active";
  if (key === "threat_intelligence" && ent?.threat_intelligence_enabled) return "active";
  if (key === "endpoint_forensics" && ent?.endpoint_forensics_enabled) return "active";
  if (key === "security_automation" && ent?.security_automation === "included") return "active";

  if (openRequestKeys.has(key)) return "requested";
  return "available";
}

export function statusLabel(status: ServiceCatalogStatus): string {
  switch (status) {
    case "included":
      return "Included";
    case "active":
      return "Active";
    case "requested":
      return "Requested";
    default:
      return "Available";
  }
}
