/** Market-standard industry + commercial picklists for MSSP customer onboarding. */

export const INDUSTRY_OPTIONS: string[] = [
  "Aerospace & Defense",
  "Agriculture",
  "Automotive",
  "Banking & Financial Services",
  "Business Services / Consulting",
  "Construction",
  "Education",
  "Energy & Utilities",
  "Government / Public Sector",
  "Healthcare & Life Sciences",
  "Hospitality & Travel",
  "Insurance",
  "Legal",
  "Manufacturing",
  "Media & Entertainment",
  "Mining & Metals",
  "Non-profit",
  "Oil & Gas",
  "Pharmaceuticals",
  "Professional Services",
  "Real Estate",
  "Retail & E-commerce",
  "Technology / Software",
  "Telecommunications",
  "Transportation & Logistics",
  "Other",
];

export const COMPANY_SIZE_OPTIONS: string[] = [
  "1-50",
  "51-200",
  "201-1000",
  "1001-5000",
  "5000+",
];

export const DATA_RESIDENCY_OPTIONS: string[] = [
  "India",
  "European Union",
  "United Kingdom",
  "United States",
  "Middle East",
  "Asia Pacific",
  "Other",
];

export const PREFERRED_LANGUAGE_OPTIONS: { value: string; label: string }[] = [
  { value: "en", label: "English" },
  { value: "hi", label: "Hindi" },
  { value: "ar", label: "Arabic" },
  { value: "de", label: "German" },
  { value: "es", label: "Spanish" },
  { value: "fr", label: "French" },
  { value: "pt", label: "Portuguese" },
  { value: "zh", label: "Chinese" },
  { value: "ja", label: "Japanese" },
  { value: "other", label: "Other" },
];

/** Default contracted services for a new MSSP customer (core package only). */
export const DEFAULT_CREATE_ENTITLEMENTS = {
  wazuh_siem: true,
  wazuh_retention_days: 90,
  thehive_mode: "full",
  greenbone_enabled: false,
  greenbone_cadence: "monthly",
  shuffle_mode: "off",
  zeek_enabled: false,
  misp_enabled: false,
  velociraptor_enabled: false,
  continuous_compliance_enabled: false,
  external_attack_surface_enabled: false,
  cloud_identity_protection_enabled: false,
  roadmap_notes: null as string | null,
};
