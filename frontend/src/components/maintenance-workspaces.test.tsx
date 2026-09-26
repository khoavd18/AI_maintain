import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MaintenancePlanCreateForm, MaintenancePlanWorkspace } from "@/components/maintenance-plan-workspace";
import { WorkOrderDetail } from "@/components/work-order-detail";
import { permissions } from "@/lib/auth";
import type { UserResponse } from "@/lib/api/schemas";
import { assetCatalogFixture } from "@/test/fixtures";
import { workOrderPartsFixture } from "@/test/inventory-fixtures";
import { mockApi, renderWithQuery } from "@/test/test-utils";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

const workOrderId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const technicianId = "33333333-3333-4333-8333-333333333333";

describe("maintenance planning workspace", () => {
  it("shows recurrence, status, and authorized generation actions", async () => {
    mockApi({
      "/maintenance-plans": {
        items: [planFixture],
        page: 1,
        page_size: 100,
        total: 1,
        total_pages: 1,
      },
    });
    renderWithQuery(<MaintenancePlanWorkspace />);
    expect((await screen.findAllByText("PM-GENERATOR-001")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Mỗi 1 tháng").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Xem trước" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Tạo kế hoạch/ })).toHaveAttribute("href", "/maintenance/plans/new");
  });

  it("keeps the main schedule visible and collapses advanced defaults", async () => {
    mockApi({
      "/assets/catalog": assetCatalogFixture,
      "/checklist-templates": {
        items: [],
        page: 1,
        page_size: 200,
        total: 0,
        total_pages: 0,
      },
      "/maintenance/options": maintenanceOptions,
    });
    renderWithQuery(<MaintenancePlanCreateForm />);

    expect(await screen.findByLabelText("Mã kế hoạch")).toBeVisible();
    expect(screen.getByLabelText("Chu kỳ")).toBeVisible();
    expect(screen.getByLabelText("Ngày bắt đầu")).toBeVisible();

    const summary = screen.getByText("Thiết lập nâng cao").closest("summary");
    expect(summary).not.toBeNull();
    expect(screen.getByLabelText("Tạo trước hạn (ngày)")).not.toBeVisible();
    fireEvent.click(summary!);
    expect(screen.getByLabelText("Tạo trước hạn (ngày)")).toBeVisible();
    expect(screen.getByLabelText("Tạo trước hạn (ngày)")).toHaveValue(7);
    expect(screen.getByLabelText("Múi giờ")).toHaveValue("Asia/Ho_Chi_Minh");
    expect(screen.getByLabelText("Kỹ thuật viên mặc định")).toBeVisible();
  });
});

