import { test, expect } from "@playwright/test";
import { adminLogin } from "../helpers/auth";

test.describe("Admin list filters (live)", () => {
  test.beforeEach(async ({ page }) => {
    await adminLogin(page);
  });

  test("Incidents severity filter updates URL and toolbar", async ({ page }) => {
    await page.goto("/incidents");
    await expect(page.getByRole("heading", { name: /Incidents/i })).toBeVisible();
    await expect(page.getByTestId("list-toolbar")).toBeVisible({ timeout: 20_000 });

    const severity = page.getByTestId("list-severity-filter");
    await severity.selectOption("high");
    await expect(page).toHaveURL(/severity=high/);
    await expect(severity).toHaveValue("high");

    await severity.selectOption("");
    await expect(page).not.toHaveURL(/severity=/);
  });

  test("Alerts page loads with search toolbar", async ({ page }) => {
    await page.goto("/alerts");
    await expect(page.getByRole("heading", { name: /Alerts/i })).toBeVisible();
    await expect(page.getByTestId("list-toolbar")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("list-search")).toBeVisible();

    await page.getByTestId("list-search").fill("ssh");
    await page.getByTestId("list-search-submit").click();
    await expect(page).toHaveURL(/q=ssh/);
  });
});
