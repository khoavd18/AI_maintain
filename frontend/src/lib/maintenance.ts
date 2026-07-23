import type { WorkOrderChecklistUpdateRequest } from "@/lib/api/maintenance-schemas";

export type IntervalUnit = "day" | "week" | "month" | "year";

const unitLabels: Record<IntervalUnit, string> = {
  day: "ngày",
  week: "tuần",
  month: "tháng",
  year: "năm",
};

export function recurrenceSummary(intervalValue: number, intervalUnit: IntervalUnit) {
  return `Mỗi ${intervalValue} ${unitLabels[intervalUnit]}`;
}

export function todayIso() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

export function addDaysIso(value: string, days: number) {
  const date = new Date(`${value}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function checklistValidationMessage(
  checklist: Array<{
    id: string;
    is_required: boolean;
    safety_critical: boolean;
    result_status: string;
  }>,
  responses: WorkOrderChecklistUpdateRequest["responses"],
) {
  const byId = new Map(responses.map((response) => [response.item_id, response]));
  const missing = checklist.filter((item) => {
    const response = byId.get(item.id);
    return item.is_required && (!response || response.result_status === "not_applicable");
  });
  if (missing.length) return `Còn ${missing.length} bước bắt buộc chưa hoàn tất.`;
  const failedSafety = checklist.filter((item) => {
    const response = byId.get(item.id);
    return item.safety_critical && response?.result_status === "fail";
  });
  if (failedSafety.length) {
    return "Có bước an toàn quan trọng không đạt. Work order chưa thể hoàn tất.";
  }
  return null;
}

export function isTerminalWorkOrderStatus(status: string) {
  return status === "verified" || status === "cancelled";
}
