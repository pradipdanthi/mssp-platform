/**
 * Maps appliance engine IDs (svc-01..10) to the same capability catalog used in Tier Operations.
 * Admin fleet view — local engine status only, not a separate SKU layer.
 */

import type { ConsultationServiceKey } from "./serviceCatalog";
import { catalogDisplayName } from "./serviceCatalog";
import { SERVICE_KEY_MIN_TIER } from "./tierCapabilityMap";
import { tierDisplayName, type SubscriptionTier } from "./subscriptionTierMatrix";

export const SVC_TO_CATALOG_KEY: Record<string, ConsultationServiceKey> = {
  "svc-01": "log_event_monitoring",
  "svc-02": "incident_response",
  "svc-03": "security_automation",
  "svc-04": "vulnerability_management",
  "svc-05": "continuous_compliance",
  "svc-06": "network_detection_response",
  "svc-07": "threat_intelligence",
  "svc-08": "endpoint_forensics_deception",
  "svc-09": "external_attack_surface",
  "svc-10": "cloud_identity_protection",
};

export type SvcCatalogMeta = {
  catalogKey: ConsultationServiceKey | null;
  catalogName: string;
  minTier: SubscriptionTier | null;
  minTierLabel: string | null;
  localRole: string;
};

const LOCAL_ROLE: Record<string, string> = {
  "svc-01": "Local Wazuh Manager + collectors",
  "svc-02": "Local IR worker (cloud TheHive cases)",
  "svc-03": "Local automation worker (cloud Shuffle)",
  "svc-04": "On-box vulnerability scanning",
  "svc-05": "On-box compliance / SCA",
  "svc-06": "On-box NDR sensors",
  "svc-07": "Local threat-intel cache",
  "svc-08": "On-box forensics listener",
  "svc-09": "On-box EASM probes",
  "svc-10": "Identity / IdP connectors",
};

export function svcCatalogMeta(serviceId: string): SvcCatalogMeta {
  const key = serviceId.trim().toLowerCase();
  const catalogKey = SVC_TO_CATALOG_KEY[key] ?? null;
  if (!catalogKey) {
    return {
      catalogKey: null,
      catalogName: serviceId,
      minTier: null,
      minTierLabel: null,
      localRole: "Local engine",
    };
  }
  const minTier = SERVICE_KEY_MIN_TIER[catalogKey];
  return {
    catalogKey,
    catalogName: catalogDisplayName(catalogKey),
    minTier,
    minTierLabel: tierDisplayName(minTier),
    localRole: LOCAL_ROLE[key] || "Local engine",
  };
}

export function formatSvcEngineLabel(serviceId: string): string {
  const meta = svcCatalogMeta(serviceId);
  return meta.catalogName;
}

export function formatSvcEngineTitle(serviceId: string, active: boolean): string {
  const meta = svcCatalogMeta(serviceId);
  const parts = [meta.catalogName, meta.minTierLabel ? `Min tier: ${meta.minTierLabel}` : null, meta.localRole];
  parts.push(active ? "Licensed on appliance" : "Not licensed");
  return parts.filter(Boolean).join(" · ");
}
