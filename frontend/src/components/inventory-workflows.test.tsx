import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { InventoryActionForm } from "@/components/inventory-action-form";
import { InventoryWorkspace } from "@/components/inventory-workspace";
import { WorkOrderPartsPanel } from "@/components/work-order-parts-panel";
import { permissions } from "@/lib/auth";
import type { UserResponse } from "@/lib/api/schemas";
import {
  balanceFixture,
  inventoryIds,
  inventoryMetricsFixture,
  movementFixture,
  page,
  partFixture,
  reservationFixture,
  stockLocationFixture,
  workOrderPartsFixture,
} from "@/test/inventory-fixtures";
import {
  administratorTestUser,
  mockApi,
  renderWithQuery,
} from "@/test/test-utils";

describe("inventory overview", () => {
  it("renders server-derived KPI and low-stock values", async () => {
    mockApi({
      "/inventory/metrics": inventoryMetricsFixture,
      "/inventory/low-stock": page([balanceFixture]),
      "/inventory/movements": page([movementFixture]),
    });

    renderWithQuery(<InventoryWorkspace view="overview" />);

    expect(await screen.findByText("Mã phụ tùng đang dùng")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getAllByText("Lọc dầu máy phát").length).toBeGreaterThan(0);
    expect(screen.getByText(/Số lượng khả dụng bằng tồn thực tế/)).toBeInTheDocument();
  });

  it("renders the controlled receipt form without calculating a balance", async () => {
    mockApi({
      "/parts": page([partFixture]),
      "/stock-locations": [stockLocationFixture],
    });

    renderWithQuery(<InventoryActionForm view="receiving" />);

    expect(await screen.findByRole("heading", { level: 2, name: "Nhập kho" })).toBeInTheDocument();
    expect(screen.getByLabelText("Mã chứng từ")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Xác nhận nhập kho" })).toBeDisabled();
    expect(screen.queryByText(/on-hand mới/i)).not.toBeInTheDocument();
  });

  it("routes an opening balance selection to the named opening endpoint", async () => {
    const openingMovement = {
      ...movementFixture,
      movement_type: "opening_balance",
      movement_type_display: "Số dư đầu kỳ",
      business_reference: "OPENING-UI-001",
      idempotency_key: "opening-ui",
    };
    const fetchMock = mockApi({
      "/parts": page([partFixture]),
      "/stock-locations": [stockLocationFixture],
      "POST /inventory/opening-balances": {
        body: openingMovement,
        status: 201,
      },
    });
    renderWithQuery(<InventoryActionForm view="receiving" />);

    await screen.findByRole("heading", { level: 2, name: "Nhập kho" });
    fireEvent.click(screen.getByLabelText("Loại nghiệp vụ"));
    fireEvent.click(
      await screen.findByRole("option", { name: "Số dư đầu kỳ" }),
    );
    fireEvent.click(screen.getByLabelText("Phụ tùng"));
    fireEvent.click(
      await screen.findByRole("option", {
        name: `${partFixture.part_number} · ${partFixture.name_vi}`,
      }),
    );
    fireEvent.click(screen.getByLabelText("Vị trí kho"));
    fireEvent.click(
      await screen.findByRole("option", {
        name: `${stockLocationFixture.code} · ${stockLocationFixture.name}`,
      }),
    );
    fireEvent.change(screen.getByLabelText(/Số lượng/), {
      target: { value: "3" },
    });
    fireEvent.change(screen.getByLabelText("Mã chứng từ"), {
      target: { value: "OPENING-UI-001" },
    });
    fireEvent.change(screen.getByLabelText("Lý do"), {
      target: { value: "Khởi tạo tồn kho demo" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ghi số lượng đầu kỳ" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/inventory/opening-balances"),
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({
            "Idempotency-Key": expect.stringContaining(
              "inventory-opening-balance-",
            ),
          }),
        }),
      ),
    );
  });

  it("confirms a reservation release with a controlled reason form", async () => {
    const released = {
      ...reservationFixture,
      status: "released",
      status_display: "Đã giải phóng",
      remaining_quantity: 0,
      version: 2,
    };
    const fetchMock = mockApi({
      "/inventory/options": inventoryOptionsFixture,
      "/inventory/reservations": page([reservationFixture]),
      [`POST /stock-reservations/${inventoryIds.reservation}/release`]: released,
    });

    renderWithQuery(<InventoryWorkspace view="reservations" />);

    expect((await screen.findAllByText(reservationFixture.reservation_number)).length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole("button", { name: "Giải phóng" })[0]);
    const confirm = screen.getByRole("button", { name: "Xác nhận" });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Lý do"), {
      target: { value: "Không còn cần phụ tùng cho công việc" },
    });
    fireEvent.click(confirm);

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(
          `/stock-reservations/${inventoryIds.reservation}/release`,
        ),
        expect.objectContaining({ method: "POST" }),
      ),
    );
    expect(screen.getByText("Đã giải phóng số lượng đặt trước.")).toBeInTheDocument();
  });
});

