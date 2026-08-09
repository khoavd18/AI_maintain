import { fireEvent, screen, waitFor } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { NotificationWorkspace } from "@/components/notification-workspace"
import { UserManagement } from "@/components/user-management"
import { WorkOrderWorkspace } from "@/components/work-order-workspace"
import { mockApi, renderWithQuery } from "@/test/test-utils"

describe("dropdown consumer handlers", () => {
  it("updates the Admin Users role field with the selected role code", async () => {
    mockApi({
      "/users": [],
      "/users/roles": roleOptions,
    })

    renderWithQuery(<UserManagement />)

    const trigger = await screen.findByRole("combobox")
    expect(trigger).toHaveTextContent("Điều phối")

    fireEvent.click(trigger)
    fireEvent.click(screen.getByRole("option", { name: "Kỹ thuật viên" }))

    expect(trigger).toHaveTextContent("Kỹ thuật viên")
    expect(screen.getAllByText("Mã kỹ thuật viên")).toHaveLength(2)
  })

  it("passes the selected work-order status to the existing filter query", async () => {
    const fetchMock = mockApi({
      "/maintenance/options": maintenanceOptions,
      "/work-orders": emptyWorkOrderPage,
      "/work-orders/metrics": workOrderMetrics,
    })

    renderWithQuery(<WorkOrderWorkspace />)

    const trigger = await screen.findByLabelText("Trạng thái")
    fireEvent.click(trigger)
    const options = screen.getAllByRole("option")
    expect(options.map((option) => option.textContent)).toEqual([
      "Tất cả trạng thái",
      "Đã lên kế hoạch",
      "Đã phân công",
    ])
    fireEvent.click(options[2])

    await waitFor(() => {
      const requestedUrls = fetchMock.mock.calls.map(([input]) =>
        input instanceof Request ? input.url : String(input),
      )
      expect(
        requestedUrls.some((url) =>
          new URL(url).searchParams.get("status") === "assigned",
        ),
      ).toBe(true)
    })
  })

  it("preserves the migrated notification severity filter handler", async () => {
    const fetchMock = mockApi({
      "/notifications": { items: [], page: 1, page_size: 50, total: 0 },
    })

    renderWithQuery(<NotificationWorkspace />)

    const trigger = await screen.findByLabelText("Mức độ")
    fireEvent.click(trigger)
    fireEvent.click(screen.getByRole("option", { name: "Cảnh báo" }))

    await waitFor(() => {
      const requestedUrls = fetchMock.mock.calls.map(([input]) =>
        input instanceof Request ? input.url : String(input),
      )
      expect(
        requestedUrls.some((url) =>
          new URL(url).searchParams.get("severity") === "warning",
        ),
      ).toBe(true)
    })
  })
})

const roleOptions = [
  { code: "helpdesk", display_name: "Điều phối", permissions: [] },
  { code: "technician", display_name: "Kỹ thuật viên", permissions: [] },
  { code: "property_manager", display_name: "Quản lý cơ sở", permissions: [] },
]

const maintenanceOptions = {
  plan_statuses: [],
  interval_units: [],
  work_order_types: [
    { code: "preventive", display_name: "Bảo trì định kỳ" },
    { code: "corrective", display_name: "Khắc phục sự cố" },
  ],
  work_order_statuses: [
    { code: "planned", display_name: "Đã lên kế hoạch" },
    { code: "assigned", display_name: "Đã phân công" },
  ],
  checklist_response_types: [],
  priorities: [],
  maintenance_results: [],
  evidence_categories: [],
  technicians: [],
}

const emptyWorkOrderPage = {
  items: [],
  page: 1,
  page_size: 200,
  total: 0,
  total_pages: 0,
}

const workOrderMetrics = {
  as_of_date: "2026-07-30",
  total_work_orders: 0,
  by_status: {},
  overdue_count: 0,
  upcoming_preventive_count: 0,
  completed_count: 0,
  verified_count: 0,
  completed_on_time_count: 0,
  technician_workload: [],
  data_notice: "Dữ liệu kiểm thử.",
}
