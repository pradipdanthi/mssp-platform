import { AppConfig, assertAppConfig } from "./types";

const APP_CONFIG_URL = "/app-config.json";

export async function loadAppConfig(): Promise<AppConfig> {
  let response: Response;
  try {
    response = await fetch(APP_CONFIG_URL, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
  } catch {
    throw new Error("Unable to load application branding configuration.");
  }

  if (!response.ok) {
    throw new Error(`Unable to load application branding configuration (HTTP ${response.status}).`);
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new Error("Application branding configuration is not valid JSON.");
  }

  return assertAppConfig(data);
}
