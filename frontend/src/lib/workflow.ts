import type { ZodIssue } from "zod";

import {
  maintenanceResultSchema,
  ticketFailureCategorySchema,
  ticketPrioritySchema,
  type TicketRecord,
} from "@/lib/api/schemas";
import type { Asset, TicketStatus } from "@/lib/types";

export const ticketPriorities = ticketPrioritySchema.options;
export const ticketFailureCategories = ticketFailureCategorySchema.options;
export const maintenanceResults = maintenanceResultSchema.options;

export const ticketStatusApiByCode: Record<TicketStatus, TicketRecord["status"]> = {
  new: "Mới tạo",
  in_progress: "Đang xử lý",
  resolved: "Đã xử lý",
};

export function suggestedIssueDescription(asset: Asset, latestAnomaly?: string): string {
  const risk = asset.riskScore == null ? "chưa có score" : asset.riskScore.toFixed(2);
  const maintenance =
    asset.overdueDays > 0
      ? `bảo trì quá hạn ${asset.overdueDays} ngày`
      : `bảo trì ${asset.maintenanceStatus?.toLocaleLowerCase("vi") ?? "chưa xác định"}`;
  const anomaly = latestAnomaly ? ` Bất thường gần nhất: ${latestAnomaly}` : "";
  return `Kiểm tra ${asset.id}: Risk ${risk} (${asset.riskLevel ?? "chưa phân loại"}), ${maintenance}. Yếu tố đóng góp: ${asset.contributingFactors}.${anomaly}`;
}

export function suggestedFailureCategory(asset: Asset, latestAnomaly?: string) {
  const context = `${asset.type} ${asset.contributingFactors} ${latestAnomaly ?? ""}`.toLocaleLowerCase("vi");
  if (context.includes("rung")) return "Lỗi rung động" as const;
  if (context.includes("điện") || context.includes("ắc quy")) return "Lỗi điện" as const;
  if (context.includes("áp suất")) return "Lỗi áp suất" as const;
  if (context.includes("runtime") || context.includes("thời gian vận hành")) {
    return "Lỗi thời gian vận hành" as const;
  }
  if (context.includes("cảm biến")) return "Lỗi cảm biến" as const;
  if (context.includes("làm lạnh") || context.includes("máy lạnh")) return "Lỗi làm lạnh" as const;
  return "Không có lỗi" as const;
}

export function suggestedPriority(asset: Asset) {
  if (asset.riskLevel === "Khẩn cấp") return "Khẩn cấp" as const;
  if (asset.riskLevel === "Cao") return "Cao" as const;
  return "Trung bình" as const;
}

export function zodFieldErrors(issues: ZodIssue[]): Record<string, string> {
  return Object.fromEntries(
    issues.map((issue) => [String(issue.path[0] ?? "form"), issue.message]),
  );
}

export function todayInVietnam(): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Ho_Chi_Minh",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

export function addDays(dateOnly: string, days: number): string {
  const date = new Date(`${dateOnly}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function latestDateOnly(...values: (string | null | undefined)[]): string {
  return values.filter((value): value is string => Boolean(value)).sort().at(-1) ?? "";
}
