import type { CustomerEntitlements } from "../api/customer";
import type { SubscriptionTier } from "./tierConfig";
import { MODULE_MIN_TIER } from "./tierConfig";
import { isModuleAccessible } from "./capabilityAccess";

/** Customer portal nav item. */
export type CustomerNavItem = {
  to: string;
  label: string;
  /** If set, tab is shown only when this entitlement check passes. */
  entitlement?: CustomerEntitlementKey;
  locked?: boolean;
  requiredTier?: SubscriptionTier;
};

export type CustomerEntitlementKey =
  | "vulnerability_management"
  | "continuous_compliance"
  | "external_attack_surface"
  | "cloud_identity_protection"
  | "network_detection"
  | "threat_intelligence"
  | "threatlens"
  | "endpoint_forensics";

/** Always-visible core portal navigation + Service Portfolio. */
export const CORE_NAV_ITEMS: CustomerNavItem[] = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/alerts", label: "Alerts" },
  { to: "/incidents", label: "Incidents" },
  { to: "/assets", label: "Assets" },
  { to: "/recommendations", label: "Recommendations" },
  { to: "/reports", label: "Reports" },
  { to: "/notifications", label: "Notifications" },
  { to: "/users", label: "User Management" },
  { to: "/audit", label: "Audit" },
  { to: "/account", label: "Account" },
  { to: "/services", label: "Service Portfolio" },
];

/** Capability modules — unlocked by subscription tier. */
export const ADDON_NAV_ITEMS: CustomerNavItem[] = [
  { to: "/vulnerabilities", label: "Vulnerabilities", entitlement: "vulnerability_management" },
  { to: "/compliance", label: "Compliance", entitlement: "continuous_compliance" },
  { to: "/easm", label: "Attack Surface", entitlement: "external_attack_surface" },
  { to: "/itdr", label: "Cloud & Identity", entitlement: "cloud_identity_protection" },
  { to: "/ndr", label: "Network Detection", entitlement: "network_detection" },
  { to: "/threat-intel", label: "Threat Intel", entitlement: "threat_intelligence" },
  { to: "/threatlens", label: "ThreatLens", entitlement: "threatlens" },
  { to: "/forensics", label: "Forensics", entitlement: "endpoint_forensics" },
];

/** Insert add-ons after Assets for a natural reading order. */
export function buildCustomerNavItems(ent: CustomerEntitlements | null): CustomerNavItem[] {
  const addons = ADDON_NAV_ITEMS.map((item) => {
    const requiredTier = item.entitlement ? MODULE_MIN_TIER[item.entitlement] : "SILVER";
    const unlocked = item.entitlement ? isModuleAccessible(ent, item.entitlement) : true;
    return {
      ...item,
      locked: !unlocked,
      requiredTier,
    };
  });
  const head = CORE_NAV_ITEMS.slice(0, 4);
  const tail = CORE_NAV_ITEMS.slice(4);
  return [...head, ...addons, ...tail];
}

/** Tier + entitlement flags — same contract on cloud SOC and NikTiar Edge. */
export function isEntitlementEnabled(
  ent: CustomerEntitlements | null | undefined,
  key: CustomerEntitlementKey
): boolean {
  return isModuleAccessible(ent, key);
}

export function entitlementLabel(key: CustomerEntitlementKey): string {
  switch (key) {
    case "vulnerability_management":
      return "Vulnerability Management";
    case "continuous_compliance":
      return "Continuous Compliance";
    case "external_attack_surface":
      return "External Attack Surface";
    case "cloud_identity_protection":
      return "Cloud & Identity Protection";
    case "network_detection":
      return "Network Detection & Response";
    case "threat_intelligence":
      return "Threat Intelligence";
    case "threatlens":
      return "ThreatLens";
    case "endpoint_forensics":
      return "Endpoint Forensics & Deception";
    default:
      return "This service";
  }
}

/** Map a route path to its entitlement key (for route guards). */
export function entitlementKeyForPath(pathname: string): CustomerEntitlementKey | null {
  const path = pathname.split("?")[0].replace(/\/+$/, "") || "/";
  if (path === "/vulnerabilities" || path === "/vulnerability") return "vulnerability_management";
  if (path === "/compliance") return "continuous_compliance";
  if (path === "/easm") return "external_attack_surface";
  if (path === "/itdr") return "cloud_identity_protection";
  if (path === "/ndr" || path === "/network") return "network_detection";
  if (path === "/threat-intel") return "threat_intelligence";
  if (path === "/threatlens") return "threatlens";
  if (path === "/forensics") return "endpoint_forensics";
  return null;
}
