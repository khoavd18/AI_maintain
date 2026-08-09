"use client";

import { RotateCcw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { JobExecution } from "@/lib/api/operations-schemas";
import { formatTimestamp } from "@/lib/formatters";
import { cn } from "@/lib/utils";

export function ExecutionTable({
  items,
  retryPending,
  onRetry,
}: {
  items: JobExecution[];
  retryPending: boolean;
  onRetry: (execution: JobExecution) => void;
}) {
  return (
    <div className="overflow-hidden rounded-lg border bg-white lg:overflow-x-auto">
      <table className="block w-full text-left text-sm lg:table lg:min-w-[950px]">
        <thead className="hidden border-b bg-muted/50 text-xs text-muted-foreground lg:table-header-group">
          <tr>
            <th className="px-4 py-3 font-medium">Tác vụ</th>
            <th className="px-4 py-3 font-medium">Trạng thái</th>
            <th className="px-4 py-3 font-medium">Nguồn kích hoạt</th>
            <th className="px-4 py-3 font-medium">Lần thử</th>
            <th className="px-4 py-3 font-medium">Bắt đầu</th>
            <th className="px-4 py-3 font-medium">Hoàn tất</th>
            <th className="px-4 py-3 font-medium">Thông báo lỗi</th>
            <th className="px-4 py-3 text-right font-medium">Thao tác</th>
          </tr>
        </thead>
        <tbody className="block space-y-3 p-3 lg:table-row-group lg:space-y-0 lg:p-0">
          {items.map((execution) => (
            <tr
              key={execution.id}
              className="grid grid-cols-2 gap-4 rounded-lg border bg-card p-4 shadow-sm lg:table-row lg:rounded-none lg:border-x-0 lg:border-t-0 lg:bg-transparent lg:p-0 lg:shadow-none"
            >
              <td className="col-span-2 block p-0 lg:table-cell lg:px-4 lg:py-3">
                <p className="font-medium">
                  {jobDisplayName(execution.job_key, execution.job_key)}
                </p>
                <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                  {execution.job_key} · {execution.id}
                </p>
              </td>
              <td className="block p-0 lg:table-cell lg:px-4 lg:py-3">
                <MobileFieldLabel>Trạng thái</MobileFieldLabel>
                <ExecutionStatusBadge status={execution.status} />
              </td>
              <td className="block p-0 lg:table-cell lg:px-4 lg:py-3">
                <MobileFieldLabel>Nguồn kích hoạt</MobileFieldLabel>
                <p>{triggerDisplayName(execution.trigger_type)}</p>
                <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                  {execution.trigger_type}
                </p>
              </td>
              <td className="col-span-2 block p-0 tabular-nums sm:col-span-1 lg:table-cell lg:px-4 lg:py-3">
                <MobileFieldLabel>Lần thử</MobileFieldLabel>
                {execution.attempt_number}
              </td>
              <td className="col-span-2 block p-0 sm:col-span-1 lg:table-cell lg:px-4 lg:py-3">
                <MobileFieldLabel>Bắt đầu</MobileFieldLabel>
                {formatTimestamp(execution.started_at)}
              </td>
              <td className="col-span-2 block p-0 sm:col-span-1 lg:table-cell lg:px-4 lg:py-3">
                <MobileFieldLabel>Hoàn tất</MobileFieldLabel>
                {formatTimestamp(execution.completed_at)}
              </td>
              <td className="col-span-2 block max-w-none p-0 text-xs text-muted-foreground lg:table-cell lg:max-w-xs lg:px-4 lg:py-3">
                <MobileFieldLabel>Thông báo lỗi</MobileFieldLabel>
                <SafeErrorSummary
                  code={execution.safe_error_code}
                  summary={execution.safe_error_summary}
                />
              </td>
              <td className="col-span-2 block p-0 text-right lg:table-cell lg:px-4 lg:py-3">
                {(execution.status === "failed" ||
                  execution.status === "dead_lettered") && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={retryPending}
                    onClick={() => onRetry(execution)}
                    className="w-full lg:w-auto"
                  >
                    <RotateCcw aria-hidden="true" />
                    Thử lại
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {items.length === 0 && (
        <p className="p-8 text-center text-sm text-muted-foreground">
          Chưa có lần chạy nào.
        </p>
      )}
    </div>
  );
}

export function ExecutionStatusBadge({ status }: { status: string }) {
  const labels: Record<string, string> = {
    pending: "Đang chờ",
    processing: "Đang xử lý",
    running: "Đang chạy",
    succeeded: "Thành công",
    processed: "Đã xử lý",
    failed: "Thất bại",
    retry_scheduled: "Chờ thử lại",
    dead_lettered: "Cần can thiệp",
    cancelled: "Đã hủy",
    skipped: "Đã bỏ qua",
  };
  return (
    <div className="space-y-1">
      <Badge
        variant="outline"
        className={cn(
          status === "succeeded" || status === "processed"
            ? "border-green-200 bg-green-50 text-green-700"
            : status === "failed" || status === "dead_lettered"
              ? "border-red-200 bg-red-50 text-red-700"
              : status === "running" || status === "processing"
                ? "border-blue-200 bg-blue-50 text-blue-700"
                : "border-amber-200 bg-amber-50 text-amber-800",
        )}
      >
        {labels[status] ?? "Trạng thái hệ thống"}
      </Badge>
      <p className="font-mono text-[11px] text-muted-foreground">{status}</p>
    </div>
  );
}

export function MobileFieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="mb-1 block text-xs font-medium text-muted-foreground lg:hidden">
      {children}
    </span>
  );
}

export function SafeErrorSummary({
  code,
  summary,
}: {
  code: string | null;
  summary: string | null;
}) {
  if (!code && !summary) return <span>Không có lỗi</span>;

  return (
    <div className="space-y-1">
      <p>{summary ?? "Tác vụ không thể hoàn tất an toàn."}</p>
      {code && <p className="font-mono text-[11px]">{code}</p>}
    </div>
  );
}

const jobDisplayNames: Record<string, string> = {
  preventive_generation: "Tạo lệnh công việc bảo trì định kỳ",
  sla_escalation: "Đánh giá SLA và chuyển cấp cảnh báo",
  analytics_refresh: "Làm mới phân tích dữ liệu theo đợt",
  inventory_reorder_detection: "Phát hiện tồn kho dưới điểm đặt hàng",
};

export function jobDisplayName(code: string, fallback: string): string {
  return jobDisplayNames[code] ?? fallback;
}

const eventDisplayNames: Record<string, string> = {
  "ticket.critical_created": "Đã tạo phiếu sự cố khẩn cấp",
  "ticket.assigned": "Đã phân công phiếu sự cố",
  "ticket.held": "Phiếu sự cố chuyển sang chờ",
  "ticket.resumed": "Phiếu sự cố tiếp tục xử lý",
  "ticket.sla_warning": "Phiếu sự cố sắp đến hạn SLA",
  "ticket.sla_breach": "Phiếu sự cố đã quá hạn SLA",
  "ticket.escalated": "Phiếu sự cố được chuyển cấp",
  "work_order.assigned": "Đã phân công lệnh công việc",
  "work_order.completed": "Lệnh công việc chờ xác minh",
  "inventory.issue_completed": "Đã hoàn tất xuất vật tư",
  "preventive.work_orders_generated": "Đã tạo lệnh công việc định kỳ",
  "inventory.stock_below_reorder": "Tồn kho dưới điểm đặt hàng",
  "analytics.refresh_failed": "Làm mới phân tích dữ liệu thất bại",
  "operations.alert_raised": "Đã phát cảnh báo vận hành",
  "operations.alert_recovered": "Cảnh báo vận hành đã phục hồi",
};

export function eventDisplayName(code: string): string {
  return eventDisplayNames[code] ?? "Sự kiện hệ thống";
}

const aggregateDisplayNames: Record<string, string> = {
  ticket: "Phiếu sự cố",
  work_order: "Lệnh công việc",
  inventory_issue: "Phiếu xuất vật tư",
  maintenance_generation: "Đợt tạo bảo trì định kỳ",
  inventory_position: "Vị trí tồn kho",
  job_execution: "Lần chạy tác vụ",
  operational_alert: "Cảnh báo vận hành",
};

export function aggregateDisplayName(code: string): string {
  return aggregateDisplayNames[code] ?? "Đối tượng hệ thống";
}

export function triggerDisplayName(trigger: JobExecution["trigger_type"]): string {
  return trigger === "manual" ? "Thủ công" : "Theo lịch";
}

export function formatInterval(seconds: number): string {
  if (seconds % 86400 === 0) return `${seconds / 86400} ngày`;
  if (seconds % 3600 === 0) return `${seconds / 3600} giờ`;
  if (seconds % 60 === 0) return `${seconds / 60} phút`;
  return `${seconds} giây`;
}

export function operationKey(prefix: string): string {
  const suffix =
    typeof globalThis.crypto?.randomUUID === "function"
      ? globalThis.crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`.slice(0, 100);
}
