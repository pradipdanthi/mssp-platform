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
  salesEmail: string;
  portalDomain: string;
  adminDomain: string;
  marketingDomain: string;
  footerCopyright: string;
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
  "salesEmail",
  "portalDomain",
  "adminDomain",
  "marketingDomain",
  "footerCopyright",
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
    salesEmail: raw.salesEmail as string,
    portalDomain: raw.portalDomain as string,
    adminDomain: raw.adminDomain as string,
    marketingDomain: raw.marketingDomain as string,
    footerCopyright: raw.footerCopyright as string,
    documentTitle: raw.documentTitle as string,
    logo: {
      markSrc: logoRaw.markSrc as string,
      logoSrc: logoRaw.logoSrc as string,
      alt: logoRaw.alt as string,
    },
  };
}

/** Build https:// URLs for portal entry points on kevantic.com. */
export function portalUrl(domain: string, path = ""): string {
  const host = domain.replace(/^https?:\/\//, "").replace(/\/+$/, "");
  const suffix = path.startsWith("/") ? path : path ? `/${path}` : "";
  return `https://${host}${suffix}`;
}
