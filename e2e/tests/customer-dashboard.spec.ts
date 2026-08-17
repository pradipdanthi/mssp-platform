import { test, expect } from "@playwright/test";
import { customerLogin, expectDashboardReady } from "../helpers/auth";

test.describe("Customer dashboard (live)", () => {
  test.beforeEach(async ({ page }) => {
    await customerLogin(page);
  });

  test("dashboard shell and chart widgets load", async ({ page }) => {
    await expectDashboardReady(page, "customer-dashboard");

    await expect(page.getByTestId("customer-dashboard-welcome")).toBeVisible();
    await expect(page.getByText("Security Alerts").first()).toBeVisible();
    await expect(page.getByText(/Active Incidents/i).first()).toBeVisible();

    await expect(page.getByTestId("customer-analytics-row")).toBeVisible();
    await expect(page.getByTestId("widget-timeline")).toBeVisible();
    await expect(page.getByTestId("widget-severity-donut")).toBeVisible();
    await expect(page.getByTestId("widget-geo-heatmap")).toBeVisible();

    await expect(page.getByText(/Incidents over time/i).first()).toBeVisible();
    await expect(page.locator(".timeline-svg, .severity-donut-svg, .geo-heatmap-svg").first()).toBeVisible();
  });

  test("alerts list filters work", async ({ page }) => {
    await page.goto("/alerts");
    await expect(page.getByRole("heading", { name: /Alerts/i })).toBeVisible();
    await expect(page.getByTestId("list-toolbar")).toBeVisible({ timeout: 20_000 });

    const severity = page.getByTestId("list-severity-filter");
    if (await severity.count()) {
      await severity.selectOption("high");
      await expect(page).toHaveURL(/severity=high/);
    }

    await page.getByTestId("list-search").fill("test");
    await page.getByTestId("list-search-submit").click();
    await expect(page).toHaveURL(/q=test/);
  });
});
