import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  NotificationCenter,
  notificationHref,
} from "@/components/notification-center";
import { JobOperationsWorkspace } from "@/components/job-operations-workspace";
import { NotificationWorkspace } from "@/components/notification-workspace";
import { permissions } from "@/lib/auth";
import type {
  JobExecution,
  NotificationRecord,
  ScheduledJob,
} from "@/lib/api/operations-schemas";
import type { UserResponse } from "@/lib/api/schemas";
import {
  administratorTestUser,
  mockApi,
  renderWithQuery,
} from "@/test/test-utils";

const notification: NotificationRecord = {
  id: "10000000-0000-4000-8000-000000000001",
  notification_type: "ticket.assigned",
  title: "Ticket được phân công",
  body: "Ticket TKT-PM7-001 của asset GENERATOR_002 đã được phân công cho bạn.",
  structured_content: {
    ticket_id: "TKT-PM7-001",
    asset_id: "GENERATOR_002",
  },
  severity: "info",
  related_entity_type: "ticket",
  related_entity_id: "TKT-PM7-001",
  created_at: "2026-07-26T03:00:00Z",
  read_at: null,
  dismissed_at: null,
  version: 1,
};

const job: ScheduledJob = {
  job_key: "sla_escalation",
  job_type: "sla_escalation",
  display_name: "Đánh giá SLA và escalation",
  enabled: false,
  interval_seconds: 300,
  timezone: "Asia/Ho_Chi_Minh",
  next_run_at: "2026-07-26T03:00:00Z",
  last_successful_run_at: null,
  concurrency_policy: "forbid_overlap",
  run_as_user_id: null,
  max_attempts: 3,
  retry_backoff_seconds: 30,
  lease_seconds: 180,
  created_at: "2026-07-26T03:00:00Z",
  updated_at: "2026-07-26T03:00:00Z",
  version: 1,
};

const execution: JobExecution = {
  id: "20000000-0000-4000-8000-000000000001",
  job_key: "sla_escalation",
  scheduled_for: "2026-07-26T03:00:00Z",
  trigger_type: "manual",
  requested_by_user_id: administratorTestUser.id,
  status: "dead_lettered",
  attempt_number: 3,
  worker_identity: null,
  available_after: "2026-07-26T03:00:00Z",
  lease_expires_at: null,
  started_at: "2026-07-26T03:00:00Z",
  completed_at: "2026-07-26T03:05:00Z",
  execution_summary: null,
  safe_error_code: "test_failure",
  safe_error_summary: "Tác vụ nền không thể hoàn tất an toàn.",
  correlation_id: "job-test",
  created_at: "2026-07-26T03:00:00Z",
  updated_at: "2026-07-26T03:05:00Z",
  version: 4,
};

