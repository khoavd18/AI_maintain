import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EscalationDashboard } from "@/components/escalation-dashboard";
import { SlaAdministration } from "@/components/sla-administration";
import { TicketInbox } from "@/components/ticket-inbox";
import { TicketIntakeForm } from "@/components/ticket-intake-form";
import { TicketOperationsDetail } from "@/components/ticket-operations-detail";
import { permissions } from "@/lib/auth";
import type { UserResponse } from "@/lib/api/schemas";
import type { TicketDetail } from "@/lib/api/ticketing-schemas";
import { assetDetailsFixture, assetsFixture } from "@/test/fixtures";
import {
  administratorTestUser,
  mockApi,
  renderWithQuery,
} from "@/test/test-utils";

describe("PM5 ticket intake and queues", () => {
  it("validates intake locally and uses the backend priority preview", async () => {
    let postedBody: Record<string, unknown> | null = null;
    const fetchMock = mockApi({
      "/ticketing/options": ticketingOptionsFixture,
      "/assets": assetsFixture,
      "/ticketing/priority-preview": priorityPreviewFixture,
      "POST /tickets/intake": async (
        _input: string | URL | Request,
        init?: RequestInit,
      ) => {
        postedBody = JSON.parse(String(init?.body));
        return { body: ticketDetailFixture, status: 201 };
      },
    });
    renderWithQuery(<TicketIntakeForm initialAssetId="GENERATOR_002" />);

    expect(
      await screen.findByText("Tính từ ảnh hưởng và độ khẩn cấp"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Trung bình").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Lưu phiếu sự cố" }));
    expect(
      await screen.findByText("Mô tả cần ít nhất 5 ký tự."),
    ).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(([, init]) => init?.method === "POST"),
    ).toHaveLength(0);

    fireEvent.change(screen.getByLabelText("Mô tả sự cố"), {
      target: {
        value: "Máy phát có điện áp không ổn định trong lần chạy thử.",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Lưu phiếu sự cố" }));

    expect(await screen.findByText("Đã lưu phiếu sự cố")).toBeInTheDocument();
    expect(screen.getByText(/Mã phiếu: TCK-000100/)).toBeInTheDocument();
    expect(postedBody).not.toHaveProperty("priority");
    expect(postedBody).toMatchObject({
      asset_id: "GENERATOR_002",
      impact: "medium",
      urgency: "medium",
    });
  });

  it("sends queue and search filters to the server", async () => {
    const fetchMock = mockApi({
      "/ticketing/options": ticketingOptionsFixture,
      "/ticketing/sla-summary": slaSummaryFixture,
      "/ticket-queues/unassigned": queueFixture("unassigned", "Chưa phân công"),
      "/ticket-queues/due_soon": queueFixture("due_soon", "Sắp đến hạn SLA"),
    });
    renderWithQuery(<TicketInbox />);

    expect(await screen.findByText("TCK-000100")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Tìm kiếm"), {
      target: { value: "GENERATOR_002" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Lọc danh sách" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([input]) =>
          String(input).includes("search=GENERATOR_002"),
        ),
      ).toBe(true),
    );

    fireEvent.click(
      screen.getByRole("combobox", { name: "Nhóm cần xử lý" }),
    );
    fireEvent.click(
      await screen.findByRole("option", { name: "Sắp đến hạn SLA" }),
    );
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([input]) =>
          String(input).includes("/ticket-queues/due_soon"),
        ),
      ).toBe(true),
    );
  });
});

