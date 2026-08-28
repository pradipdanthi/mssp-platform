import type { CustomerEntitlementKey } from "./navEntitlements";

export type SubscriptionTier = "SILVER" | "GOLD" | "PLATINUM";

export const TIER_RANK: Record<SubscriptionTier, number> = {
  SILVER: 1,
  GOLD: 2,
  PLATINUM: 3,
};

export const MODULE_MIN_TIER: Record<CustomerEntitlementKey, SubscriptionTier> = {
  cloud_identity_protection: "SILVER",
  vulnerability_management: "GOLD",
  continuous_compliance: "PLATINUM",
  external_attack_surface: "GOLD",
  network_detection: "PLATINUM",
  threat_intelligence: "PLATINUM",
  threatlens: "PLATINUM",
  endpoint_forensics: "PLATINUM",
};

export function normalizeTier(tier?: string | null): SubscriptionTier {
  const value = (tier || "SILVER").toUpperCase();
  if (value === "GOLD" || value === "PLATINUM") return value;
  return "SILVER";
}

export function tierMeetsMinimum(
  current: SubscriptionTier | string | null | undefined,
  required: SubscriptionTier
): boolean {
  return TIER_RANK[normalizeTier(current)] >= TIER_RANK[required];
}

export function upgradeLabel(required: SubscriptionTier): string {
  if (required === "PLATINUM") return "Upgrade to Platinum";
  if (required === "GOLD") return "Upgrade to Gold";
  return "Upgrade to Silver";
}
