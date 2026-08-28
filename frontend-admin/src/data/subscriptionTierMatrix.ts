export type SubscriptionTier = "SILVER" | "GOLD" | "PLATINUM";

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
      "Okta / Active Directory ingest",
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
      "Wazuh EDR telemetry & alerting",
      "Automated active containment (host isolation)",
      "Pre-LLM AI veto gate",
      "Vulnerability management sync",
      "External attack surface (EASM) sync",
    ],
  },
  {
    tier: "PLATINUM",
    name: "Platinum",
    subtitle: "Full MXDR",
    tagline: "Full MXDR — DeepSight NDR, Spectre Endpoint DFIR & Retrospective Sweeps",
    inheritsFrom: "GOLD",
    features: [
      "Suricata / Zeek NDR (NikTiar DeepSight)",
      "Spectre endpoint DFIR (process tree & artifacts)",
      "90-day retrospective threat sweeps",
      "ClickHouse OLAP analytics & log archiver",
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
  { id: "okta_ad", label: "Okta / AD ingest", minTier: "SILVER", group: "identity" },
  { id: "mfa_fatigue", label: "MFA fatigue detection", minTier: "SILVER", group: "identity" },
  { id: "impossible_travel", label: "Impossible travel", minTier: "SILVER", group: "identity" },
  { id: "kerberoasting", label: "Kerberoasting detection", minTier: "SILVER", group: "identity" },
  { id: "portal_mfa", label: "Portal MFA", minTier: "SILVER", group: "identity" },
  { id: "retention_90", label: "90-day retention", minTier: "SILVER", group: "identity" },
  { id: "wazuh_edr", label: "Wazuh EDR", minTier: "GOLD", group: "mdr" },
  { id: "host_isolation", label: "Automated active containment (host isolation)", minTier: "GOLD", group: "mdr" },
  { id: "ai_veto", label: "Pre-LLM AI veto gate", minTier: "GOLD", group: "mdr" },
  { id: "vuln_sync", label: "Vulnerability management sync", minTier: "GOLD", group: "mdr" },
  { id: "easm_sync", label: "EASM sync", minTier: "GOLD", group: "mdr" },
  { id: "ndr", label: "Suricata / Zeek NDR (DeepSight)", minTier: "PLATINUM", group: "mxdr" },
  { id: "spectre_dfir", label: "Spectre endpoint DFIR (process tree / artifacts)", minTier: "PLATINUM", group: "mxdr" },
  { id: "retrospective", label: "90-day retrospective sweeps", minTier: "PLATINUM", group: "mxdr" },
  { id: "clickhouse", label: "ClickHouse OLAP & archiver", minTier: "PLATINUM", group: "mxdr" },
];

export const TIER_RANK: Record<SubscriptionTier, number> = {
  SILVER: 1,
  GOLD: 2,
  PLATINUM: 3,
};

export function normalizeTier(tier?: string | null): SubscriptionTier {
  const value = (tier || "SILVER").toUpperCase();
  if (value === "GOLD" || value === "PLATINUM") return value;
  return "SILVER";
}

export function tierDisplayName(tier: SubscriptionTier): string {
  return TIER_CATALOG.find((t) => t.tier === tier)?.name ?? tier;
}
