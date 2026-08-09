import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

import { credentialsFor, type DemoRole } from "./environment";

export interface BrowserIssueCollector {
  assertEmpty: () => void;
}

function redact(value: string): string {
  let result = value
    .replace(/Bearer\s+\S+/gi, "Bearer [REDACTED]")
    .replace(/\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/g, "[REDACTED_TOKEN]")
    .replace(/([?&](?:token|code|secret|password)=)[^&\s]+/gi, "$1[REDACTED]");
  for (const name of [
    "PLAYWRIGHT_DEMO_PASSWORD",
    "PLAYWRIGHT_MANAGER_PASSWORD",
    "PLAYWRIGHT_TECHNICIAN_PASSWORD",
    "PLAYWRIGHT_STOREKEEPER_PASSWORD",
  ]) {
    const secret = process.env[name];
    if (secret) result = result.replaceAll(secret, "[REDACTED]");
  }
  return result.slice(0, 300);
}

export function collectUnexpectedBrowserIssues(page: Page): BrowserIssueCollector {
  const issues: string[] = [];
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const anonymousRefresh =
      new URL(page.url()).pathname === "/login" &&
      /^Failed to load resource: the server responded with a status of 401 \(Unauthorized\)$/.test(
        message.text(),
      );
    if (!anonymousRefresh) issues.push(`console.error: ${redact(message.text())}`);
  });
  page.on("pageerror", (error) => issues.push(`pageerror: ${redact(error.message)}`));
  return {
    assertEmpty: () => expect(issues, "Unexpected browser errors").toEqual([]),
  };
}

export async function loginAs(page: Page, role: DemoRole) {
  const credentials = credentialsFor(role);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/login");
  const identifier = page.getByLabel(/Username|Tên đăng nhập|Tài khoản/i);
  const password = page.getByLabel(/Mật khẩu/i);
  await expect(identifier).toBeVisible();
  await identifier.fill(credentials.identifier);
  await password.fill(credentials.password);
  await page.getByRole("button", { name: /^Đăng nhập$/i }).click();
  await expect(page).not.toHaveURL(/\/login(?:[?#]|$)/, { timeout: 30_000 });
  await expect(page.locator("main h1").first()).toBeVisible({ timeout: 30_000 });
}

export async function loginWithKeyboard(page: Page, role: DemoRole) {
  const credentials = credentialsFor(role);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/login");
  const identifier = page.getByLabel(/Username|Tên đăng nhập|Tài khoản/i);
  await expect(identifier).toBeFocused();
  await page.keyboard.type(credentials.identifier);
  await page.keyboard.press("Tab");
  await expect(page.getByLabel(/Mật khẩu/i)).toBeFocused();
  await page.keyboard.type(credentials.password);
  await page.keyboard.press("Enter");
  await expect(page).not.toHaveURL(/\/login(?:[?#]|$)/, { timeout: 30_000 });
  await expect(page.locator("main h1").first()).toBeVisible({ timeout: 30_000 });
}

export async function logoutIfAuthenticated(page: Page) {
  const logout = page.getByRole("button", { name: /^Đăng xuất$/i });
  if (!(await logout.isVisible().catch(() => false))) return;
  await logout.click();
  await expect(page).toHaveURL(/\/login(?:[?#]|$)/);
}

export async function tabToHref(page: Page, href: string, maximumTabs = 40) {
  for (let index = 0; index < maximumTabs; index += 1) {
    await page.keyboard.press("Tab");
    const focusedHref = await page.evaluate(() =>
      document.activeElement instanceof HTMLAnchorElement
        ? document.activeElement.getAttribute("href")
        : null,
    );
    if (focusedHref === href) return;
  }
  throw new Error(`Keyboard focus did not reach ${href}.`);
}

export async function assertNoDocumentOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    htmlClientWidth: document.documentElement.clientWidth,
    htmlScrollWidth: document.documentElement.scrollWidth,
    bodyClientWidth: document.body.clientWidth,
    bodyScrollWidth: document.body.scrollWidth,
  }));
  expect(dimensions.htmlScrollWidth, "documentElement overflow").toBeLessThanOrEqual(
    dimensions.htmlClientWidth + 1,
  );
  expect(dimensions.bodyScrollWidth, "body overflow").toBeLessThanOrEqual(
    dimensions.bodyClientWidth + 1,
  );
}

export async function assertNoSeriousAccessibilityViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const summary = results.violations
    .filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))
    .map((violation) => ({
      id: violation.id,
      impact: violation.impact,
      affectedNodes: violation.nodes.length,
    }));
  expect(summary, "Serious WCAG A/AA violations").toEqual([]);
}

export async function assertLogicalHeadingOrder(page: Page) {
  const levels = await page.locator("main h1, main h2, main h3, main h4, main h5, main h6")
    .evaluateAll((headings) => headings.map((heading) => Number(heading.tagName.slice(1))));
  expect(levels.length, "The main content needs a semantic heading").toBeGreaterThan(0);
  expect(levels[0], "The first main-content heading must be h1").toBe(1);
  for (let index = 1; index < levels.length; index += 1) {
    expect(
      levels[index] - levels[index - 1],
      `Heading level jumps from h${levels[index - 1]} to h${levels[index]}`,
    ).toBeLessThanOrEqual(1);
  }
}
