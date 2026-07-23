import { describe, expect, it } from "vitest";

import {
  checklistItemRequestSchema,
  maintenancePlanCreateRequestSchema,
} from "@/lib/api/maintenance-schemas";
import {
  addDaysIso,
  checklistValidationMessage,
  isTerminalWorkOrderStatus,
  recurrenceSummary,
} from "@/lib/maintenance";

describe("maintenance planning helpers", () => {
  it("presents only the controlled recurrence vocabulary", () => {
    expect(recurrenceSummary(2, "week")).toBe("Mỗi 2 tuần");
    expect(addDaysIso("2028-02-28", 1)).toBe("2028-02-29");
  });

  it("rejects an incoherent plan date range and raw recurrence rules", () => {
    const request = {
      plan_code: "PM-GEN-001",
      name: "Bảo trì máy phát",
      description: null,
      asset_id: "GENERATOR_002",
      interval_value: 1,
      interval_unit: "month",
      start_date: "2026-08-01",
      end_date: "2026-07-01",
      local_timezone: "Asia/Ho_Chi_Minh",
      lead_time_days: 7,
      grace_period_days: 1,
      estimated_duration_minutes: 60,
      default_priority: "high",
      default_assignee_user_id: null,
      checklist_template_id: null,
      instructions: null,
      recurrence_rule: null,
    };
    expect(maintenancePlanCreateRequestSchema.safeParse(request).success).toBe(false);
    expect(maintenancePlanCreateRequestSchema.safeParse({ ...request, end_date: null, recurrence_rule: "FREQ=DAILY" }).success).toBe(false);
  });

  it("validates numeric checklist bounds on the client", () => {
    const parsed = checklistItemRequestSchema.safeParse({
      sequence: 1,
      instruction: "Đo độ rung",
      response_type: "numeric",
      is_required: true,
      safety_critical: false,
      allow_not_applicable: false,
      expected_unit: "mm/s",
      minimum_value: 10,
      maximum_value: 5,
      guidance: null,
    });
    expect(parsed.success).toBe(false);
  });
});

describe("work-order completion guard", () => {
  const checklist = [
    { id: "required", is_required: true, safety_critical: false, result_status: "pending" },
    { id: "safety", is_required: true, safety_critical: true, result_status: "pending" },
  ];

  it("reports required steps and safety failures before completion", () => {
    expect(checklistValidationMessage(checklist, [])).toContain("2 bước bắt buộc");
    expect(checklistValidationMessage(checklist, [
      { item_id: "required", result_status: "completed", boolean_value: true, numeric_value: null, text_value: null, note: null },
      { item_id: "safety", result_status: "fail", boolean_value: null, numeric_value: null, text_value: null, note: null },
    ])).toContain("an toàn quan trọng");
  });

  it("distinguishes terminal work-order states", () => {
    expect(isTerminalWorkOrderStatus("verified")).toBe(true);
    expect(isTerminalWorkOrderStatus("cancelled")).toBe(true);
    expect(isTerminalWorkOrderStatus("completed")).toBe(false);
  });
});
