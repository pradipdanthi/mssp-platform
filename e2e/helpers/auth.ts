import { expect, type Page } from "@playwright/test";
import { requireCred } from "./env";

export async function adminLogin(page: Page): Promise<void> {
  const email = requireCred("PLATFORM_ADMIN_EMAIL");
  const password = requireCred("PLATFORM_ADMIN_PASSWORD");
  await page.goto("/login");
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });
  await expect(page.getByTestId("admin-dashboard")).toBeVisible({ timeout: 20_000 });
}

export async function customerLogin(page: Page): Promise<void> {
  const email = requireCred("CUSTOMER_ADMIN_EMAIL");
  const password = requireCred("CUSTOMER_ADMIN_PASSWORD");
  await page.goto("/login");
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });
  await expect(page.getByTestId("customer-dashboard")).toBeVisible({ timeout: 20_000 });
}

/** Wait until dashboard left loading and did not hit a hard error. */
export async function expectDashboardReady(page: Page, rootTestId: string): Promise<void> {
  const root = page.getByTestId(rootTestId);
  await expect(root).toBeVisible();
  await expect(root.getByText(/Loading workspace/i)).toHaveCount(0, { timeout: 25_000 });
  await expect(root.locator(".state-error")).toHaveCount(0);
}
