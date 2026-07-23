"use client";

import Link from "next/link";
import { Archive, CalendarPlus, Eye, Pause, Play, RefreshCw, Save, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { CodePriorityBadge, PlanStatusBadge, WorkOrderStatusBadge } from "@/components/status-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState, ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import {
  useArchiveMaintenancePlan,
  useGenerateMaintenanceWorkOrders,
  usePauseMaintenancePlan,
  useResumeMaintenancePlan,
  useUpdateMaintenancePlan,
} from "@/hooks/use-api-mutations";
import {
  useMaintenanceOptionsQuery,
  useMaintenancePlanOccurrencesQuery,
  useMaintenancePlanQuery,
  useWorkOrdersQuery,
} from "@/hooks/use-api-queries";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { MaintenancePlan, MaintenancePlanUpdateRequest } from "@/lib/api/maintenance-schemas";
import { permissions } from "@/lib/auth";
import { formatDate, formatTimestamp } from "@/lib/formatters";
import { addDaysIso, recurrenceSummary, todayIso, type IntervalUnit } from "@/lib/maintenance";

export function MaintenancePlanDetail({ planId }: { planId: string }) {
  const auth = useAuth();
  const planQuery = useMaintenancePlanQuery(planId);
  const dateFrom = todayIso();
  const occurrenceQuery = useMaintenancePlanOccurrencesQuery(planId, { date_from: dateFrom, date_to: addDaysIso(dateFrom, 180), limit: 24 });
  const workOrders = useWorkOrdersQuery({ preventive_plan_id: planId, page_size: 100 });
  const pause = usePauseMaintenancePlan(planId);
  const resume = useResumeMaintenancePlan(planId);
  const archive = useArchiveMaintenancePlan(planId);
  const dryRun = useGenerateMaintenanceWorkOrders(true);
  const generate = useGenerateMaintenanceWorkOrders(false);
  const [message, setMessage] = useState<string | null>(null);

  if (planQuery.isPending || occurrenceQuery.isPending || workOrders.isPending) return <LoadingSkeleton />;
  const error = planQuery.error ?? occurrenceQuery.error ?? workOrders.error;
  if (error || !planQuery.data) return <ErrorState title="Chưa tải được preventive plan" description={getApiErrorMessage(error)} action={<RetryButton onClick={() => void Promise.all([planQuery.refetch(), occurrenceQuery.refetch(), workOrders.refetch()])} />} />;
  const plan = planQuery.data;

  async function lifecycleAction(action: "pause" | "resume" | "archive") {
    try {
      if (action === "pause") await pause.mutateAsync(plan.version);
      if (action === "resume") await resume.mutateAsync({ expected_version: plan.version, resume_date: todayIso() });
      if (action === "archive") {
        const reason = window.prompt("Lý do lưu trữ plan (tối thiểu 3 ký tự):");
        if (!reason) return;
        await archive.mutateAsync({ expected_version: plan.version, archive_reason: reason });
      }
      setMessage("Đã cập nhật lifecycle của plan.");
    } catch (actionError) {
      setMessage(getApiErrorMessage(actionError));
    }
  }

  async function generationAction(isDryRun: boolean) {
    if (!isDryRun && !window.confirm(`Tạo work order đến hạn cho ${plan.plan_code}?`)) return;
    try {
      const result = await (isDryRun ? dryRun : generate).mutateAsync({ as_of_date: todayIso(), plan_id: plan.id });
      setMessage(isDryRun ? `Dry run: ${result.would_generate_count} occurrence sẽ tạo work order.` : `Đã tạo ${result.generated_count} work order; retry không tạo bản trùng.`);
    } catch (actionError) {
      setMessage(getApiErrorMessage(actionError));
    }
  }

  return (
    <div className="space-y-5">
      <section className="rounded-lg border bg-white p-4 sm:p-5">
        <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
          <div>
            <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-sm font-semibold text-primary">{plan.plan_code}</span><PlanStatusBadge status={plan.status} label={plan.status_display} /><Badge variant="outline">Version {plan.version}</Badge></div>
            <h2 className="mt-2 text-xl font-semibold">{plan.name}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{plan.asset_id} · {plan.asset_name}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {auth.can(permissions.maintenanceGenerationRun) && plan.status === "active" && <><Button variant="outline" onClick={() => void generationAction(true)} disabled={dryRun.isPending || generate.isPending}><Eye aria-hidden="true" />Dry run</Button><Button variant="outline" onClick={() => void generationAction(false)} disabled={dryRun.isPending || generate.isPending}><CalendarPlus aria-hidden="true" />Generate</Button></>}
            {auth.can(permissions.maintenancePlansPause) && plan.status === "active" && <Button variant="outline" onClick={() => void lifecycleAction("pause")}><Pause aria-hidden="true" />Tạm dừng</Button>}
            {auth.can(permissions.maintenancePlansPause) && plan.status === "paused" && <Button variant="outline" onClick={() => void lifecycleAction("resume")}><Play aria-hidden="true" />Tiếp tục</Button>}
            {auth.can(permissions.maintenancePlansArchive) && plan.status !== "archived" && <Button variant="outline" onClick={() => void lifecycleAction("archive")}><Archive aria-hidden="true" />Lưu trữ</Button>}
          </div>
        </div>
        {message && <p role="status" className="mt-4 rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-800">{message}</p>}
        <dl className="mt-5 grid gap-4 border-t pt-4 sm:grid-cols-2 lg:grid-cols-4">
          <Detail label="Chu kỳ" value={plan.recurrence_summary} />
          <Detail label="Kỳ tiếp theo" value={formatDate(plan.next_due_date)} />
          <Detail label="Timezone" value={plan.local_timezone} />
          <Detail label="Checklist" value={plan.checklist_template_name ?? "Không áp dụng"} />
          <Detail label="Lead / grace" value={`${plan.lead_time_days} / ${plan.grace_period_days} ngày`} />
          <Detail label="Thời lượng" value={`${plan.estimated_duration_minutes} phút`} />
          <Detail label="Assignee mặc định" value={plan.default_assignee_name ?? "Chưa phân công"} />
          <Detail label="Ưu tiên" value={plan.default_priority_display} />
        </dl>
        {plan.description && <p className="mt-4 text-sm leading-6">{plan.description}</p>}
        {plan.instructions && <div className="mt-4 rounded-md bg-neutral-50 p-3"><p className="text-xs font-semibold text-muted-foreground">HƯỚNG DẪN THỰC THI</p><p className="mt-1 whitespace-pre-wrap text-sm">{plan.instructions}</p></div>}
      </section>

      {auth.can(permissions.maintenancePlansUpdate) && plan.status !== "archived" && <PlanScheduleEditor key={plan.version} plan={plan} />}

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div className="rounded-lg border bg-white p-4">
          <h2 className="font-semibold">Occurrence sắp tới</h2>
          <p className="mt-1 text-xs text-muted-foreground">Business date, preview có giới hạn 180 ngày.</p>
          <div className="mt-4 space-y-2">{occurrenceQuery.data?.items.length ? occurrenceQuery.data.items.map((occurrence) => <div key={occurrence.due_date} className="flex items-center justify-between gap-3 rounded-md border p-3 text-sm"><div><p className="font-medium">{formatDate(occurrence.due_date)}</p><p className="text-xs text-muted-foreground">Phát hành từ {formatDate(occurrence.generation_release_date)}</p></div><Badge variant={occurrence.generated ? "secondary" : "outline"}>{occurrence.generated ? "Đã tạo WO" : "Chưa tạo"}</Badge></div>) : <EmptyState title="Không có occurrence" description="Không có kỳ nào trong khoảng preview hiện tại." />}</div>
        </div>

        <div className="overflow-hidden rounded-lg border bg-white">
          <div className="p-4"><h2 className="font-semibold">Work order đã phát hành</h2><p className="mt-1 text-xs text-muted-foreground">Schedule change không sửa lại các work order lịch sử.</p></div>
          {workOrders.data?.items.length ? <div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead>Work order</TableHead><TableHead>Đến hạn</TableHead><TableHead>Ưu tiên</TableHead><TableHead>Trạng thái</TableHead></TableRow></TableHeader><TableBody>{workOrders.data.items.map((item) => <TableRow key={item.id}><TableCell><Link href={`/work-orders/${item.id}`} className="font-mono text-xs font-semibold text-primary hover:underline">{item.work_order_number}</Link><p className="mt-1 text-sm">{item.title}</p></TableCell><TableCell>{formatDate(item.due_date)}</TableCell><TableCell><CodePriorityBadge priority={item.priority} label={item.priority_display} /></TableCell><TableCell><WorkOrderStatusBadge status={item.status} label={item.status_display} /></TableCell></TableRow>)}</TableBody></Table></div> : <EmptyState title="Chưa phát hành work order" description="Dùng dry run để kiểm tra occurrence trước khi generate." />}
        </div>
      </section>

      <section className="rounded-lg border bg-white p-4">
        <h2 className="font-semibold">Dấu vết cấu hình</h2>
        <dl className="mt-3 grid gap-3 sm:grid-cols-3"><Detail label="Tạo lúc" value={formatTimestamp(plan.created_at)} /><Detail label="Cập nhật lúc" value={formatTimestamp(plan.updated_at)} /><Detail label="Occurrence gần nhất đã tạo" value={formatDate(plan.last_generated_due_date)} /></dl>
        <p className="mt-3 text-xs text-muted-foreground">Lịch sử mutation đầy đủ được ghi append-only trong Audit log theo quyền truy cập.</p>
      </section>
    </div>
  );
}