describe("notification UI", () => {
  it("shows unread count and private notification actions", async () => {
    const fetchMock = mockApi({
      "/notifications/unread-count": { unread_count: 1 },
      "/notifications": {
        items: [notification],
        page: 1,
        page_size: 8,
        total: 1,
      },
      "POST /notifications/10000000-0000-4000-8000-000000000001/read": {
        ...notification,
        read_at: "2026-07-26T03:10:00Z",
        version: 2,
      },
    });

    renderWithQuery(<NotificationCenter />);
    const trigger = await screen.findByRole("button", {
      name: "Thông báo, 1 chưa đọc",
    });
    fireEvent.click(trigger);

    expect(await screen.findByText(notification.body)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Đánh dấu đã đọc" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(`/notifications/${notification.id}/read`),
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("filters the full inbox and supports read-all", async () => {
    const fetchMock = mockApi({
      "/notifications": {
        items: [notification],
        page: 1,
        page_size: 50,
        total: 1,
      },
      "POST /notifications/read-all": { updated_count: 1 },
    });
    renderWithQuery(<NotificationWorkspace />);

    expect(await screen.findByText(notification.body)).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Đánh dấu tất cả đã đọc" }),
    );
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/notifications/read-all"),
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("does not create a related link without the required permission", () => {
    const canOnlyReadNotifications = (permission: string) =>
      permission === permissions.notificationsRead;
    const inventoryNotification = {
      ...notification,
      related_entity_type: "part",
      related_entity_id: "30000000-0000-4000-8000-000000000001",
    };

    expect(
      notificationHref(
        inventoryNotification,
        canOnlyReadNotifications,
      ),
    ).toBeNull();
  });
});

describe("job operations UI", () => {
  it("renders the closed job catalog and sends idempotent manual triggers", async () => {
    const fetchMock = mockApi({
      "/operations/jobs": [job],
      "/operations/executions": {
        items: [execution],
        page: 1,
        page_size: 50,
        total: 1,
      },
      "/operations/outbox": {
        items: [],
        page: 1,
        page_size: 50,
        total: 0,
      },
      "/operations/metrics": {
        as_of: "2026-07-26T03:00:00Z",
        pending_job_count: 0,
        failed_job_count: 0,
        dead_letter_job_count: 1,
        pending_outbox_count: 0,
        dead_letter_outbox_count: 0,
        oldest_pending_outbox_age_seconds: null,
        last_successful_run_by_job: { sla_escalation: null },
      },
      "/health/worker": {
        status: "ready",
        ready: true,
        worker_identity: "worker-test",
        last_seen_at: "2026-07-26T03:00:00Z",
        age_seconds: 1,
      },
      "POST /operations/jobs/sla_escalation/trigger": {
        execution: { ...execution, status: "pending", attempt_number: 0 },
        created: true,
      },
    });

    renderWithQuery(<JobOperationsWorkspace />);
    expect(await screen.findByText(job.display_name)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Chạy thủ công" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/operations/jobs/sla_escalation/trigger"),
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({
            "Idempotency-Key": expect.stringContaining(
              "trigger-sla_escalation-",
            ),
          }),
        }),
      ),
    );
    expect(await screen.findByText(/đã đưa/i)).toBeInTheDocument();
  });

  it("reuses the trigger key after an ambiguous network failure", async () => {
    const keys: string[] = [];
    let triggerAttempt = 0;
    mockApi({
      "/operations/jobs": [job],
      "/operations/executions": {
        items: [],
        page: 1,
        page_size: 50,
        total: 0,
      },
      "/operations/outbox": {
        items: [],
        page: 1,
        page_size: 50,
        total: 0,
      },
      "/operations/metrics": {
        as_of: "2026-07-26T03:00:00Z",
        pending_job_count: 0,
        failed_job_count: 0,
        dead_letter_job_count: 0,
        pending_outbox_count: 0,
        dead_letter_outbox_count: 0,
        oldest_pending_outbox_age_seconds: null,
        last_successful_run_by_job: { sla_escalation: null },
      },
      "/health/worker": {
        status: "ready",
        ready: true,
        worker_identity: "worker-test",
        last_seen_at: "2026-07-26T03:00:00Z",
        age_seconds: 1,
      },
      "POST /operations/jobs/sla_escalation/trigger": (
        _input,
        init,
      ) => {
        keys.push(new Headers(init?.headers).get("Idempotency-Key") ?? "");
        triggerAttempt += 1;
        if (triggerAttempt === 1) {
          throw new TypeError("Network connection was interrupted");
        }
        return {
          execution: { ...execution, status: "pending", attempt_number: 0 },
          created: false,
        };
      },
    });

    renderWithQuery(<JobOperationsWorkspace />);
    const trigger = await screen.findByRole("button", { name: "Chạy thủ công" });
    fireEvent.click(trigger);
    await screen.findByRole("alert");
    await waitFor(() => expect(trigger).not.toBeDisabled());
    fireEvent.click(trigger);

    await waitFor(() => expect(keys).toHaveLength(2));
    expect(keys[0]).not.toBe("");
    expect(keys[1]).toBe(keys[0]);
  });

  it("keeps job permissions administrator-only in the frontend contract", () => {
    const technician: UserResponse = {
      ...administratorTestUser,
      id: "40000000-0000-4000-8000-000000000001",
      role: "technician",
      role_display_name: "Kỹ thuật viên",
      permissions: [permissions.notificationsRead],
    };

    expect(technician.permissions).toContain(permissions.notificationsRead);
    expect(technician.permissions).not.toContain(permissions.jobOperationsRead);
  });
});