describe("PM5 ticket detail", () => {
  it("presents backend SLA state and performs a named start action", async () => {
    let current = ticketDetailFixture;
    const fetchMock = mockApi({
      "/ticketing/options": ticketingOptionsFixture,
      "/assets/GENERATOR_002/details": assetDetailsFixture,
      "/tickets/TCK-000100/work-orders": [],
      "/tickets/TCK-000100": () => current,
      "POST /tickets/TCK-000100/start": () => {
        current = {
          ...current,
          status: "in_progress",
          status_display: "Đang xử lý",
          first_response_at: "2026-07-23T01:10:00Z",
          version: 2,
        };
        return current;
      },
    });
    renderWithQuery(<TicketOperationsDetail ticketId="TCK-000100" />, technicianUser);

    expect(await screen.findByText("Sắp đến hạn")).toBeInTheDocument();
    expect(screen.getByText("Còn 30 phút làm việc")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Bắt đầu" }));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            String(input).includes("/tickets/TCK-000100/start") &&
            init?.method === "POST",
        ),
      ).toBe(true),
    );
    expect(await screen.findByText("Đang xử lý")).toBeInTheDocument();
  });

  it("adds append-only comments and hides write controls without permission", async () => {
    let current = ticketDetailFixture;
    mockApi({
      "/ticketing/options": ticketingOptionsFixture,
      "/assets/GENERATOR_002/details": assetDetailsFixture,
      "/tickets/TCK-000100/work-orders": [],
      "/tickets/TCK-000100": () => current,
      "POST /tickets/TCK-000100/comments": async (
        _input: string | URL | Request,
        init?: RequestInit,
      ) => {
        const request = JSON.parse(String(init?.body));
        const comment = {
          id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
          ticket_id: "TCK-000100",
          author_user_id: technicianUser.id,
          author_name: technicianUser.display_name,
          visibility: request.visibility,
          body: request.body,
          created_at: "2026-07-23T01:15:00Z",
          attachments: [],
        };
        current = { ...current, comments: [...current.comments, comment] };
        return { body: comment, status: 201 };
      },
    });
    const view = renderWithQuery(
      <TicketOperationsDetail ticketId="TCK-000100" />,
      technicianUser,
    );
    fireEvent.mouseDown(
      await screen.findByRole("tab", { name: "Trao đổi (1)" }),
      { button: 0, ctrlKey: false },
    );
    fireEvent.change(await screen.findByLabelText("Nội dung comment"), {
      target: { value: "Đã kiểm tra khu vực và chuẩn bị cô lập nguồn." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Gửi cập nhật" }));
    expect(
      await screen.findByText("Đã kiểm tra khu vực và chuẩn bị cô lập nguồn."),
    ).toBeInTheDocument();
    view.unmount();

    mockApi({
      "/ticketing/options": ticketingOptionsFixture,
      "/assets/GENERATOR_002/details": assetDetailsFixture,
      "/tickets/TCK-000100/work-orders": [],
      "/tickets/TCK-000100": ticketDetailFixture,
    });
    renderWithQuery(
      <TicketOperationsDetail ticketId="TCK-000100" />,
      storekeeperUser,
    );
    expect(await screen.findByText("TCK-000100")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Bắt đầu" }),
    ).not.toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Trao đổi (1)" }), {
      button: 0,
      ctrlKey: false,
    });
    expect(screen.queryByLabelText("Nội dung comment")).not.toBeInTheDocument();
  });

  it("surfaces stale action conflicts with a reload control", async () => {
    mockApi({
      "/ticketing/options": ticketingOptionsFixture,
      "/assets/GENERATOR_002/details": assetDetailsFixture,
      "/tickets/TCK-000100/work-orders": [],
      "/tickets/TCK-000100": ticketDetailFixture,
      "POST /tickets/TCK-000100/start": {
        body: { detail: "Ticket đã thay đổi. Hãy tải lại trước khi cập nhật." },
        status: 409,
      },
    });
    renderWithQuery(<TicketOperationsDetail ticketId="TCK-000100" />, technicianUser);
    fireEvent.click(await screen.findByRole("button", { name: "Bắt đầu" }));
    expect(
      await screen.findByText("Ticket đã thay đổi. Hãy tải lại trước khi cập nhật."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Tải trạng thái mới" }),
    ).toBeInTheDocument();
  });
});

