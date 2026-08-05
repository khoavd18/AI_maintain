import { expect, test } from "@playwright/test";

import {
  assertNoDocumentOverflow,
  assertNoSeriousAccessibilityViolations,
  collectUnexpectedBrowserIssues,
  loginAs,
  logoutIfAuthenticated,
} from "../support/browser";

test.describe("mobile usability", () => {
  test.afterEach(async ({ page }) => {
    await logoutIfAuthenticated(page);
  });

  test("mobile navigation exposes relevant destinations and closes after navigation", async ({ page }) => {
    const browserIssues = collectUnexpectedBrowserIssues(page);
    await loginAs(page, "manager");
    await assertNoDocumentOverflow(page);

    await page.getByRole("button", { name: /Mở menu/i }).click();
    const mobileNavigation = page.getByRole("navigation", { name: /Điều hướng chính/i }).last();
    await expect(mobileNavigation).toBeVisible();
    await mobileNavigation.getByRole("link", { name: /^Thiết bị$/i }).click();
    await expect(page).toHaveURL(/\/assets$/);
    await expect(page.getByRole("heading", { level: 1, name: /^Thiết bị$/i })).toBeVisible();
    await expect(mobileNavigation).not.toBeVisible();
    await assertNoDocumentOverflow(page);
    await assertNoSeriousAccessibilityViolations(page);
    browserIssues.assertEmpty();
  });

  test("primary mobile pages do not create document-level horizontal overflow", async ({ page }) => {
    const browserIssues = collectUnexpectedBrowserIssues(page);
    await loginAs(page, "manager");

    for (const route of ["/", "/assets", "/tickets", "/work-orders", "/inventory", "/copilot?asset=GENERATOR_002"]) {
      await page.goto(route);
      await expect(page.locator("main h1").first()).toBeVisible({ timeout: 30_000 });
      await assertNoDocumentOverflow(page);
    }

    browserIssues.assertEmpty();
  });
});
