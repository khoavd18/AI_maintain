"use client";

import Link from "next/link";
import {
  AlertTriangle,
  Clock3,
  Loader2,
  Play,
  SearchCheck,
  ShieldAlert,
} from "lucide-react";
import { useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { KpiCard } from "@/components/kpi-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import {
  useEvaluateEscalationsMutation,
  useSlaSummaryQuery,
} from "@/hooks/use-ticketing";
import { getApiErrorMessage } from "@/lib/api/errors";
import { permissions } from "@/lib/auth";
import { formatTimestamp } from "@/lib/formatters";

export function EscalationDashboard() {
  const auth = useAuth();
  const summary = useSlaSummaryQuery();
  const evaluation = useEvaluateEscalationsMutation();
  const [asOf, setAsOf] = useState("");

  if (summary.isPending) return <LoadingSkeleton />;
  if (summary.isError) {
    return (
      <ErrorState
        title="Chưa tải được SLA summary"
        description={getApiErrorMessage(summary.error)}
        action={<RetryButton onClick={() => void summary.refetch()} />}
      />
    );
  }

  async function evaluate(dryRun: boolean) {
    try {
      await evaluation.mutateAsync({
        dry_run: dryRun,
        as_of: asOf ? new Date(asOf).toISOString() : null,
      });
    } catch {
      // Safe error is rendered below.
    }
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Critical đang mở"
          value={String(summary.data.critical_count)}
          detail="Ticket-level escalation candidate"
          icon={AlertTriangle}
          tone="red"
        />
        <KpiCard
          label="Sắp đến hạn"
          value={String(summary.data.due_soon_count)}
          detail="Theo business minutes còn lại"
          icon={Clock3}
          tone="amber"
        />
        <KpiCard
          label="Vi phạm SLA"
          value={String(summary.data.breached_count)}
          detail="First response hoặc resolution"
          icon={ShieldAlert}
          tone="red"
        />
        <KpiCard
          label="Đang chờ"
          value={String(summary.data.waiting_count)}
          detail="Pause phụ thuộc policy snapshot"
          icon={Clock3}
          tone="orange"
        />
      </div>

      <section className="rounded-lg border bg-white">
        <header className="flex flex-col justify-between gap-4 border-b p-4 sm:flex-row sm:items-end">
          <div>
            <h2 className="text-sm font-semibold">Đánh giá escalation</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Chạy có chủ đích qua cùng một service; không có worker hoặc gửi email tự động.
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <div className="space-y-1.5">
              <Label htmlFor="escalation-as-of">Thời điểm đánh giá</Label>
              <Input
                id="escalation-as-of"
                type="datetime-local"
                value={asOf}
                onChange={(event) => setAsOf(event.target.value)}
              />
            </div>
            <Button
              type="button"
              variant="outline"
              disabled={evaluation.isPending}
              onClick={() => void evaluate(true)}
            >
              <SearchCheck aria-hidden="true" />
              Dry run
            </Button>
            {auth.can(permissions.escalationsExecute) && (
              <Button
                type="button"
                disabled={evaluation.isPending}
                onClick={() => void evaluate(false)}
              >
                {evaluation.isPending ? (
                  <Loader2 className="animate-spin" aria-hidden="true" />
                ) : (
                  <Play aria-hidden="true" />
                )}
                Ghi escalation events
              </Button>
            )}
          </div>
        </header>

        {evaluation.isError && (
          <p
            role="alert"
            className="m-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900"
          >
            {getApiErrorMessage(evaluation.error)}
          </p>
        )}

        {evaluation.data ? (
          <>
            <div className="grid gap-3 border-b p-4 sm:grid-cols-3">
              <ResultFact
                label="Chế độ"
                value={evaluation.data.dry_run ? "Dry run" : "Đã ghi events"}
              />
              <ResultFact
                label="Candidate"
                value={String(evaluation.data.candidate_count)}
              />
              <ResultFact
                label="Event mới"
                value={String(evaluation.data.created_count)}
              />
            </div>
            {evaluation.data.candidates.length ? (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Ticket</TableHead>
                      <TableHead>Quy tắc</TableHead>
                      <TableHead>Clock</TableHead>
                      <TableHead>SLA occurrence</TableHead>
                      <TableHead>Hạn</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {evaluation.data.candidates.map((candidate) => (
                      <TableRow
                        key={`${candidate.ticket_id}-${candidate.rule_code}-${candidate.clock_type}-${candidate.occurrence_number}`}
                      >
                        <TableCell className="font-mono text-xs font-semibold text-primary">
                          {candidate.ticket_id}
                        </TableCell>
                        <TableCell>
                          <p className="font-medium">{candidate.rule_display}</p>
                          <p className="mt-1 font-mono text-xs text-muted-foreground">
                            {candidate.rule_code}
                          </p>
                        </TableCell>
                        <TableCell>{candidate.clock_type ?? "ticket"}</TableCell>
                        <TableCell>{candidate.occurrence_number}</TableCell>
                        <TableCell>{formatTimestamp(candidate.due_at)}</TableCell>
                        <TableCell className="text-right">
                          <Button asChild variant="ghost" size="sm">
                            <Link href={`/tickets/${candidate.ticket_id}`}>Mở ticket</Link>
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ) : (
              <p className="p-6 text-sm text-muted-foreground">
                Không có escalation candidate tại thời điểm đánh giá.
              </p>
            )}
          </>
        ) : (
          <p className="p-6 text-sm text-muted-foreground">
            Chạy dry run để xem candidate trước khi ghi event idempotent.
          </p>
        )}
      </section>
    </div>
  );
}

function ResultFact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
    </div>
  );
}