function PlanScheduleEditor({ plan }: { plan: MaintenancePlan }) {
  const mutation = useUpdateMaintenancePlan(plan.id);
  const options = useMaintenanceOptionsQuery();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ interval_value: String(plan.interval_value), interval_unit: plan.interval_unit as IntervalUnit, start_date: plan.start_date, end_date: plan.end_date ?? "", lead_time_days: String(plan.lead_time_days), grace_period_days: String(plan.grace_period_days), estimated_duration_minutes: String(plan.estimated_duration_minutes), default_priority: plan.default_priority as "low" | "medium" | "high" | "critical", instructions: plan.instructions ?? "" });

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const request: MaintenancePlanUpdateRequest = { expected_version: plan.version, interval_value: Number(form.interval_value), interval_unit: form.interval_unit, start_date: form.start_date, end_date: form.end_date || null, lead_time_days: Number(form.lead_time_days), grace_period_days: Number(form.grace_period_days), estimated_duration_minutes: Number(form.estimated_duration_minutes), default_priority: form.default_priority, instructions: form.instructions.trim() || null };
    try { await mutation.mutateAsync(request); setOpen(false); } catch { /* Render safe error. */ }
  }

  return <section className="rounded-lg border bg-white p-4"><div className="flex items-center justify-between gap-3"><div><h2 className="font-semibold">Cấu hình lịch</h2><p className="mt-1 text-xs text-muted-foreground">{recurrenceSummary(plan.interval_value, plan.interval_unit as IntervalUnit)}</p></div><Button type="button" variant="outline" onClick={() => setOpen((value) => !value)}>{open ? "Đóng" : "Chỉnh lịch"}</Button></div>{open && <form onSubmit={submit} className="mt-4 space-y-4 border-t pt-4"><div className="flex gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950"><TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />Thay đổi chỉ áp dụng cho occurrence chưa phát hành; work order lịch sử không bị viết lại.</div><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"><Field id="edit-interval" label="Chu kỳ"><Input id="edit-interval" type="number" min={1} max={366} value={form.interval_value} onChange={(event) => setForm({ ...form, interval_value: event.target.value })} /></Field><Field id="edit-unit" label="Đơn vị"><Select value={form.interval_unit} onValueChange={(value) => setForm({ ...form, interval_unit: value as IntervalUnit })}><SelectTrigger id="edit-unit" className="w-full"><SelectValue /></SelectTrigger><SelectContent>{options.data?.interval_units.map((option) => <SelectItem key={option.code} value={option.code}>{option.display_name}</SelectItem>)}</SelectContent></Select></Field><Field id="edit-start" label="Bắt đầu"><Input id="edit-start" type="date" value={form.start_date} onChange={(event) => setForm({ ...form, start_date: event.target.value })} /></Field><Field id="edit-end" label="Kết thúc"><Input id="edit-end" type="date" min={form.start_date} value={form.end_date} onChange={(event) => setForm({ ...form, end_date: event.target.value })} /></Field><Field id="edit-lead" label="Lead time"><Input id="edit-lead" type="number" min={0} value={form.lead_time_days} onChange={(event) => setForm({ ...form, lead_time_days: event.target.value })} /></Field><Field id="edit-grace" label="Grace period"><Input id="edit-grace" type="number" min={0} value={form.grace_period_days} onChange={(event) => setForm({ ...form, grace_period_days: event.target.value })} /></Field><Field id="edit-duration" label="Thời lượng (phút)"><Input id="edit-duration" type="number" min={1} value={form.estimated_duration_minutes} onChange={(event) => setForm({ ...form, estimated_duration_minutes: event.target.value })} /></Field><Field id="edit-priority" label="Ưu tiên"><Select value={form.default_priority} onValueChange={(value) => setForm({ ...form, default_priority: value as typeof form.default_priority })}><SelectTrigger id="edit-priority" className="w-full"><SelectValue /></SelectTrigger><SelectContent>{options.data?.priorities.map((option) => <SelectItem key={option.code} value={option.code}>{option.display_name}</SelectItem>)}</SelectContent></Select></Field></div><Field id="edit-instructions" label="Hướng dẫn"><Textarea id="edit-instructions" value={form.instructions} onChange={(event) => setForm({ ...form, instructions: event.target.value })} /></Field>{mutation.error && <div role="alert" className="flex items-center justify-between gap-2 rounded-md bg-red-50 p-3 text-sm text-red-800"><span>{getApiErrorMessage(mutation.error)}</span><Button type="button" variant="outline" size="sm" onClick={() => window.location.reload()}><RefreshCw aria-hidden="true" />Tải bản mới</Button></div>}<div className="flex justify-end"><Button type="submit" disabled={mutation.isPending}><Save aria-hidden="true" />Lưu cấu hình</Button></div></form>}</section>;
}

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) { return <div className="space-y-1.5"><Label htmlFor={id}>{label}</Label>{children}</div>; }
function Detail({ label, value }: { label: string; value: string }) { return <div><dt className="text-xs font-medium text-muted-foreground">{label}</dt><dd className="mt-1 text-sm font-medium">{value}</dd></div>; }
