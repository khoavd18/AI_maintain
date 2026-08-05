import { describe, expect, it } from "vitest";

import {
  isActivePath,
  navigationForRole,
  quickActionsForPermissions,
} from "@/components/app-shell";
import { defaultRouteFor } from "@/components/auth-provider";
import type { UserResponse } from "@/lib/api/schemas";
import { permissions } from "@/lib/auth";

describe("role-relevant application navigation", () => {
  it("puts assigned work first for technicians and separates setup links", () => {
    const sections = navigationForRole("technician", [
      permissions.assetsRead,
      permissions.ticketsRead,
      permissions.workOrdersRead,
      permissions.copilotUse,
      permissions.checklistTemplatesRead,
    ]);

    expect(sections).toEqual([
      {
        label: "Công việc",
        items: [
          { label: "Lệnh công việc", href: "/work-orders" },
          { label: "Thiết bị", href: "/assets" },
          { label: "Sự cố", href: "/tickets" },
          { label: "Trợ lý bảo trì", href: "/copilot" },
        ],
      },
      {
        label: "Thiết lập & quản trị",
        items: [{ label: "Mẫu kiểm tra", href: "/maintenance/checklists" }],
      },
    ]);
  });

  it("puts inventory first for storekeepers and hides unauthorized setup", () => {
    const sections = navigationForRole("storekeeper", [
      permissions.inventoryRead,
      permissions.workOrdersRead,
      permissions.assetsRead,
      permissions.ticketsRead,
    ]);

    expect(sections).toHaveLength(1);
    expect(sections[0]?.items.map((item) => item.label)).toEqual([
      "Kho phụ tùng",
      "Lệnh công việc",
      "Thiết bị",
      "Sự cố",
    ]);
  });

  it("keeps administration visibly separate and permission-filtered", () => {
    const sections = navigationForRole("administrator", [
      permissions.analyticsRead,
      permissions.assetsRead,
      permissions.usersRead,
      permissions.auditLogsRead,
    ]);

    expect(sections[0]).toMatchObject({
      label: "Công việc",
      items: [
        { label: "Tổng quan", href: "/" },
        { label: "Thiết bị", href: "/assets" },
        { label: "Bất thường", href: "/anomalies" },
      ],
    });
    expect(sections[1]).toEqual({
      label: "Thiết lập & quản trị",
      items: [
        { label: "Người dùng & quyền", href: "/admin/users" },
        { label: "Nhật ký hệ thống", href: "/admin/audit" },
      ],
    });
  });

  it("marks only exact dashboard and matching route branches active", () => {
    expect(isActivePath("/", "/")).toBe(true);
    expect(isActivePath("/assets/GENERATOR_002", "/assets")).toBe(true);
    expect(isActivePath("/tickets", "/")).toBe(false);
    expect(isActivePath("/inventory", "/work-orders")).toBe(false);
    expect(isActivePath("/assets-old", "/assets")).toBe(false);
  });

  it("only exposes stable quick actions allowed by permissions", () => {
    expect(quickActionsForPermissions([
      permissions.ticketsCreate,
      permissions.inventoryReceive,
      permissions.workOrdersCreate,
    ])).toEqual([
      { label: "Báo sự cố", href: "/tickets/new" },
      { label: "Ghi nhận nhập kho", href: "/inventory/receiving" },
    ]);
  });

  it("sends helpdesk users to incidents instead of the inventory overview", () => {
    const user: UserResponse = {
      id: "22222222-2222-4222-8222-222222222222",
      username: "helpdesk.test",
      email: null,
      display_name: "Bộ phận tiếp nhận",
      role: "helpdesk",
      role_display_name: "Bộ phận tiếp nhận",
      permissions: [
        permissions.inventoryRead,
        permissions.workOrdersRead,
        permissions.ticketsRead,
      ],
      technician_id: null,
      is_active: true,
      created_at: "2026-07-18T00:00:00Z",
      updated_at: "2026-07-18T00:00:00Z",
      last_login_at: null,
      version: 1,
    };

    expect(defaultRouteFor(user)).toBe("/tickets");
  });
});
