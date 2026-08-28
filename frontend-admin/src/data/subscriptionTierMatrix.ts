export type SubscriptionTier = "SILVER" | "GOLD" | "PLATINUM" | "CUSTOM";

/** Public SKUs — CUSTOM is admin-provisioned only, not selectable on tenant create. */
export type StandardSubscriptionTier = Exclude<SubscriptionTier, "CUSTOM">;

export type TierCatalogEntry = {
  tier: SubscriptionTier;
  name: string;
  subtitle: string;
  tagline: string;
  features: string[];
  inheritsFrom?: SubscriptionTier;
};

export const TIER_CATALOG: TierCatalogEntry[] = [
  {
    tier: "SILVER",
    name: "Silver",
    subtitle: "Identity ITDR",
    tagline: "Cloud & Identity ITDR — Okta, Entra ID, & Active Directory Protection",
    features: [
      "NikTiar identity telemetry (Okta / AD ingest)",
      "MFA fatigue detection",
      "Impossible travel alerts",
      "Kerberoasting detection",
      "Portal MFA enforcement",
      "90-day log retention",
    ],
  },
  {
    tier: "GOLD",
    name: "Gold",
    subtitle: "Core MDR",
    tagline: "Core MDR — 24/7 Host Protection, Automated Containment & Pre-LLM AI Triage",
    inheritsFrom: "SILVER",
    features: [
      "NikTiar Core EDR telemetry & alerting",
      "Automated active containment (host isolation)",
      "Pre-LLM whitelist AI veto gate",
      "NikTiar Aegis vulnerability sync",
      "NikTiar perimeter EASM sync",
    ],
  },
  {
    tier: "PLATINUM",
    name: "Platinum",
    subtitle: "Full MXDR",
    tagline: "Full MXDR — DeepSight NDR, Spectre Endpoint DFIR & Retrospective Sweeps",
    inheritsFrom: "GOLD",
    features: [
      "NikTiar DeepSight NDR",
      "NikTiar Spectre endpoint DFIR (process tree & artifacts)",
      "90-day retrospective threat sweeps",
      "NikTiar analytics OLAP & compressed archival",
      "NikTiar continuous compliance indicators",
    ],
  },
];

export type TierFeatureRow = {
  id: string;
  label: string;
  minTier: SubscriptionTier;
  group: "identity" | "mdr" | "mxdr";
};

export const TIER_FEATURE_MATRIX: TierFeatureRow[] = [
  { id: "okta_ad", label: "NikTiar identity telemetry (Okta / AD)", minTier: "SILVER", group: "identity" },
  { id: "mfa_fatigue", label: "MFA fatigue detection", minTier: "SILVER", group: "identity" },
  { id: "impossible_travel", label: "Impossible travel", minTier: "SILVER", group: "identity" },
  { id: "kerberoasting", label: "Kerberoasting detection", minTier: "SILVER", group: "identity" },
  { id: "portal_mfa", label: "Portal MFA", minTier: "SILVER", group: "identity" },
  { id: "retention_90", label: "90-day retention", minTier: "SILVER", group: "identity" },
  { id: "core_edr", label: "NikTiar Core EDR", minTier: "GOLD", group: "mdr" },
  { id: "host_isolation", label: "Automated active containment (host isolation)", minTier: "GOLD", group: "mdr" },
  { id: "ai_veto", label: "Pre-LLM whitelist AI veto gate", minTier: "GOLD", group: "mdr" },
  { id: "vuln_sync", label: "NikTiar Aegis vulnerability sync", minTier: "GOLD", group: "mdr" },
  { id: "easm_sync", label: "NikTiar perimeter EASM sync", minTier: "GOLD", group: "mdr" },
  { id: "ndr", label: "NikTiar DeepSight NDR", minTier: "PLATINUM", group: "mxdr" },
  { id: "spectre_dfir", label: "NikTiar Spectre DFIR (process tree / artifacts)", minTier: "PLATINUM", group: "mxdr" },
  { id: "retrospective", label: "90-day retrospective sweeps", minTier: "PLATINUM", group: "mxdr" },
  { id: "clickhouse", label: "NikTiar analytics OLAP & archival", minTier: "PLATINUM", group: "mxdr" },
  { id: "compliance", label: "NikTiar continuous compliance", minTier: "PLATINUM", group: "mxdr" },
];

export const TIER_RANK: Record<SubscriptionTier, number> = {
  SILVER: 1,
  GOLD: 2,
  PLATINUM: 3,
  CUSTOM: 0,
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

export function tierDisplayName(tier: SubscriptionTier | string): string {
  if (normalizeTier(tier) === "CUSTOM") return "Custom";
  return TIER_CATALOG.find((t) => t.tier === normalizeTier(tier))?.name ?? String(tier);
}