describe("PM5 SLA operations", () => {
  it("renders calendar and policy administration without duplicating SLA math", async () => {
    mockApi({
      "/ticketing/business-calendars": [calendarFixture],
      "/ticketing/sla-policies": [policyFixture],
      "/ticketing/options": ticketingOptionsFixture,
    });
    renderWithQuery(<SlaAdministration />);
    expect(await screen.findByText("DEFAULT_FACILITY")).toBeInTheDocument();
    fireEvent.mouseDown(
      screen.getByRole("tab", { name: "Business calendars" }),
      { button: 0, ctrlKey: false },
    );
    expect((await screen.findAllByText("VN_FACILITY")).length).toBeGreaterThan(0);
    expect(await screen.findByText(/5 khung giờ/)).toBeInTheDocument();
  });

  it("supports escalation dry-run and hides execution without permission", async () => {
    const fetchMock = mockApi({
      "/ticketing/sla-summary": slaSummaryFixture,
      "POST /ticketing/escalations/evaluate": {
        dry_run: true,
        as_of: "2026-07-23T01:30:00Z",
        candidate_count: 1,
        created_count: 0,
        candidates: [
          {
            ticket_id: "TCK-000100",
            rule_code: "resolution_due_soon",
            rule_display: "Resolution SLA sắp đến hạn",
            clock_type: "resolution",
            occurrence_number: 1,
            due_at: "2026-07-23T02:00:00Z",
          },
        ],
      },
    });
    renderWithQuery(<EscalationDashboard />, managerDryRunUser);
    expect(
      screen.queryByRole("button", { name: "Ghi escalation events" }),
    ).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Dry run" }));
    expect(
      await screen.findByText("Resolution SLA sắp đến hạn"),
    ).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([, init]) => init?.method === "POST"),
    ).toBe(true);
  });
});

const technicianId = "55555555-5555-4555-8555-555555555555";
const categoryId = "11111111-aaaa-4aaa-8aaa-111111111111";
const subcategoryId = "22222222-bbbb-4bbb-8bbb-222222222222";
const sourceId = "33333333-cccc-4ccc-8ccc-333333333333";
const groupId = "44444444-dddd-4ddd-8ddd-444444444444";
const calendarId = "77777777-7777-4777-8777-777777777777";
const policyId = "88888888-8888-4888-8888-888888888888";

const ticketingOptionsFixture = {
  categories: [
    {
      id: categoryId,
      code: "GENERAL",
      name: "Sự cố thiết bị",
      is_active: true,
      category_id: null,
    },
  ],
  subcategories: [
    {
      id: subcategoryId,
      code: "ELECTRICAL",
      name: "Điện",
      is_active: true,
      category_id: categoryId,
    },
  ],
  intake_sources: [
    {
      id: sourceId,
      code: "WEB",
      name: "Web",
      is_active: true,
      category_id: null,
    },
  ],
  support_groups: [
    {
      id: groupId,
      code: "ENGINEERING",
      name: "Kỹ thuật",
      is_active: true,
      category_id: null,
    },
  ],
  assignees: [
    {
      id: technicianId,
      display_name: "Kỹ thuật viên test",
      role: "technician",
      technician_id: "TECH_002",
      is_active: true,
    },
  ],
  statuses: [
    { code: "open", display_name: "Mở" },
    { code: "assigned", display_name: "Đã phân công" },
    { code: "in_progress", display_name: "Đang xử lý" },
    { code: "waiting", display_name: "Đang chờ" },
    { code: "resolved", display_name: "Đã xử lý" },
    { code: "closed", display_name: "Đã đóng" },
    { code: "cancelled", display_name: "Đã hủy" },
    { code: "reopened", display_name: "Mở lại" },
  ],
  impacts: [
    { code: "low", display_name: "Thấp" },
    { code: "medium", display_name: "Trung bình" },
    { code: "high", display_name: "Cao" },
    { code: "critical", display_name: "Nghiêm trọng" },
  ],
  urgencies: [
    { code: "low", display_name: "Thấp" },
    { code: "medium", display_name: "Trung bình" },
    { code: "high", display_name: "Cao" },
    { code: "immediate", display_name: "Ngay lập tức" },
  ],
  priorities: [
    { code: "low", display_name: "Thấp" },
    { code: "medium", display_name: "Trung bình" },
    { code: "high", display_name: "Cao" },
    { code: "critical", display_name: "Khẩn cấp" },
  ],
  comment_visibilities: [
    { code: "internal", display_name: "Nội bộ" },
    { code: "requester", display_name: "Requester" },
  ],
  sla_statuses: [
    { code: "due_soon", display_name: "Sắp đến hạn" },
  ],
  queues: [
    { code: "unassigned", display_name: "Chưa phân công" },
    { code: "assigned_to_me", display_name: "Của tôi" },
    { code: "assigned_to_queue", display_name: "Theo nhóm" },
    { code: "critical", display_name: "Critical" },
    { code: "due_soon", display_name: "Sắp đến hạn SLA" },
    { code: "sla_breached", display_name: "Vi phạm SLA" },
    { code: "waiting", display_name: "Đang chờ" },
    { code: "recently_resolved", display_name: "Mới resolve" },
    { code: "reopened", display_name: "Mở lại" },
  ],
  failure_categories: [
    { code: "electrical_issue", display_name: "Lỗi điện" },
    { code: "no_failure", display_name: "Chưa xác định" },
  ],
  priority_matrix: [],
};

