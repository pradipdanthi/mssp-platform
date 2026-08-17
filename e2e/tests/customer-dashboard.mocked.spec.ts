import { test, expect } from "@playwright/test";
import { customerLogin, expectDashboardReady } from "../helpers/auth";
import { mockCustomerListBundle } from "../fixtures/mock-dashboard";
import { requireCred } from "../helpers/env";

test.describe("Customer dashboard (mocked) @mocked", () => {
  test("mock KPI and chart widgets render", async ({ page }) => {
    const shortCode = requireCred("CUSTOMER_ADMIN_TENANT");
    const bundle = mockCustomerListBundle(shortCode);

    await customerLogin(page);

    await page.route("**/api/customer/**", async (route) => {
      const url = route.request().url();
      if (url.includes("/incidents/")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(bundle.incidents),
        });
        return;
      }
      if (url.includes("/alerts/")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(bundle.alerts),
        });
        return;
      }
      if (url.includes("/recommendations/")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(bundle.recommendations),
        });
        return;
      }
      if (url.includes("/assets/")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(bundle.assets),
        });
        return;
      }
      if (url.includes("/reports/")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(bundle.reports),
        });
        return;
      }
      await route.continue();
    });

    await page.route("**/api/**/edr/**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      })
    );

    await page.reload();
    await expectDashboardReady(page, "customer-dashboard");

    await expect(page.getByTestId("widget-timeline")).toBeVisible();
    await expect(page.getByTestId("widget-severity-donut")).toBeVisible();
    await expect(page.getByTestId("widget-geo-heatmap")).toBeVisible();

    await expect(page.locator(".timeline-svg")).toBeVisible();
    await expect(page.locator(".severity-donut-svg")).toBeVisible();
    await expect(page.locator(".geo-heatmap-svg")).toBeVisible();

    await expect(page.getByText("Active Incidents").first()).toBeVisible();
    await expect(page.getByTestId("customer-dashboard").getByText("2").first()).toBeVisible();
  });
});
