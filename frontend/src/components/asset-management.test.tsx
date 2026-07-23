import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AssetFormSheet } from "@/components/asset-form-sheet";
import { AssetManagementTabs } from "@/components/asset-management-tabs";
import { MobileAssetLookup } from "@/components/mobile-asset-lookup";
import type { UserResponse } from "@/lib/api/schemas";
import { permissions } from "@/lib/auth";
import {
  assetDetailsFixture,
  assetHistoryFixture,
  assetOptionsFixture,
  assetProfileFixture,
  assetQrFixture,
  locationFixture,
  ticketsFixture,
} from "@/test/fixtures";
import { administratorTestUser, mockApi, renderWithQuery } from "@/test/test-utils";

const helpdeskUser: UserResponse = {
  ...administratorTestUser,
  id: "44444444-4444-4444-8444-444444444444",
  username: "helpdesk.test",
  display_name: "Helpdesk test",
  role: "helpdesk",
  role_display_name: "Helpdesk",
  permissions: [permissions.assetsRead, permissions.ticketsRead],
};

describe("asset management UI", () => {
  it("creates an asset with the selected canonical location", async () => {
    const created = { ...assetProfileFixture, asset_id: "TEST_ASSET_001", asset_name: "Máy phát điện test" };
    const fetchMock = mockApi({
      "/assets/options": assetOptionsFixture,
      "/locations": [locationFixture],
      "POST /assets": created,
    });
    const saved = vi.fn();
    renderWithQuery(<AssetFormSheet open onOpenChange={vi.fn()} onSaved={saved} />);

    fireEvent.change(screen.getByLabelText("Asset ID"), { target: { value: "TEST_ASSET_001" } });
    fireEvent.change(screen.getByLabelText("Tên thiết bị"), { target: { value: "Máy phát điện test" } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Tạo asset" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Tạo asset" }));

    await waitFor(() => expect(saved).toHaveBeenCalledWith("TEST_ASSET_001"));
    const write = fetchMock.mock.calls.find((call) => String(call[0]).endsWith("/assets") && call[1]?.method === "POST");
    expect(write).toBeDefined();
    expect(JSON.parse(String(write?.[1]?.body))).toMatchObject({
      asset_id: "TEST_ASSET_001",
      location_id: locationFixture.id,
      lifecycle_status: "active",
    });
  });

  it("validates create input before a write and surfaces stale update conflicts", async () => {
    const invalidFetch = mockApi({
      "/assets/options": assetOptionsFixture,
      "/locations": [locationFixture],
    });
    const invalid = renderWithQuery(<AssetFormSheet open onOpenChange={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Asset ID"), { target: { value: "TEST_ASSET_001" } });
    fireEvent.change(screen.getByLabelText("Tên thiết bị"), { target: { value: "Máy phát điện test" } });
    fireEvent.change(screen.getByLabelText("Chu kỳ (ngày)"), { target: { value: "0" } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Tạo asset" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Tạo asset" }));
    expect(await screen.findByText("Biểu mẫu chưa hợp lệ. Hãy kiểm tra các trường được đánh dấu.")).toBeInTheDocument();
    expect(invalidFetch.mock.calls.some((call) => call[1]?.method === "POST")).toBe(false);
    invalid.unmount();

    const reload = vi.fn();
    mockApi({
      "/assets/options": assetOptionsFixture,
      "/locations": [locationFixture],
      "PATCH /assets/GENERATOR_002": { status: 409, body: { detail: "Hồ sơ đã được người khác cập nhật." } },
    });
    renderWithQuery(<AssetFormSheet open onOpenChange={vi.fn()} profile={assetProfileFixture} onReload={reload} />);
    fireEvent.change(screen.getByLabelText("Nhà sản xuất"), { target: { value: "Cummins Việt Nam" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu hồ sơ" }));
    expect(await screen.findByText("Hồ sơ đã được người khác cập nhật.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Tải hồ sơ mới nhất" }));
    expect(reload).toHaveBeenCalledOnce();
  });

  it("enforces permission-aware actions and confirms lifecycle changes", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = mockApi({
      "/assets/options": assetOptionsFixture,
      "POST /assets/GENERATOR_002/lifecycle-transition": {
        ...assetProfileFixture,
        lifecycle_status: "inactive",
        lifecycle_status_display: "Tạm ngừng",
        version: 2,
      },
    });
    const admin = renderWithQuery(<AssetManagementTabs profile={assetProfileFixture} onReload={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Áp dụng lifecycle" }));
    await waitFor(() => expect(fetchMock.mock.calls.some((call) => String(call[0]).includes("lifecycle-transition") && call[1]?.method === "POST")).toBe(true));
    expect(confirm).toHaveBeenCalled();
    admin.unmount();

    mockApi({ "/assets/options": assetOptionsFixture });
    renderWithQuery(<AssetManagementTabs profile={assetProfileFixture} onReload={vi.fn()} />, helpdeskUser);
    expect(screen.queryByRole("button", { name: /Chỉnh sửa hồ sơ/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Archive asset/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Tệp đính kèm" })).not.toBeInTheDocument();
  });

  it("rejects unsafe attachments and renders QR plus unified history", async () => {
    mockApi({
      "/assets/options": assetOptionsFixture,
      "/assets/GENERATOR_002/attachments": [],
      "/assets/GENERATOR_002/qr": assetQrFixture,
      "/assets/GENERATOR_002/history": assetHistoryFixture,
    });
    renderWithQuery(<AssetManagementTabs profile={assetProfileFixture} onReload={vi.fn()} />);

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Tệp đính kèm" }), { button: 0, ctrlKey: false });
    const input = await screen.findByLabelText("Chọn tệp");
    fireEvent.change(input, { target: { files: [new File(["MZ"], "payload.exe", { type: "application/octet-stream" })] } });
    expect(await screen.findByText("Chỉ chấp nhận PDF, PNG, JPG hoặc JPEG.")).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole("tab", { name: "QR" }), { button: 0, ctrlKey: false });
    expect(await screen.findByRole("img", { name: "QR tra cứu GENERATOR_002" })).toBeInTheDocument();
    expect(screen.getByText(assetQrFixture.lookup_url)).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Lịch sử" }), { button: 0, ctrlKey: false });
    expect(await screen.findByText("Đã đăng ký asset GENERATOR_002.")).toBeInTheDocument();
  });

  it("supports the authenticated mobile QR lookup workflow", async () => {
    mockApi({
      [`/asset-lookup/${assetQrFixture.lookup_token}`]: assetProfileFixture,
      "/assets/GENERATOR_002/details": assetDetailsFixture,
      "/tickets": ticketsFixture,
    });
    const { container } = renderWithQuery(<MobileAssetLookup lookupToken={assetQrFixture.lookup_token} />);

    expect(await screen.findByRole("heading", { name: "Máy phát điện dự phòng 002" })).toBeInTheDocument();
    expect(screen.getByText(locationFixture.breadcrumb)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tạo ticket" })).toBeEnabled();
    expect(screen.getByRole("link", { name: "Mở Copilot" })).toHaveAttribute("href", "/copilot?asset=GENERATOR_002");
    expect(container.firstElementChild).toHaveClass("overflow-x-hidden");
  });
});
