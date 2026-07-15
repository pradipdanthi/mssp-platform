export interface BrandLogoConfig {
  markSrc: string;
  logoSrc: string;
  alt: string;
}

export interface AppConfig {
  productName: string;
  portalName: string;
  companyName: string;
  legalEntityName: string;
  tagline: string;
  supportEmail: string;
  portalDomain: string;
  documentTitle: string;
  logo: BrandLogoConfig;
}

const REQUIRED_STRING_KEYS: Array<keyof Omit<AppConfig, "logo">> = [
  "productName",
  "portalName",
  "companyName",
  "legalEntityName",
  "tagline",
  "supportEmail",
  "portalDomain",
  "documentTitle",
];

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

export function assertAppConfig(data: unknown): AppConfig {
  if (!data || typeof data !== "object") {
    throw new Error("app-config.json must be a JSON object");
  }

  const raw = data as Record<string, unknown>;
  for (const key of REQUIRED_STRING_KEYS) {
    if (!isNonEmptyString(raw[key])) {
      throw new Error(`app-config.json is missing required string field: ${key}`);
    }
  }

  const logo = raw.logo;
  if (!logo || typeof logo !== "object") {
    throw new Error("app-config.json is missing required object field: logo");
  }
  const logoRaw = logo as Record<string, unknown>;
  for (const key of ["markSrc", "logoSrc", "alt"] as const) {
    if (!isNonEmptyString(logoRaw[key])) {
      throw new Error(`app-config.json is missing required logo field: ${key}`);
    }
  }

  return {
    productName: raw.productName as string,
    portalName: raw.portalName as string,
    companyName: raw.companyName as string,
    legalEntityName: raw.legalEntityName as string,
    tagline: raw.tagline as string,
    supportEmail: raw.supportEmail as string,
    portalDomain: raw.portalDomain as string,
    documentTitle: raw.documentTitle as string,
    logo: {
      markSrc: logoRaw.markSrc as string,
      logoSrc: logoRaw.logoSrc as string,
      alt: logoRaw.alt as string,
    },
  };
}
