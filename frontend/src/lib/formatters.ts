import type { MaintenanceStatus, RiskLevel, TicketPriority } from "@/lib/types";

export const missingValue = "Chưa có dữ liệu";

const dateFormatter = new Intl.DateTimeFormat("vi-VN", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  timeZone: "Asia/Ho_Chi_Minh",
});

const timestampFormatter = new Intl.DateTimeFormat("vi-VN", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: "Asia/Ho_Chi_Minh",
});

export function formatDate(value: string | null | undefined): string {
  if (!value) return missingValue;
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? new Date(`${value}T12:00:00+07:00`)
    : new Date(value);
  return Number.isNaN(dateOnly.getTime()) ? missingValue : dateFormatter.format(dateOnly);
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return missingValue;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? missingValue : timestampFormatter.format(date);
}

export function formatPercentage(value: number | null | undefined, digits = 1): string {
  return value == null ? missingValue : `${value.toFixed(digits)}%`;
}

export function formatDurationHours(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return missingValue;
  if (value < 24) return `${value.toFixed(value < 10 ? 1 : 0)} giờ`;
  const days = Math.floor(value / 24);
  const hours = Math.round(value % 24);
  return hours ? `${days} ngày ${hours} giờ` : `${days} ngày`;
}

export function formatElapsedTime(start: string, end?: string | null): string {
  const startTime = new Date(start).getTime();
  const endTime = end ? new Date(end).getTime() : Date.now();
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime) || endTime < startTime) {
    return missingValue;
  }
  return formatDurationHours((endTime - startTime) / 3_600_000);
}

export function formatRiskLabel(value: RiskLevel | null | undefined): RiskLevel | null {
  return value ?? null;
}

export function formatMaintenanceLabel(
  value: MaintenanceStatus | null | undefined,
): MaintenanceStatus | null {
  return value ?? null;
}

export function formatPriorityLabel(
  value: TicketPriority | null | undefined,
): TicketPriority {
  return value ?? "Trung bình";
}

export function presentContributingFactors(value: string | null | undefined): string[] {
  if (!value?.trim()) return [];
  return (value.match(/[^.!?]+[.!?]?/g) ?? [value])
    .map((item) => item.trim())
    .filter(Boolean);
}

const metricLabels: Record<string, string> = {
  energy_kwh: "Điện năng tiêu thụ",
  runtime_hours: "Thời gian vận hành",
  temperature: "Nhiệt độ",
  vibration: "Độ rung",
  pressure: "Áp suất",
};

export function formatMetricList(value: string | undefined): string {
  if (!value?.trim()) return missingValue;
  return value
    .split(",")
    .map((metric) => metricLabels[metric.trim()] ?? metric.trim())
    .join(" / ");
}