describe("work-order inventory workflow", () => {
  it("releases a reservation with an idempotency key", async () => {
    const released = {
      ...reservationFixture,
      status: "released",
      status_display: "Đã giải phóng",
      remaining_quantity: 0,
      version: 2,
      events: [
        ...reservationFixture.events,
        {
          ...reservationFixture.events[0],
          id: "20000000-0000-4000-8000-000000000001",
          event_type: "released",
          reason: "Giải phóng reservation từ work order workspace",
        },
      ],
    };
    const fetchMock = mockWorkOrderPartsApi({
      [`POST /stock-reservations/${inventoryIds.reservation}/release`]: released,
    });

    renderWithQuery(<WorkOrderPartsPanel workOrderId={inventoryIds.workOrder} />);
    expect(await screen.findByText("Vật tư cho công việc")).toBeInTheDocument();
    fireEvent.mouseDown(
      screen.getByRole("tab", { name: /Đặt trước/ }),
      { button: 0, ctrlKey: false },
    );
    fireEvent.click(await screen.findByRole("button", { name: "Giải phóng" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(
          `/stock-reservations/${inventoryIds.reservation}/release`,
        ),
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({
            "Idempotency-Key": expect.stringContaining(
              "inventory-release-",
            ),
          }),
        }),
      ),
    );
  });

  it("replaces a reservation through the explicit named action", async () => {
    const replacement = {
      ...reservationFixture,
      id: "20000000-0000-4000-8000-000000000020",
      reservation_number: "RSV-2026-000002",
      occurrence_number: 2,
      events: [
        {
          ...reservationFixture.events[0],
          id: "20000000-0000-4000-8000-000000000021",
          reason: "Thay thế nguồn giữ vật tư cho work order",
        },
      ],
    };
    const fetchMock = mockWorkOrderPartsApi({
      [`POST /stock-reservations/${inventoryIds.reservation}/replace`]:
        replacement,
    });

    renderWithQuery(<WorkOrderPartsPanel workOrderId={inventoryIds.workOrder} />);
    await screen.findByText("Vật tư cho công việc");
    fireEvent.mouseDown(
      screen.getByRole("tab", { name: /Đặt trước/ }),
      { button: 0, ctrlKey: false },
    );
    fireEvent.click(await screen.findByRole("button", { name: "Thay thế" }));
    fireEvent.click(screen.getByRole("button", { name: "Xác nhận" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(
          `/stock-reservations/${inventoryIds.reservation}/replace`,
        ),
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({
            "Idempotency-Key": expect.stringContaining(
              "inventory-replace-reservation-",
            ),
          }),
        }),
      ),
    );
  });

  it("lets only the assigned technician explicitly consume an issue", async () => {
    const consumed = {
      id: "20000000-0000-4000-8000-000000000002",
      issue_id: inventoryIds.issue,
      work_order_id: inventoryIds.workOrder,
      part_id: inventoryIds.part,
      quantity: 1,
      consumed_by_user_id: inventoryIds.user,
      consumed_by_display_name: "Kỹ thuật viên demo",
      consumed_at: "2026-07-23T03:00:00Z",
      note: "Kỹ thuật viên xác nhận sử dụng tại work order",
    };
    const fetchMock = mockWorkOrderPartsApi(
      {
        [`POST /part-issues/${inventoryIds.issue}/consumptions`]: consumed,
      },
      technicianUser,
    );

    renderWithQuery(
      <WorkOrderPartsPanel workOrderId={inventoryIds.workOrder} />,
      technicianUser,
    );
    expect(await screen.findByText("Vật tư cho công việc")).toBeInTheDocument();
    fireEvent.mouseDown(
      screen.getByRole("tab", { name: /Đã xuất/ }),
      { button: 0, ctrlKey: false },
    );
    fireEvent.change(
      await screen.findByLabelText("Xác nhận đã sử dụng (cái)"),
      { target: { value: "1" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ghi dùng" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(
          `/part-issues/${inventoryIds.issue}/consumptions`,
        ),
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({
            "Idempotency-Key": expect.stringContaining(
              "inventory-consume-",
            ),
          }),
        }),
      ),
    );
    expect(
      screen.queryByRole("button", { name: "Hoàn kho" }),
    ).not.toBeInTheDocument();
  });

  it("hides inventory mutations from a read-only manager", async () => {
    mockWorkOrderPartsApi({}, managerUser);
    renderWithQuery(
      <WorkOrderPartsPanel workOrderId={inventoryIds.workOrder} />,
      managerUser,
    );
    expect(await screen.findByText("Vật tư cho công việc")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Thao tác" })).not.toBeInTheDocument();
    fireEvent.mouseDown(
      screen.getByRole("tab", { name: /Đặt trước/ }),
      { button: 0, ctrlKey: false },
    );
    expect(
      screen.queryByRole("button", { name: "Giải phóng" }),
    ).not.toBeInTheDocument();
  });
});

