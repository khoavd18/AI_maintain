import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WorkOrderWorkspace } from "@/components/work-order-workspace";
import { mockApi, renderWithQuery } from "@/test/test-utils";

const longVietnameseTitle =
  "Kiểm tra toàn bộ hệ thống máy phát điện dự phòng, tủ chuyển nguồn tự động và đường dây cấp điện cho khu vực kỹ thuật tầng mái";

describe("work-order desktop table", () => {
  it("contains long Vietnamese titles within fixed columns and wraps flexible fields safely", async () => {
    mockApi({
      "/maintenance/options": maintenanceOptions,
      "/work-orders": {
        items: [{ ...workOrderFixture, title: longVietnameseTitle }],
        page: 1,
        page_size: 200,
        total: 1,
        total_pages: 1,
      },
      "/work-orders/metrics": workOrderMetrics,
    });

    renderWithQuery(<WorkOrderWorkspace />);

    const title = await screen.findByTitle(longVietnameseTitle);
    expect(title).toHaveClass("line-clamp-2", "break-words", "leading-5");
    expect(title).toHaveTextContent(longVietnameseTitle);

    const table = title.closest("table");
    expect(table).not.toBeNull();
    expect(table).toHaveClass("table-fixed");
    expect(Array.from(table!.querySelectorAll("col"), (column) => column.className)).toEqual([
      "w-[25%]",
      "w-[13%]",
      "w-[13%]",
      "w-[12%]",
      "w-[13%]",
      "w-[11%]",
      "w-[13%]",
    ]);

    const row = title.closest("tr");
    expect(row).not.toBeNull();
    const cells = within(row!).getAllByRole("cell");
    expect(cells).toHaveLength(7);
    for (const cell of cells.slice(0, 4)) {
      expect(cell).toHaveClass("min-w-0", "whitespace-normal", "align-top");
      expect(cell).not.toHaveClass("whitespace-nowrap");
    }
    for (const cell of cells.slice(4)) {
      expect(cell).toHaveClass("whitespace-nowrap", "align-top");
    }
  });
});

const maintenanceOptions = {
  plan_statuses: [{ code: "active", display_name: "Đang hoạt động" }],
  interval_units: [{ code: "month", display_name: "Tháng" }],
  work_order_types: [{ code: "preventive", display_name: "Phòng ngừa" }],
  work_order_statuses: [{ code: "assigned", display_name: "Đã phân công" }],
  checklist_response_types: [{ code: "checkbox", display_name: "Checkbox" }],
  priorities: [{ code: "high", display_name: "Cao" }],
  maintenance_results: [{ code: "resolved", display_name: "Đã xử lý" }],
  evidence_categories: [{ code: "before_photo", display_name: "Ảnh trước bảo trì" }],
  technicians: [{
    id: "33333333-3333-4333-8333-333333333333",
    display_name: "Kỹ thuật viên phụ trách khu vực kỹ thuật tầng mái",
    role: "technician",
    technician_id: "TECHNICIAN_IDENTIFIER_WITHOUT_SPACES_002",
    is_active: true,
  }],
};

const workOrderFixture = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  work_order_number: "WO-2026-000001",
  title: longVietnameseTitle,
  description: "Thực hiện danh sách kiểm tra an toàn.",
  work_order_type: "preventive",
  work_order_type_display: "Bảo trì phòng ngừa theo kế hoạch định kỳ",
  asset_id: "GENERATOR_IDENTIFIER_WITHOUT_SPACES_002",
  asset_name: "Máy phát điện dự phòng 002",
  location: "Khu vực kỹ thuật tầng mái phía Đông tòa nhà",
  preventive_plan_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  preventive_plan_code: "PREVENTIVE_PLAN_IDENTIFIER_WITHOUT_SPACES_001",
  source_ticket_id: null,
  assigned_to_user_id: "33333333-3333-4333-8333-333333333333",
  assigned_to_name: "Kỹ thuật viên phụ trách khu vực kỹ thuật tầng mái",
  created_by_user_id: "11111111-1111-4111-8111-111111111111",
  verified_by_user_id: null,
  verified_by_name: null,
  maintenance_log_id: null,
  priority: "high",
  priority_display: "Cao",
  scheduled_start_at: null,
  scheduled_end_at: null,
  due_date: "2026-08-05",
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

const workOrderMetrics = {
  as_of_date: "2026-07-30",
  total_work_orders: 1,
  by_status: { assigned: 1 },
  overdue_count: 0,
  upcoming_preventive_count: 1,
  completed_count: 0,
  verified_count: 0,
  completed_on_time_count: 0,
  technician_workload: [{
    user_id: "33333333-3333-4333-8333-333333333333",
    display_name: "Kỹ thuật viên phụ trách khu vực kỹ thuật tầng mái",
    open_count: 1,
  }],
  data_notice: "Dữ liệu phục vụ kiểm thử giao diện.",
};
