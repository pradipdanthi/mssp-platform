import type { CustomerEntitlementKey } from "../config/navEntitlements";
import { MODULE_MIN_TIER, normalizeTier, isCustomTier, TIER_RANK, type SubscriptionTier } from "../config/tierConfig";

export const TIER_CONSULTATION_KEYS = ["tier_silver", "tier_gold", "tier_platinum"] as const;

export function consultationKeyForTier(tier: SubscriptionTier): string {
  return `tier_${tier.toLowerCase()}`;
}

export function moduleIncludedInTierLabel(key: CustomerEntitlementKey): string {
  const tier = MODULE_MIN_TIER[key];
  const name = tier.charAt(0) + tier.slice(1).toLowerCase();
  return `Included in ${name}`;
}

export function tierIncludesModule(
  subscriptionTier: string | null | undefined,
  key: CustomerEntitlementKey
): boolean {
  if (isCustomTier(subscriptionTier)) return false;
  const current = normalizeTier(subscriptionTier);
  const required = MODULE_MIN_TIER[key];
  return TIER_RANK[current] >= TIER_RANK[required];
}
