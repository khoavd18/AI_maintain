import { expect, test } from "@playwright/test";

import {
  assertNoDocumentOverflow,
  assertNoSeriousAccessibilityViolations,
  assertLogicalHeadingOrder,
  collectUnexpectedBrowserIssues,
  loginAs,
  loginWithKeyboard,
  logoutIfAuthenticated,
  tabToHref,
} from "../support/browser";

test.describe("desktop maintenance journeys", () => {
  test.afterEach(async ({ page }) => {
    await logoutIfAuthenticated(page);
  });

  test("manager sees actionable priorities and can open equipment", async ({ page }) => {
    const browserIssues = collectUnexpectedBrowserIssues(page);
    await loginAs(page, "manager");

    await expect(page.getByRole("heading", { level: 1, name: /Tổng quan/i })).toBeVisible();
    await expect(
      page.getByText(/Sự cố cần xử lý|Phiếu sự cố cần xử lý|Ticket đang mở/i).first(),
    ).toBeVisible();
    await expect(
      page.getByText(/Lệnh công việc quá hạn|Phiếu công việc quá hạn|Work order quá hạn/i).first(),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: /Ưu tiên|Cần chú ý/i }).first()).toBeVisible();
    await assertNoDocumentOverflow(page);
    await assertNoSeriousAccessibilityViolations(page);
    await assertLogicalHeadingOrder(page);

    await page.getByRole("link", { name: /^Thiết bị$/i }).first().click();
    await expect(page).toHaveURL(/\/assets$/);
    await expect(page.getByRole("heading", { level: 1, name: /^Thiết bị$/i })).toBeVisible();
    await expect(page.getByLabel(/Tìm thiết bị/i)).toBeVisible();

    const equipmentLink = page.locator('main a[href^="/assets/"]:visible').first();
    await expect(equipmentLink).toBeVisible();
    await equipmentLink.click();
    await expect(page).toHaveURL(/\/assets\/[^/?#]+$/);
    await expect(page.locator("main h1").first()).toBeVisible();
    await assertNoDocumentOverflow(page);
    browserIssues.assertEmpty();
  });

  test("manager can open ticket and work-order records without raw API errors", async ({ page }) => {
    const browserIssues = collectUnexpectedBrowserIssues(page);
    await loginAs(page, "manager");

    await page.goto("/tickets");
    await expect(page.getByRole("heading", { level: 1, name: /Sự cố|Phiếu sự cố/i })).toBeVisible();
    const ticketLink = page.getByRole("link", { name: "Xem phiếu" }).first();
    await expect(ticketLink).toBeVisible();
    const ticketHref = await ticketLink.getAttribute("href");
    expect(ticketHref).toMatch(/^\/tickets\/[^/?#]+$/);
    await page.goto(ticketHref!);
    await expect(page).toHaveURL(/\/tickets\/[^/?#]+$/);
    await expect(page.locator("main h1").first()).toBeVisible();
    const nextActions = page.locator("section").filter({
      has: page.getByRole("heading", { name: "Hành động tiếp theo" }),
    });
    await expect(nextActions).toBeVisible();
    await expect(nextActions.getByRole("button").first()).toBeVisible();

    await page.goto("/work-orders");
    await expect(page.getByRole("heading", { level: 1, name: /Lệnh công việc|Phiếu công việc/i })).toBeVisible();
    await expect(page.getByText("Không có lệnh công việc phù hợp")).toBeVisible();
    await page.getByRole("button", { name: "Tạo lệnh công việc" }).click();
    await expect(page.getByRole("heading", { name: "Tạo lệnh công việc" })).toBeVisible();
    await expect(page.getByLabel("Thiết bị", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Tạo lệnh công việc" })).toBeDisabled();
    await page.getByRole("button", { name: "Đóng biểu mẫu" }).click();
    await expect(page.getByRole("heading", { name: "Tạo lệnh công việc" })).not.toBeVisible();
    browserIssues.assertEmpty();

    await page.goto("/assets/PLAYWRIGHT-ASSET-DOES-NOT-EXIST");
    await expect(page.getByText(/Không tìm thấy|không tồn tại/i).first()).toBeVisible();
    await expect(page.locator("main")).not.toContainText(
      /Traceback|Internal Server Error|request[_ -]?id|sqlalchemy|postgresql:\/\//i,
    );
    await assertNoDocumentOverflow(page);
  });

  test("Copilot explains grounded, mismatch, and insufficient-evidence states", async ({ page }) => {
    test.setTimeout(240_000);
    const browserIssues = collectUnexpectedBrowserIssues(page);
    await loginAs(page, "manager");
    await page.goto("/copilot?asset=GENERATOR_002");
    await expect(page.getByRole("heading", { level: 1, name: /Trợ lý bảo trì/i })).toBeVisible();

    const question = page.getByLabel(/Câu hỏi bảo trì|Câu hỏi cho/i);
    await question.fill("Máy phát điện không khởi động thì cần kiểm tra những gì?");
    await page.getByRole("button", { name: /Gửi câu hỏi/i }).click();
    await expect(page.getByText("Câu trả lời có nguồn tham khảo").last()).toBeVisible({
      timeout: 90_000,
    });
    await expect(page.getByRole("heading", { name: /Nguồn tham khảo/i }).last()).toBeVisible();
    await expect(page.getByText(/Cảnh báo an toàn/i).last()).toBeVisible();

    await question.fill("Máy bơm nước bị rung thì cần kiểm tra gì?");
    await question.press("Enter");
    await expect(page.getByText("Cần xác nhận lại thiết bị").last()).toBeVisible({
      timeout: 60_000,
    });

    // The canonical demo has a generator incident categorized as a sensor issue.
    // That filter intentionally has no matching generator SOP, so the real UI can
    // demonstrate the insufficient-evidence state without creating test records.
    await page.goto("/copilot?asset=GENERATOR_006");
    await expect(page.getByText(/Mã thiết bị:\s*GENERATOR_006/i)).toBeVisible();
    const relatedIncident = page.getByLabel(/Sự cố liên quan|Ticket liên quan/i);
    await relatedIncident.click();
    const sensorIncident = page.getByRole("option", { name: /TCK-/i }).first();
    await expect(sensorIncident).toBeVisible();
    await sensorIncident.click();
    await question.fill("Máy phát điện không khởi động thì cần kiểm tra gì?");
    await page.getByRole("button", { name: /Gửi câu hỏi/i }).click();
    await expect(page.getByText("Không đủ tài liệu để kết luận").last()).toBeVisible({
      timeout: 60_000,
    });

    await expect(page.locator("main")).not.toContainText(
      /\bQdrant\b|\bRAG\b|\bLLM\b|Provider:|(?:chunk|doc|source)[ _-]?id|llm_grounded|asset_context_mismatch|insufficient_evidence/i,
    );
    await assertNoDocumentOverflow(page);
    browserIssues.assertEmpty();
  });

  test("role navigation and denied routes remain understandable", async ({ page }) => {
    const browserIssues = collectUnexpectedBrowserIssues(page);
    await loginAs(page, "technician");
    await expect(page).toHaveURL(/\/work-orders(?:[?#]|$)/);
    await expect(page.getByRole("link", { name: /Lệnh công việc|Phiếu công việc/i }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /Kho phụ tùng|Kho vật tư/i })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /Người dùng/i })).toHaveCount(0);
    await page.goto("/admin/users");
    await expect(page.getByRole("heading", { name: /Không có quyền truy cập/i })).toBeVisible();
    await expect(page.locator("main")).toContainText(/vai trò|khu vực được phép/i);
    await expect(page.locator("main")).not.toContainText(/\bpermission\b|[a-z_]+:[a-z_]+/i);
    await logoutIfAuthenticated(page);

    await loginAs(page, "storekeeper");
    await expect(page).toHaveURL(/\/inventory(?:[?#]|$)/);
    await expect(page.getByRole("link", { name: /Kho phụ tùng|Kho vật tư/i }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /Trợ lý bảo trì/i })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /Người dùng/i })).toHaveCount(0);
    await page.getByText("Nghiệp vụ kho", { exact: true }).click();
    await page.getByRole("link", { name: "Nhập kho", exact: true }).click();
    await expect(page).toHaveURL(/\/inventory\/receiving$/);
    await expect(page.getByRole("heading", { level: 1, name: "Nhập kho" })).toBeVisible();
    await expect(page.getByLabel(/^Số lượng/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Xác nhận nhập kho" })).toBeDisabled();
    browserIssues.assertEmpty();
  });

  test("primary login and equipment path works with keyboard only", async ({ page }) => {
    const browserIssues = collectUnexpectedBrowserIssues(page);
    await page.goto("/login");
    await expect(page.getByRole("heading", { level: 1, name: /Đăng nhập/i })).toBeVisible();
    await assertNoSeriousAccessibilityViolations(page);
    await loginWithKeyboard(page, "manager");
    await tabToHref(page, "/assets");
    const focusVisible = await page.evaluate(() => {
      const element = document.activeElement;
      return element instanceof HTMLElement && element.matches(":focus-visible");
    });
    expect(focusVisible).toBe(true);
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/assets$/);
    await expect(page.getByLabel(/Tìm thiết bị/i)).toBeVisible();
    browserIssues.assertEmpty();
  });
});