const priorityPreviewFixture = {
  impact: "medium",
  impact_display: "Trung bình",
  urgency: "medium",
  urgency_display: "Trung bình",
  priority: "medium",
  priority_display: "Trung bình",
};

const ticketDetailFixture: TicketDetail = {
  ticket_id: "TCK-000100",
  asset_id: "GENERATOR_002",
  issue_description: "Máy phát có điện áp không ổn định khi chạy thử.",
  failure_category: "electrical_issue",
  failure_category_display: "Lỗi điện",
  reporter_name: "Nguyễn Văn A",
  reporter_email: "requester@example.com",
  reporter_phone: "0900000000",
  reporter_redacted: false,
  category_id: categoryId,
  category_name: "Sự cố thiết bị",
  subcategory_id: subcategoryId,
  subcategory_name: "Điện",
  impact: "medium",
  impact_display: "Trung bình",
  urgency: "medium",
  urgency_display: "Trung bình",
  priority: "medium",
  priority_display: "Trung bình",
  status: "assigned",
  status_display: "Đã phân công",
  intake_source_id: sourceId,
  intake_source_name: "Web",
  support_group_id: groupId,
  support_group_name: "Kỹ thuật",
  assigned_user_id: technicianId,
  assigned_user_name: "Kỹ thuật viên test",
  technician_id: "TECH_002",
  created_at: "2026-07-23T01:00:00Z",
  first_response_at: null,
  waiting_reason: null,
  waiting_previous_status: null,
  resolved_at: null,
  closed_at: null,
  reopened_at: null,
  cancelled_at: null,
  cancellation_reason: null,
  reopen_count: 0,
  manager_note: "Ưu tiên kiểm tra trong ca.",
  note: null,
  updated_at: "2026-07-23T01:00:00Z",
  version: 1,
  sla: {
    id: "99999999-9999-4999-8999-999999999999",
    policy_id: policyId,
    policy_code: "DEFAULT_FACILITY",
    policy_name: "SLA vận hành mặc định",
    calendar_id: calendarId,
    calendar_code: "VN_FACILITY",
    timezone: "Asia/Ho_Chi_Minh",
    calendar_snapshot: { timezone: "Asia/Ho_Chi_Minh" },
    pause_on_waiting: true,
    due_soon_percent: 20,
    first_response_target_minutes: 120,
    resolution_target_minutes: 720,
    started_at: "2026-07-23T01:00:00Z",
    first_response_due_at: "2026-07-23T03:00:00Z",
    resolution_due_at: "2026-07-24T06:00:00Z",
    first_response_remaining_minutes: null,
    resolution_remaining_minutes: null,
    paused_at: null,
    resolution_stopped_at: null,
    occurrence_number: 1,
    version: 1,
    first_response: {
      status: "due_soon",
      status_display: "Sắp đến hạn",
      due_at: "2026-07-23T03:00:00Z",
      completed_at: null,
      remaining_business_minutes: 30,
    },
    resolution: {
      status: "active",
      status_display: "Đang chạy",
      due_at: "2026-07-24T06:00:00Z",
      completed_at: null,
      remaining_business_minutes: 600,
    },
  },
  comments: [
    {
      id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      ticket_id: "TCK-000100",
      author_user_id: technicianId,
      author_name: "Kỹ thuật viên test",
      visibility: "internal",
      body: "Đã tiếp nhận ticket.",
      created_at: "2026-07-23T01:05:00Z",
      attachments: [],
    },
  ],
  sla_events: [],
  escalations: [],
  linked_work_orders: [],
};

