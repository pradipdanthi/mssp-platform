import type { CustomerEntitlements } from "../api/customer";
import type { CustomerEntitlementKey } from "./navEntitlements";
import { isCustomTier, MODULE_MIN_TIER, tierMeetsMinimum } from "./tierConfig";

/** Maps portal module keys to customer entitlements API boolean fields. */
const CAPABILITY_FLAG_FIELD: Record<CustomerEntitlementKey, keyof CustomerEntitlements> = {
  vulnerability_management: "vulnerability_management_enabled",
  continuous_compliance: "continuous_compliance_enabled",
  external_attack_surface: "external_attack_surface_enabled",
  cloud_identity_protection: "cloud_identity_protection_enabled",
  network_detection: "network_traffic_analysis_enabled",
  threat_intelligence: "threat_intelligence_enabled",
  threatlens: "threat_intelligence_enabled",
  endpoint_forensics: "endpoint_forensics_enabled",
};

/** True when the entitlement API reports the capability flag as enabled. */
export function capabilityFlagEnabled(
  ent: CustomerEntitlements | null | undefined,
  key: CustomerEntitlementKey
): boolean {
  if (!ent) return false;
  const field = CAPABILITY_FLAG_FIELD[key];
  const value = ent[field];
  return typeof value === "boolean" ? value : false;
}

/**
 * Uniform module access: standard tiers require rank + flag; CUSTOM uses flags only.
 */
export function isModuleAccessible(
  ent: CustomerEntitlements | null | undefined,
  key: CustomerEntitlementKey
): boolean {
  if (!ent) return false;
  if (isCustomTier(ent.subscription_tier)) {
    return capabilityFlagEnabled(ent, key);
  }
  if (!tierMeetsMinimum(ent.subscription_tier, MODULE_MIN_TIER[key])) return false;
  return capabilityFlagEnabled(ent, key);
}