function mockWorkOrderPartsApi(
  writes: Record<string, unknown> = {},
  user: UserResponse = administratorTestUser,
) {
  const routes: Record<string, unknown> = {
    [`/work-orders/${inventoryIds.workOrder}/parts`]: workOrderPartsFixture,
    "/parts": page([partFixture]),
    "/stock-locations": [stockLocationFixture],
    ...writes,
  };
  if (!user.permissions.includes(permissions.inventoryRead)) {
    delete routes["/parts"];
    delete routes["/stock-locations"];
  }
  return mockApi(routes);
}

const technicianUser: UserResponse = {
  ...administratorTestUser,
  id: inventoryIds.user,
  username: "technician.inventory",
  display_name: "Kỹ thuật viên demo",
  role: "technician",
  role_display_name: "Kỹ thuật viên",
  permissions: [
    permissions.workOrderPartsRead,
    permissions.inventoryConsume,
  ],
  technician_id: "TECH_001",
};

const managerUser: UserResponse = {
  ...administratorTestUser,
  username: "manager.inventory",
  display_name: "Quản lý demo",
  role: "property_manager",
  role_display_name: "Quản lý tòa nhà",
  permissions: [
    permissions.workOrderPartsRead,
    permissions.inventoryRead,
  ],
  technician_id: null,
};

const inventoryOptionsFixture = {
  part_lifecycle_statuses: [],
  stock_location_statuses: [],
  stock_location_types: [],
  movement_types: [],
  requirement_statuses: [],
  reservation_statuses: [
    { code: "active", display_name: "Đang đặt trước" },
    { code: "released", display_name: "Đã giải phóng" },
  ],
  stock_states: [],
  attachment_categories: [],
  compatible_asset_types: [],
};