describe("work-order technician workflow", () => {
  it("shows execution controls but hides verification for a technician", async () => {
    mockWorkOrderApi(workOrderFixture);
    renderWithQuery(<WorkOrderDetail workOrderId={workOrderId} />, technicianUser);
    expect(await screen.findByText("WO-2026-000001")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Bắt đầu/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Xác minh kỹ thuật/ })).not.toBeInTheDocument();
  });

  it("surfaces a stale-version conflict and offers state refresh", async () => {
    const fetchMock = mockWorkOrderApi(workOrderFixture, {
      body: { detail: "Work order đã được người khác cập nhật. Hãy tải trạng thái mới." },
      status: 409,
    });
    renderWithQuery(<WorkOrderDetail workOrderId={workOrderId} />, technicianUser);
    fireEvent.click(await screen.findByRole("button", { name: /Bắt đầu/ }));
    expect(await screen.findByText(/đã được người khác cập nhật/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Tải trạng thái mới/ })).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining(`/work-orders/${workOrderId}/transition`),
      expect.objectContaining({ method: "POST" }),
    ));
  });

  it("marks the parts step complete when all required stock is settled", async () => {
    const inProgressWorkOrder = {
      ...workOrderFixture,
      status: "in_progress" as const,
      status_display: "Đang thực hiện",
      started_at: "2026-07-20T02:00:00Z",
    };
    mockWorkOrderApi(inProgressWorkOrder, undefined, {
      ...workOrderPartsFixture,
      total_planned_quantity: 1,
      total_issued_quantity: 1,
      net_consumed_quantity: 1,
      open_shortage_count: 0,
      has_unresolved_issued_stock: false,
      completion_warning: null,
    });
    renderWithQuery(
      <WorkOrderDetail workOrderId={workOrderId} />,
      {
        ...technicianUser,
        permissions: [
          ...technicianUser.permissions,
          permissions.workOrderPartsRead,
        ],
      },
    );

    const partsStep = (await screen.findByText("Phụ tùng")).closest("li");
    await waitFor(() => expect(partsStep).toHaveClass("border-primary"));
    expect(partsStep).toHaveTextContent("✓");
  });

  it("derives follow-up from a non-resolved completion result", async () => {
    const inProgressWorkOrder = {
      ...workOrderFixture,
      status: "in_progress" as const,
      status_display: "Đang thực hiện",
      started_at: "2026-07-20T02:00:00Z",
    };
    const fetchMock = mockWorkOrderApi(inProgressWorkOrder);
    renderWithQuery(<WorkOrderDetail workOrderId={workOrderId} />, technicianUser);

    fireEvent.change(await screen.findByLabelText("Kết quả kiểm tra"), { target: { value: "Dây curoa hoạt động ổn định." } });
    fireEvent.change(screen.getByLabelText("Hành động đã thực hiện"), { target: { value: "Thay dây curoa và chạy thử HVAC." } });
    fireEvent.change(screen.getByLabelText("Ghi chú kỹ thuật viên"), { target: { value: "Thiết bị đã vận hành bình thường." } });
    fireEvent.change(screen.getByLabelText("Tóm tắt hoàn thành"), { target: { value: "Đã thay dây curoa HVAC A42." } });
    fireEvent.click(document.getElementById("completion-result")!);
    fireEvent.click(await screen.findByRole("option", { name: "Xử lý một phần" }));
    expect(screen.getByText("Có", { selector: "span" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Gửi hoàn thành" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining(`/work-orders/${workOrderId}/complete`),
      expect.objectContaining({ method: "POST" }),
    ));
    const completionCall = fetchMock.mock.calls.find(([url]) =>
      String(url).includes(`/work-orders/${workOrderId}/complete`),
    );
    expect(JSON.parse(String(completionCall?.[1]?.body))).toMatchObject({
      maintenance_result: "partially_resolved",
      follow_up_required: true,
    });
  });
});

function mockWorkOrderApi(workOrder: unknown, transitionResponse: unknown = { ...workOrderFixture, status: "in_progress", status_display: "Đang thực hiện", started_at: "2026-07-20T02:00:00Z", version: 2 }, partsSummary: unknown = workOrderPartsFixture, completionResponse: unknown = { ...workOrderFixture, status: "completed", status_display: "Đã hoàn thành", started_at: "2026-07-20T02:00:00Z", completed_at: "2026-07-20T03:00:00Z", completion_summary: "Đã hoàn thành.", labor_minutes: 60, version: 2 }) {
  return mockApi({
    [`/work-orders/${workOrderId}`]: workOrder,
    "/maintenance/options": maintenanceOptions,
    [`/work-orders/${workOrderId}/attachments`]: [],
    [`/work-orders/${workOrderId}/parts`]: partsSummary,
    [`POST /work-orders/${workOrderId}/transition`]: transitionResponse,
    [`POST /work-orders/${workOrderId}/complete`]: completionResponse,
  });
}

const technicianUser: UserResponse = {
  id: technicianId,
  username: "technician.test",
  email: null,
  display_name: "Kỹ thuật viên test",
  role: "technician",
  role_display_name: "Kỹ thuật viên",
  permissions: [
    permissions.workOrdersRead,
    permissions.workOrdersExecute,
    permissions.workOrdersComplete,
    permissions.workOrderAttachmentsRead,
    permissions.workOrderAttachmentsCreate,
  ],
  technician_id: "TECH_002",
  is_active: true,
  created_at: "2026-07-20T00:00:00Z",
  updated_at: "2026-07-20T00:00:00Z",
  last_login_at: null,
  version: 1,
};

