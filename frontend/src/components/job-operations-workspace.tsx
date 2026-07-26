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
          label="Worker"
          value={worker.data?.ready ? "Sẵn sàng" : "Chưa sẵn sàng"}
          detail={worker.data?.worker_identity ?? "Không có heartbeat hợp lệ"}
          icon={Activity}
          tone={worker.data?.ready ? "green" : "amber"}
        />
        <KpiCard
          label="Job đang chờ"
          value={String(metrics.data?.pending_job_count ?? 0)}
          detail="Pending và retry scheduled"
          icon={Clock3}
          tone="blue"
        />
        <KpiCard
          label="Job dead-letter"
          value={String(metrics.data?.dead_letter_job_count ?? 0)}
          detail="Cần operator xem xét"
          icon={CircleAlert}
          tone={(metrics.data?.dead_letter_job_count ?? 0) > 0 ? "red" : "neutral"}
        />
        <KpiCard
          label="Outbox đang chờ"
          value={String(metrics.data?.pending_outbox_count ?? 0)}
          detail="Sự kiện chưa xử lý xong"
          icon={Database}
          tone="amber"
        />
        <KpiCard
          label="Outbox dead-letter"
          value={String(metrics.data?.dead_letter_outbox_count ?? 0)}
          detail="Không chứa stack trace"
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
        <TabsList>
          <TabsTrigger value="jobs">Job được hỗ trợ</TabsTrigger>
          <TabsTrigger value="executions">Lịch sử chạy</TabsTrigger>
          <TabsTrigger value="outbox">Transactional outbox</TabsTrigger>
        </TabsList>
        <TabsContent value="jobs" className="mt-3">
          <div className="overflow-x-auto rounded-lg border bg-white">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead className="border-b bg-muted/50 text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">Job</th>
                  <th className="px-4 py-3 font-medium">Trạng thái</th>
                  <th className="px-4 py-3 font-medium">Chu kỳ</th>
                  <th className="px-4 py-3 font-medium">Lần chạy kế tiếp</th>
                  <th className="px-4 py-3 font-medium">Thành công gần nhất</th>
                  <th className="px-4 py-3 text-right font-medium">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {jobs.data?.map((job) => (
                  <tr key={job.job_key}>
                    <td className="px-4 py-3">
                      <p className="font-medium">{job.display_name}</p>
                      <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                        {job.job_key}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <Badge
                        variant="outline"
                        className={job.enabled ? "border-green-200 bg-green-50 text-green-700" : ""}
                      >
                        {job.enabled ? "Đang bật" : "Đang tắt"}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {formatInterval(job.interval_seconds)}
                    </td>
                    <td className="px-4 py-3">{formatTimestamp(job.next_run_at)}</td>
                    <td className="px-4 py-3">
                      {formatTimestamp(job.last_successful_run_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-2">
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
                                    `${job.display_name}: ${job.enabled ? "đã tắt" : "đã bật"}.`,
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
                                      ? `Đã đưa ${job.display_name} vào hàng đợi.`
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
                Chưa có job catalog. Hãy kiểm tra migration PM7.
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
                        ? "Đã tạo execution retry mới."
                        : "Yêu cầu retry đã tồn tại.",
                    );
                  },
                },
              );
            }}
          />
        </TabsContent>
        <TabsContent value="outbox" className="mt-3">
          <div className="overflow-x-auto rounded-lg border bg-white">
            <table className="w-full min-w-[850px] text-left text-sm">
              <thead className="border-b bg-muted/50 text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">Event</th>
                  <th className="px-4 py-3 font-medium">Aggregate</th>
                  <th className="px-4 py-3 font-medium">Trạng thái</th>
                  <th className="px-4 py-3 font-medium">Attempts</th>
                  <th className="px-4 py-3 font-medium">Tạo lúc</th>
                  <th className="px-4 py-3 font-medium">Lỗi an toàn</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {outbox.data?.items.map((event) => (
                  <tr key={event.id}>
                    <td className="px-4 py-3 font-mono text-xs">{event.event_type}</td>
                    <td className="px-4 py-3">
                      <p>{event.aggregate_type}</p>
                      <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                        {event.aggregate_id}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <ExecutionStatusBadge status={event.status} />
                    </td>
                    <td className="px-4 py-3 tabular-nums">{event.attempt_count}</td>
                    <td className="px-4 py-3">{formatTimestamp(event.created_at)}</td>
                    <td className="max-w-xs px-4 py-3 text-xs text-muted-foreground">
                      {event.last_safe_error_summary ?? "Không có"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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
    <div className="overflow-x-auto rounded-lg border bg-white">
      <table className="w-full min-w-[950px] text-left text-sm">
        <thead className="border-b bg-muted/50 text-xs text-muted-foreground">
          <tr>
            <th className="px-4 py-3 font-medium">Job</th>
            <th className="px-4 py-3 font-medium">Trạng thái</th>
            <th className="px-4 py-3 font-medium">Trigger</th>
            <th className="px-4 py-3 font-medium">Attempt</th>
            <th className="px-4 py-3 font-medium">Bắt đầu</th>
            <th className="px-4 py-3 font-medium">Hoàn tất</th>
            <th className="px-4 py-3 font-medium">Lỗi an toàn</th>
            <th className="px-4 py-3 text-right font-medium">Thao tác</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {items.map((execution) => (
            <tr key={execution.id}>
              <td className="px-4 py-3">
                <p className="font-medium">{execution.job_key}</p>
                <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                  {execution.id}
                </p>
              </td>
              <td className="px-4 py-3">
                <ExecutionStatusBadge status={execution.status} />
              </td>
              <td className="px-4 py-3">{execution.trigger_type}</td>
              <td className="px-4 py-3 tabular-nums">{execution.attempt_number}</td>
              <td className="px-4 py-3">{formatTimestamp(execution.started_at)}</td>
              <td className="px-4 py-3">{formatTimestamp(execution.completed_at)}</td>
              <td className="max-w-xs px-4 py-3 text-xs text-muted-foreground">
                {execution.safe_error_summary ?? "Không có"}
              </td>
              <td className="px-4 py-3 text-right">
                {(execution.status === "failed" ||
                  execution.status === "dead_lettered") && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={retryPending}
                    onClick={() => onRetry(execution)}
                  >
                    <RotateCcw aria-hidden="true" />
                    Retry
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {items.length === 0 && (
        <p className="p-8 text-center text-sm text-muted-foreground">
          Chưa có execution.
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
    retry_scheduled: "Chờ retry",
    dead_lettered: "Dead-letter",
    cancelled: "Đã hủy",
    skipped: "Đã bỏ qua",
  };
  return (
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
      {labels[status] ?? status}
    </Badge>
  );
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