function queueFixture(queue: "unassigned" | "due_soon", label: string) {
  return {
    items: [ticketDetailFixture],
    page: 1,
    page_size: 25,
    total: 1,
    queue,
    queue_display: label,
    as_of: "2026-07-23T01:30:00Z",
  };
}

const slaSummaryFixture = {
  as_of: "2026-07-23T01:30:00Z",
  active_count: 3,
  waiting_count: 1,
  critical_count: 1,
  due_soon_count: 1,
  breached_count: 0,
  without_sla_count: 0,
};

const calendarFixture = {
  id: calendarId,
  code: "VN_FACILITY",
  name: "Lịch vận hành Việt Nam",
  timezone: "Asia/Ho_Chi_Minh",
  is_active: true,
  periods: [0, 1, 2, 3, 4].map((weekday) => ({
    weekday,
    start_time: "08:00:00",
    end_time: "17:00:00",
  })),
  holidays: [],
  version: 1,
};

const policyFixture = {
  id: policyId,
  code: "DEFAULT_FACILITY",
  name: "SLA vận hành mặc định",
  calendar_id: calendarId,
  calendar_code: "VN_FACILITY",
  calendar: calendarFixture,
  category_id: null,
  category_name: null,
  timezone: "Asia/Ho_Chi_Minh",
  pause_on_waiting: true,
  due_soon_percent: 20,
  effective_from: "2026-01-01",
  effective_to: null,
  is_active: true,
  targets: [
    { priority: "low", first_response_minutes: 240, resolution_minutes: 1440 },
    { priority: "medium", first_response_minutes: 120, resolution_minutes: 720 },
    { priority: "high", first_response_minutes: 60, resolution_minutes: 240 },
    { priority: "critical", first_response_minutes: 15, resolution_minutes: 120 },
  ],
  version: 1,
};

const technicianUser: UserResponse = {
  ...administratorTestUser,
  id: technicianId,
  username: "technician.ticket",
  display_name: "Kỹ thuật viên test",
  role: "technician",
  role_display_name: "Kỹ thuật viên",
  technician_id: "TECH_002",
  permissions: [
    permissions.assetsRead,
    permissions.ticketsRead,
    permissions.ticketsAcknowledge,
    permissions.ticketsExecute,
    permissions.ticketCommentsInternal,
    permissions.workOrdersRead,
  ],
};

const storekeeperUser: UserResponse = {
  ...administratorTestUser,
  username: "storekeeper.ticket",
  display_name: "Thủ kho test",
  role: "storekeeper",
  role_display_name: "Thủ kho",
  permissions: [
    permissions.assetsRead,
    permissions.ticketsRead,
    permissions.workOrdersRead,
  ],
};

const managerDryRunUser: UserResponse = {
  ...administratorTestUser,
  username: "manager.ticket",
  display_name: "Quản lý test",
  role: "property_manager",
  role_display_name: "Quản lý cơ sở",
  permissions: [
    permissions.ticketsRead,
    permissions.slaPoliciesRead,
    permissions.escalationsEvaluate,
  ],
};
