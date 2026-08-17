import { test, expect } from "@playwright/test";
import { adminLogin, expectDashboardReady } from "../helpers/auth";
import {
  MOCK_ADMIN_DASHBOARD,
  MOCK_ADMIN_INCIDENTS,
  MOCK_ADMIN_TENANTS,
} from "../fixtures/mock-dashboard";

test.describe("Admin dashboard (mocked) @mocked", () => {
  test("mock KPI numbers and chart widgets render", async ({ page }) => {
    await adminLogin(page);

    await page.route("**/api/auth/**", (route) => route.continue());
    await page.route("**/api/admin/dashboard**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_ADMIN_DASHBOARD),
      });
    });
    await page.route("**/api/admin/incidents**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_ADMIN_INCIDENTS),
      });
    });
    await page.route("**/api/admin/tenants**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_ADMIN_TENANTS),
      });
    });
    await page.route("**/api/admin/service-consultation-requests/summary**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          pending_consultation: 1,
          under_review: 0,
          unreviewed_total: 1,
        }),
      })
    );
    await page.route("**/api/admin/appliances/command-summary**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          engine: "mock",
          appliances: {
            total: 2,
            online: 2,
            offline: 0,
            disk_used_gb_total: 1.5,
            log_ingest_rate_total: 0,
          },
          hunts: { running: 0, pending: 0, last_24h: 1 },
        }),
      })
    );
    await page.route("**/api/**/edr/**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          mean_time_to_contain_seconds: 45,
          telemetry_events_processed: 12,
          isolated_endpoints_count: 0,
        }),
      })
    );

    await page.goto("/dashboard");
    await expectDashboardReady(page, "admin-dashboard");

    await expect(page.getByText("Security Alerts").first()).toBeVisible();
    await expect(page.getByTestId("admin-dashboard").getByText("5").first()).toBeVisible();

    await expect(page.getByTestId("widget-timeline")).toBeVisible();
    await expect(page.getByTestId("widget-severity-donut")).toBeVisible();
    await expect(page.getByTestId("widget-geo-heatmap")).toBeVisible();

    await expect(page.locator(".timeline-svg")).toBeVisible();
    await expect(page.locator(".severity-donut-svg")).toBeVisible();
    await expect(page.locator(".geo-heatmap-svg")).toBeVisible();

    await expect(page.getByTestId("widget-severity-donut")).toContainText(
      /critical|high|Execution|Initial/i
    );
  });
});
