import { test, expect } from "@playwright/test";
import { adminLogin, expectDashboardReady } from "../helpers/auth";

test.describe("Admin dashboard (live)", () => {
  test.beforeEach(async ({ page }) => {
    await adminLogin(page);
  });

  test("dashboard shell and chart widgets load", async ({ page }) => {
    await expectDashboardReady(page, "admin-dashboard");

    await expect(page.getByTestId("admin-dashboard-welcome")).toBeVisible();
    await expect(page.getByTestId("admin-dashboard-controls")).toBeVisible();
    await expect(page.getByTestId("customer-scope")).toBeVisible();

    // KPI tiles (labels from live dashboard)
    await expect(page.getByText("Security Alerts").first()).toBeVisible();
    await expect(page.getByText(/Active Incidents|Open incidents/i).first()).toBeVisible();

    // Chart widgets
    await expect(page.getByTestId("admin-analytics-row")).toBeVisible();
    await expect(page.getByTestId("widget-timeline")).toBeVisible();
    await expect(page.getByTestId("widget-severity-donut")).toBeVisible();
    await expect(page.getByTestId("widget-geo-heatmap")).toBeVisible();

    await expect(page.getByText(/Incidents over time/i).first()).toBeVisible();
    await expect(page.getByText(/Alerts by Severity|Alerts/i).first()).toBeVisible();
    await expect(page.locator(".timeline-svg, .severity-donut-svg, .geo-heatmap-svg").first()).toBeVisible();
  });

  test("time-window filter toggles 24h / 7d", async ({ page }) => {
    await expectDashboardReady(page, "admin-dashboard");

    const chip24 = page.getByTestId("filter-window-24h");
    const chip7d = page.getByTestId("filter-window-7d");

    await expect(chip24).toHaveAttribute("aria-pressed", "true");
    await chip7d.click();
    await expect(chip7d).toHaveAttribute("aria-pressed", "true");
    await expect(chip24).toHaveAttribute("aria-pressed", "false");
    await expect(page.getByText(/Incidents over time \(7d\)/i)).toBeVisible();

    await chip24.click();
    await expect(chip24).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText(/Incidents over time \(24h\)/i)).toBeVisible();
  });

  test("customer scope control is interactive", async ({ page }) => {
    await expectDashboardReady(page, "admin-dashboard");
    const scope = page.getByTestId("customer-scope");
    await expect(scope).toBeVisible();
    const options = scope.locator("option");
    await expect(options.first()).toContainText(/All customers/i);
    // Switch to first real tenant if present, then back to all
    const count = await options.count();
    if (count > 1) {
      const value = await options.nth(1).getAttribute("value");
      if (value) {
        await scope.selectOption(value);
        await expect(scope).toHaveValue(value);
        await scope.selectOption("all");
        await expect(scope).toHaveValue("all");
      }
    }
  });
});