const maintenanceOptions = {
  plan_statuses: [{ code: "active", display_name: "Đang hoạt động" }],
  interval_units: [{ code: "month", display_name: "Tháng" }],
  work_order_types: [{ code: "preventive", display_name: "Phòng ngừa" }],
  work_order_statuses: [{ code: "assigned", display_name: "Đã phân công" }],
  checklist_response_types: [{ code: "checkbox", display_name: "Checkbox" }],
  priorities: [{ code: "high", display_name: "Cao" }],
  maintenance_results: [{ code: "resolved", display_name: "Đã xử lý" }],
  evidence_categories: [{ code: "before_photo", display_name: "Ảnh trước bảo trì" }],
  technicians: [{ id: technicianId, display_name: "Kỹ thuật viên test", role: "technician", technician_id: "TECH_002", is_active: true }],
};

const planFixture = {
  id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  plan_code: "PM-GENERATOR-001",
  name: "Bảo trì máy phát hàng tháng",
  description: "Kế hoạch preventive có kiểm soát.",
  asset_id: "GENERATOR_002",
  asset_name: "Máy phát điện dự phòng 002",
  schedule_type: "interval",
  interval_value: 1,
  interval_unit: "month",
  recurrence_summary: "Mỗi 1 tháng",
  recurrence_rule: null,
  start_date: "2026-07-20",
  end_date: "2027-07-20",
  local_timezone: "Asia/Ho_Chi_Minh",
  lead_time_days: 7,
  grace_period_days: 1,
  next_due_date: "2026-07-20",
  last_generated_due_date: null,
  estimated_duration_minutes: 90,
  default_priority: "high",
  default_priority_display: "Cao",
  default_assignee_user_id: technicianId,
  default_assignee_name: "Kỹ thuật viên test",
  checklist_template_id: null,
  checklist_template_name: null,
  instructions: null,
  status: "active",
  status_display: "Đang hoạt động",
  is_active: true,
  paused_at: null,
  archived_at: null,
  archive_reason: null,
  created_by_user_id: "11111111-1111-4111-8111-111111111111",
  updated_by_user_id: "11111111-1111-4111-8111-111111111111",
  created_at: "2026-07-20T00:00:00Z",
  updated_at: "2026-07-20T00:00:00Z",
  version: 1,
};

const workOrderFixture = {
  id: workOrderId,
  work_order_number: "WO-2026-000001",
  title: "Kiểm tra máy phát điện",
  description: "Thực hiện checklist an toàn.",
  work_order_type: "preventive",
  work_order_type_display: "Phòng ngừa",
  asset_id: "GENERATOR_002",
  asset_name: "Máy phát điện dự phòng 002",
  location: "Sân thượng phía Đông",
  preventive_plan_id: planFixture.id,
  preventive_plan_code: planFixture.plan_code,
  source_ticket_id: null,
  assigned_to_user_id: technicianId,
  assigned_to_name: "Kỹ thuật viên test",
  created_by_user_id: "11111111-1111-4111-8111-111111111111",
  verified_by_user_id: null,
  verified_by_name: null,
  maintenance_log_id: null,
  priority: "high",
  priority_display: "Cao",
  scheduled_start_at: null,
  scheduled_end_at: null,
  due_date: "2026-07-20",
  local_timezone: "Asia/Ho_Chi_Minh",
  grace_period_days: 1,
  is_overdue: false,
  estimated_duration_minutes: 90,
  started_at: null,
  completed_at: null,
  verified_at: null,
  cancelled_at: null,
  cancellation_reason: null,
  completion_summary: null,
  safety_notes: null,
  labor_minutes: null,
  status: "assigned",
  status_display: "Đã phân công",
  hold_reason: null,
  created_at: "2026-07-20T00:00:00Z",
  updated_at: "2026-07-20T00:00:00Z",
  version: 1,
  checklist: [],
  history: [],
};
