import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AuditLogWorkspace } from "@/components/audit-log-workspace";
import { TicketWorkspace } from "@/components/ticket-workspace";
import { UserManagement } from "@/components/user-management";
import { permissions } from "@/lib/auth";
import type { UserResponse } from "@/lib/api/schemas";
import {
  assetsFixture,
  logFixture,
  ticketsFixture,
} from "@/test/fixtures";
import {
  administratorTestUser,
  mockApi,
  renderWithQuery,
} from "@/test/test-utils";

const helpdesk: UserResponse = {
  ...administratorTestUser,
  id: "22222222-2222-4222-8222-222222222222",
  username: "helpdesk.test",
  display_name: "Helpdesk test",
  role: "helpdesk",
  role_display_name: "Bộ phận tiếp nhận",
  permissions: [
    permissions.assetsRead,
    permissions.ticketsRead,
    permissions.ticketsCreate,
    permissions.ticketsUpdate,
  ],
};

const technician: UserResponse = {
  ...administratorTestUser,
  id: "33333333-3333-4333-8333-333333333333",
  username: "technician.test",
  display_name: "Kỹ thuật viên test",
  role: "technician",
  role_display_name: "Kỹ thuật viên",
  technician_id: "TECH_003",
  permissions: [
    permissions.assetsRead,
    permissions.ticketsRead,
    permissions.ticketsUpdate,
    permissions.ticketsResolve,
    permissions.maintenanceLogsRead,
    permissions.maintenanceLogsCreate,
    permissions.copilotUse,
  ],
};

describe("permission-aware product UI", () => {
  it("lets helpdesk create an unassigned ticket without assignment controls", async () => {
    mockWorkspace();
    renderWithQuery(<TicketWorkspace />, helpdesk);

    fireEvent.click(await screen.findByRole("button", { name: "Tạo ticket" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Chưa phân công kỹ thuật viên")).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Mã kỹ thuật viên")).not.toBeInTheDocument();
  });

  it("lets a technician update assigned work but not reassign it", async () => {
    mockWorkspace();
    renderWithQuery(<TicketWorkspace />, technician);

    fireEvent.click(
      await screen.findByRole("button", { name: "Xem chi tiết ticket TCK-000041" }),
    );
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByLabelText("Mã kỹ thuật viên")).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Lưu cập nhật" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /Chuyển sang Đang xử lý/ })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Lưu phân công" })).not.toBeInTheDocument();
  });

  it("hides technical result and resolution controls from helpdesk", async () => {
    mockWorkspace([
      { ...ticketsFixture[0], status: "Đang xử lý" },
      ticketsFixture[1],
    ]);
    renderWithQuery(<TicketWorkspace />, helpdesk);

    fireEvent.click(
      await screen.findByRole("button", { name: "Xem chi tiết ticket TCK-000041" }),
    );
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByRole("button", { name: "Ghi kết quả bảo trì" })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Resolve ticket" })).not.toBeInTheDocument();
  });

  it("renders administrator user management without sensitive hashes", async () => {
    mockApi({
      "/users": [administratorTestUser, helpdesk],
      "/users/roles": [
        {
          code: "administrator",
          display_name: "Quản trị viên",
          permissions: Object.values(permissions),
        },
        {
          code: "helpdesk",
          display_name: "Bộ phận tiếp nhận",
          permissions: helpdesk.permissions,
        },
      ],
    });
    renderWithQuery(<UserManagement />);

    expect(await screen.findByText("Quản trị viên test")).toBeInTheDocument();
    expect(screen.getByText("Helpdesk test")).toBeInTheDocument();
    expect(screen.queryByText(/password_hash/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tạo người dùng" })).toBeInTheDocument();
  });

  it("renders safe audit summaries instead of raw JSON", async () => {
    mockApi({
      "/audit-logs?page=1&page_size=25": {
        items: [
          {
            id: "44444444-4444-4444-8444-444444444444",
            occurred_at: "2026-07-18T08:00:00Z",
            actor_user_id: administratorTestUser.id,
            actor_display_name: administratorTestUser.display_name,
            action: "ticket.status_changed",
            resource_type: "ticket",
            resource_id: "TCK-000041",
            request_id: "request-test-1",
            before_state: { status: "Mới tạo" },
            after_state: { status: "Đang xử lý" },
            metadata: { changed_fields: "status" },
            outcome: "success",
          },
        ],
        page: 1,
        page_size: 25,
        total: 1,
        total_pages: 1,
      },
    });
    renderWithQuery(<AuditLogWorkspace />);

    expect(await screen.findByText("ticket.status_changed")).toBeInTheDocument();
    expect(screen.getByText("Trường thay đổi: status")).toBeInTheDocument();
    expect(screen.getByText("Thành công")).toBeInTheDocument();
    expect(screen.getByText("request-test-1")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Hành động" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Tài nguyên" })).toBeInTheDocument();
    expect(screen.queryByText(/password/i)).not.toBeInTheDocument();
  });
});

function mockWorkspace(tickets = ticketsFixture) {
  mockApi({
    "/tickets?limit=1000": tickets,
    "/assets": assetsFixture,
    "/maintenance/logs?limit=1000": [{ ...logFixture, ticket_id: "TCK-000010" }],
  });
}
