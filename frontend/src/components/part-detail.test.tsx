import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PartDetail } from "@/components/part-detail";
import {
  balanceFixture,
  inventoryIds,
  movementFixture,
  page,
  partFixture,
} from "@/test/inventory-fixtures";
import { mockApi, renderWithQuery } from "@/test/test-utils";

describe("part lifecycle controls", () => {
  it("collects an archive reason in the page before calling the named action", async () => {
    const archivedPart = {
      ...partFixture,
      lifecycle_status: "archived",
      lifecycle_status_display: "Đã lưu trữ",
      archived_at: "2026-08-03T01:00:00Z",
      archive_reason: "Thay thế bằng mã phụ tùng mới",
      version: 2,
      updated_at: "2026-08-03T01:00:00Z",
    } as const;
    const fetchMock = mockApi({
      [`/parts/${inventoryIds.part}`]: partFixture,
      "/inventory/balances": page([balanceFixture]),
      "/inventory/movements": page([movementFixture]),
      [`POST /parts/${inventoryIds.part}/archive`]: archivedPart,
    });

    renderWithQuery(<PartDetail partId={inventoryIds.part} />);

    expect(
      await screen.findByRole("button", { name: "Ngừng kích hoạt" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Lưu trữ" }));

    expect(
      screen.getByRole("heading", { name: "Lưu trữ mã phụ tùng?" }),
    ).toBeInTheDocument();
    const confirmButton = screen.getByRole("button", {
      name: "Xác nhận lưu trữ",
    });
    expect(confirmButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Lý do lưu trữ"), {
      target: { value: "  Thay thế bằng mã phụ tùng mới  " },
    });
    expect(confirmButton).toBeEnabled();
    fireEvent.click(confirmButton);

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(`/parts/${inventoryIds.part}/archive`),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            expected_version: partFixture.version,
            reason: "Thay thế bằng mã phụ tùng mới",
          }),
        }),
      ),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Đã lưu trữ mã phụ tùng.",
    );
  });
});
