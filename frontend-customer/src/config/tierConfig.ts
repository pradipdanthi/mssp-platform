import type { CustomerEntitlementKey } from "./navEntitlements";

export type SubscriptionTier = "SILVER" | "GOLD" | "PLATINUM" | "CUSTOM";

export const TIER_RANK: Record<SubscriptionTier, number> = {
  SILVER: 1,
  GOLD: 2,
  PLATINUM: 3,
  CUSTOM: 0,
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
  if (value === "CUSTOM") return "CUSTOM";
  if (value === "GOLD" || value === "PLATINUM") return value;
  return "SILVER";
}

export function isCustomTier(tier?: string | null): boolean {
  return normalizeTier(tier) === "CUSTOM";
}

export function tierMeetsMinimum(
  current: SubscriptionTier | string | null | undefined,
  required: SubscriptionTier
): boolean {
  if (isCustomTier(current)) return false;
  return TIER_RANK[normalizeTier(current)] >= TIER_RANK[required];
}

export function upgradeLabel(required: SubscriptionTier): string {
  if (required === "PLATINUM") return "Upgrade to Platinum";
  if (required === "GOLD") return "Upgrade to Gold";
  return "Upgrade to Silver";
}

/** Compact label for nav pills and table hints where space is tight. */
export function upgradeShortLabel(required: SubscriptionTier): string {
  if (required === "PLATINUM") return "Platinum";
  if (required === "GOLD") return "Gold";
  return "Silver";
}
