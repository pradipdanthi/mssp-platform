import { defineConfig, devices } from "@playwright/test";
import path from "path";
import { loadValidationEnv } from "./helpers/env";

loadValidationEnv();

const ADMIN_BASE = process.env.E2E_ADMIN_URL || "http://192.168.0.201:3000";
const CUSTOMER_BASE = process.env.E2E_CUSTOMER_URL || "http://192.168.0.201:3001";

/**
 * Live E2E against production nginx portals on VM 100.
 * Credentials: /opt/mssp-control/.secrets/validation.env (never committed).
 */
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["list"]],
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    ignoreHTTPSErrors: true,
  },
  projects: [
    {
      name: "admin-chromium",
      testMatch: /admin-.*\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        baseURL: ADMIN_BASE,
        storageState: undefined,
      },
    },
    {
      name: "customer-chromium",
      testMatch: /customer-.*\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        baseURL: CUSTOMER_BASE,
        storageState: undefined,
      },
    },
  ],
  outputDir: path.join(__dirname, "test-results"),
});
