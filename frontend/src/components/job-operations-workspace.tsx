"use client";

import {
  Activity,
  CircleAlert,
  Clock3,
  Database,
  Play,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import { useRef, useState } from "react";

import { KpiCard } from "@/components/kpi-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import {
  useJobExecutionsQuery,
  useJobsQuery,
  useJobStateMutation,
  useOperationalMetricsQuery,
  useOutboxQuery,
  useRetryExecutionMutation,
  useTriggerJobMutation,
  useWorkerHealthQuery,
} from "@/hooks/use-operations";
import type { JobExecution } from "@/lib/api/operations-schemas";
import { getApiErrorMessage } from "@/lib/api/errors";
import { formatTimestamp } from "@/lib/formatters";
import { cn } from "@/lib/utils";

export function JobOperationsWorkspace() {
  const jobs = useJobsQuery();
  const executions = useJobExecutionsQuery({ page: 1, page_size: 50 });
  const outbox = useOutboxQuery({ page: 1, page_size: 50 });
  const metrics = useOperationalMetricsQuery();
  const worker = useWorkerHealthQuery();
  const stateMutation = useJobStateMutation();
  const triggerMutation = useTriggerJobMutation();
  const retryMutation = useRetryExecutionMutation();
  const [confirmation, setConfirmation] = useState<string | null>(null);
  const operationKeys = useRef(new Map<string, string>());

  const keyFor = (operation: string) => {
    const existing = operationKeys.current.get(operation);
    if (existing) return existing;
    const created = operationKey(operation);
    operationKeys.current.set(operation, created);
    return created;
  };
  const confirmOperation = (operation: string) => {
    operationKeys.current.delete(operation);
  };

  const error =
    jobs.error ??
    executions.error ??
    outbox.error ??
    metrics.error ??
    stateMutation.error ??
    triggerMutation.error ??
    retryMutation.error;
  const refresh = async () => {
    await Promise.all([
      jobs.refetch(),
      executions.refetch(),
      outbox.refetch(),
      metrics.refetch(),
      worker.refetch(),
    ]);
  };

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <KpiCard
          label="Tiến trình nền"
          value={worker.data?.ready ? "Sẵn sàng" : "Chưa sẵn sàng"}
          detail={worker.data?.worker_identity ?? "Chưa có tín hiệu hoạt động hợp lệ"}
          icon={Activity}
          tone={worker.data?.ready ? "green" : "amber"}
        />
        <KpiCard
          label="Tác vụ đang chờ"
          value={String(metrics.data?.pending_job_count ?? 0)}
          detail="Đang chờ hoặc chờ thử lại"
          icon={Clock3}
          tone="blue"
        />
        <KpiCard
          label="Tác vụ cần can thiệp"
          value={String(metrics.data?.dead_letter_job_count ?? 0)}
          detail="Đã hết lượt thử; cần quản trị viên xem xét"
          icon={CircleAlert}
          tone={(metrics.data?.dead_letter_job_count ?? 0) > 0 ? "red" : "neutral"}
        />
        <KpiCard
          label="Sự kiện đang chờ"
          value={String(metrics.data?.pending_outbox_count ?? 0)}
          detail="Sự kiện chưa xử lý xong"
          icon={Database}
          tone="amber"
        />
        <KpiCard
          label="Sự kiện cần can thiệp"
          value={String(metrics.data?.dead_letter_outbox_count ?? 0)}
          detail="Không hiển thị dấu vết lỗi nội bộ"
          icon={CircleAlert}
          tone={(metrics.data?.dead_letter_outbox_count ?? 0) > 0 ? "red" : "neutral"}
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div aria-live="polite" className="text-sm text-green-700">
          {confirmation}
        </div>
        <Button type="button" variant="outline" onClick={() => void refresh()}>
          <RefreshCw aria-hidden="true" />
          Làm mới
        </Button>
      </div>
      {error && (
        <div role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-800">
          {getApiErrorMessage(error)}
        </div>
      )}

      <Tabs defaultValue="jobs">
        <TabsList className="h-auto w-full flex-wrap justify-start">
          <TabsTrigger value="jobs">Tác vụ định kỳ</TabsTrigger>
          <TabsTrigger value="executions">Lịch sử chạy</TabsTrigger>
          <TabsTrigger value="outbox">Hộp sự kiện</TabsTrigger>
        </TabsList>
        <TabsContent value="jobs" className="mt-3">
          <div className="overflow-hidden rounded-lg border bg-white lg:overflow-x-auto">
            <table className="block w-full text-left text-sm lg:table lg:min-w-[900px]">
              <thead className="hidden border-b bg-muted/50 text-xs text-muted-foreground lg:table-header-group">
                <tr>
                  <th className="px-4 py-3 font-medium">Tác vụ</th>
                  <th className="px-4 py-3 font-medium">Trạng thái</th>
                  <th className="px-4 py-3 font-medium">Chu kỳ</th>
                  <th className="px-4 py-3 font-medium">Lần chạy kế tiếp</th>
                  <th className="px-4 py-3 font-medium">Thành công gần nhất</th>
                  <th className="px-4 py-3 text-right font-medium">Thao tác</th>
                </tr>
              </thead>
              <tbody className="block space-y-3 p-3 lg:table-row-group lg:space-y-0 lg:p-0">
                {jobs.data?.map((job) => (
                  <tr
                    key={job.job_key}
                    className="grid grid-cols-2 gap-4 rounded-lg border bg-card p-4 shadow-sm lg:table-row lg:rounded-none lg:border-x-0 lg:border-t-0 lg:bg-transparent lg:p-0 lg:shadow-none"
                  >
                    <td className="col-span-2 block p-0 lg:table-cell lg:px-4 lg:py-3">
                      <p className="font-medium">
                        {jobDisplayName(job.job_type, job.display_name)}
                      </p>
                      <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                        {job.job_key}
                      </p>
                    </td>
                    <td className="block p-0 lg:table-cell lg:px-4 lg:py-3">
                      <MobileFieldLabel>Trạng thái</MobileFieldLabel>
                      <Badge
                        variant="outline"
                        className={job.enabled ? "border-green-200 bg-green-50 text-green-700" : ""}
                      >
                        {job.enabled ? "Đang bật" : "Đang tắt"}
                      </Badge>
                    </td>
                    <td className="block p-0 tabular-nums lg:table-cell lg:px-4 lg:py-3">
                      <MobileFieldLabel>Chu kỳ</MobileFieldLabel>
                      {formatInterval(job.interval_seconds)}
                    </td>
                    <td className="col-span-2 block p-0 sm:col-span-1 lg:table-cell lg:px-4 lg:py-3">
                      <MobileFieldLabel>Lần chạy kế tiếp</MobileFieldLabel>
                      {formatTimestamp(job.next_run_at)}
                    </td>
                    <td className="col-span-2 block p-0 sm:col-span-1 lg:table-cell lg:px-4 lg:py-3">
                      <MobileFieldLabel>Thành công gần nhất</MobileFieldLabel>
                      {formatTimestamp(job.last_successful_run_at)}
                    </td>
                    <td className="col-span-2 block p-0 lg:table-cell lg:px-4 lg:py-3">
                      <div className="grid gap-2 sm:grid-cols-2 lg:flex lg:justify-end">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={stateMutation.isPending}
                          onClick={() =>
                            stateMutation.mutate(
                              {
                                jobKey: job.job_key,
                                enabled: !job.enabled,
                                expectedVersion: job.version,
                              },
                              {
                                onSuccess: () =>
                                  setConfirmation(
                                    `${jobDisplayName(job.job_type, job.display_name)}: ${job.enabled ? "đã tắt" : "đã bật"}.`,
                                  ),
                              },
                            )
                          }
                        >
                          {job.enabled ? "Tắt" : "Bật"}
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          disabled={triggerMutation.isPending}
                          onClick={() => {
                            const operation = `trigger-${job.job_key}`;
                            triggerMutation.mutate(
                              {
                                jobKey: job.job_key,
                                idempotencyKey: keyFor(operation),
                              },
                              {
                                onSuccess: (result) => {
                                  confirmOperation(operation);
                                  setConfirmation(
                                    result.created
                                      ? `Đã đưa ${jobDisplayName(job.job_type, job.display_name)} vào hàng đợi.`
                                      : "Yêu cầu này đã tồn tại và không được tạo trùng.",
                                  );
                                },
                              },
                            );
                          }}
                        >
                          <Play aria-hidden="true" />
                          Chạy thủ công
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {jobs.data?.length === 0 && (
              <p className="p-8 text-center text-sm text-muted-foreground">
                Chưa có danh mục tác vụ. Hãy kiểm tra trạng thái nâng cấp cơ sở dữ liệu PM7.
              </p>
            )}
          </div>
        </TabsContent>
        <TabsContent value="executions" className="mt-3">
          <ExecutionTable
            items={executions.data?.items ?? []}
            retryPending={retryMutation.isPending}
            onRetry={(execution) => {
              const operation = `retry-${execution.id}`;
              retryMutation.mutate(
                {
                  executionId: execution.id,
                  idempotencyKey: keyFor(operation),
                },
                {
                  onSuccess: (result) => {
                    confirmOperation(operation);
                    setConfirmation(
                      result.created
                        ? "Đã tạo lần chạy thử lại mới."
                        : "Yêu cầu thử lại đã tồn tại.",
                    );
                  },
                },
              );
            }}
          />
        </TabsContent>
        <TabsContent value="outbox" className="mt-3">
          <div className="overflow-hidden rounded-lg border bg-white lg:overflow-x-auto">
            <table className="block w-full text-left text-sm lg:table lg:min-w-[850px]">
              <thead className="hidden border-b bg-muted/50 text-xs text-muted-foreground lg:table-header-group">
                <tr>
                  <th className="px-4 py-3 font-medium">Sự kiện</th>
                  <th className="px-4 py-3 font-medium">Đối tượng</th>
                  <th className="px-4 py-3 font-medium">Trạng thái</th>
                  <th className="px-4 py-3 font-medium">Số lần thử</th>
                  <th className="px-4 py-3 font-medium">Tạo lúc</th>
                  <th className="px-4 py-3 font-medium">Thông báo lỗi</th>
                </tr>
              </thead>
              <tbody className="block space-y-3 p-3 lg:table-row-group lg:space-y-0 lg:p-0">
                {outbox.data?.items.map((event) => (
                  <tr
                    key={event.id}
                    className="grid grid-cols-2 gap-4 rounded-lg border bg-card p-4 shadow-sm lg:table-row lg:rounded-none lg:border-x-0 lg:border-t-0 lg:bg-transparent lg:p-0 lg:shadow-none"
                  >
                    <td className="col-span-2 block p-0 lg:table-cell lg:px-4 lg:py-3">
                      <p className="font-medium">{eventDisplayName(event.event_type)}</p>
                      <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                        {event.event_type}
                      </p>
                    </td>
                    <td className="col-span-2 block p-0 sm:col-span-1 lg:table-cell lg:px-4 lg:py-3">
                      <MobileFieldLabel>Đối tượng</MobileFieldLabel>
                      <p>{aggregateDisplayName(event.aggregate_type)}</p>
                      <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                        {event.aggregate_type} · {event.aggregate_id}
                      </p>
                    </td>
                    <td className="col-span-2 block p-0 sm:col-span-1 lg:table-cell lg:px-4 lg:py-3">
                      <MobileFieldLabel>Trạng thái</MobileFieldLabel>
                      <ExecutionStatusBadge status={event.status} />
                    </td>
                    <td className="block p-0 tabular-nums lg:table-cell lg:px-4 lg:py-3">
                      <MobileFieldLabel>Số lần thử</MobileFieldLabel>
                      {event.attempt_count}
                    </td>
                    <td className="block p-0 lg:table-cell lg:px-4 lg:py-3">
                      <MobileFieldLabel>Tạo lúc</MobileFieldLabel>
                      {formatTimestamp(event.created_at)}
                    </td>
                    <td className="col-span-2 block max-w-none p-0 text-xs text-muted-foreground lg:table-cell lg:max-w-xs lg:px-4 lg:py-3">
                      <MobileFieldLabel>Thông báo lỗi</MobileFieldLabel>
                      <SafeErrorSummary
                        code={event.last_safe_error_code}
                        summary={event.last_safe_error_summary}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {outbox.data?.items.length === 0 && (
              <p className="p-8 text-center text-sm text-muted-foreground">
                Chưa có sự kiện trong hộp sự kiện.
              </p>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function ExecutionTable({
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

function ExecutionStatusBadge({ status }: { status: string }) {
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

function MobileFieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="mb-1 block text-xs font-medium text-muted-foreground lg:hidden">
      {children}
    </span>
  );
}

function SafeErrorSummary({
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

function jobDisplayName(code: string, fallback: string): string {
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

function eventDisplayName(code: string): string {
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

function aggregateDisplayName(code: string): string {
  return aggregateDisplayNames[code] ?? "Đối tượng hệ thống";
}

function triggerDisplayName(trigger: JobExecution["trigger_type"]): string {
  return trigger === "manual" ? "Thủ công" : "Theo lịch";
}

function formatInterval(seconds: number): string {
  if (seconds % 86400 === 0) return `${seconds / 86400} ngày`;
  if (seconds % 3600 === 0) return `${seconds / 3600} giờ`;
  if (seconds % 60 === 0) return `${seconds / 60} phút`;
  return `${seconds} giây`;
}

function operationKey(prefix: string): string {
  const suffix =
    typeof globalThis.crypto?.randomUUID === "function"
      ? globalThis.crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`.slice(0, 100);
}
