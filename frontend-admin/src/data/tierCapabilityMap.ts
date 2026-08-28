import type { ConsultationServiceKey } from "./serviceCatalog";
import {
  normalizeTier,
  tierDisplayName,
  isCustomTier,
  TIER_RANK,
  type SubscriptionTier,
} from "./subscriptionTierMatrix";

/** Minimum subscription tier that includes each internal capability module. */
export const SERVICE_KEY_MIN_TIER: Record<ConsultationServiceKey, SubscriptionTier> = {
  log_event_monitoring: "SILVER",
  incident_response: "SILVER",
  cloud_identity_protection: "SILVER",
  security_automation: "GOLD",
  vulnerability_management: "GOLD",
  external_attack_surface: "GOLD",
  continuous_compliance: "PLATINUM",
  network_detection_response: "PLATINUM",
  threat_intelligence: "PLATINUM",
  endpoint_forensics_deception: "PLATINUM",
  other: "SILVER",
};

export const TIER_CONSULTATION_KEYS = ["tier_silver", "tier_gold", "tier_platinum"] as const;

export type TierConsultationKey = (typeof TIER_CONSULTATION_KEYS)[number];

export function consultationKeyForTier(tier: SubscriptionTier): TierConsultationKey {
  return `tier_${tier.toLowerCase()}` as TierConsultationKey;
}

export function tierFromConsultationKey(key: string): SubscriptionTier | null {
  const normalized = key.toLowerCase();
  if (normalized === "tier_gold") return "GOLD";
  if (normalized === "tier_platinum") return "PLATINUM";
  if (normalized === "tier_silver") return "SILVER";
  return null;
}

export function includedInTierLabel(serviceKey: ConsultationServiceKey): string {
  const tier = SERVICE_KEY_MIN_TIER[serviceKey];
  return `Included in ${tierDisplayName(tier)}`;
}

export function tenantMeetsServiceTier(
  subscriptionTier: string | null | undefined,
  serviceKey: ConsultationServiceKey
): boolean {
  if (isCustomTier(subscriptionTier)) return false;
  const current = normalizeTier(subscriptionTier);
  const required = SERVICE_KEY_MIN_TIER[serviceKey];
  return TIER_RANK[current] >= TIER_RANK[required];
}
