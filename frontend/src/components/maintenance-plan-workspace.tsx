"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { CalendarClock, ChevronDown, Eye, Plus, Search, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";

import { PermissionDeniedNotice, useAuth } from "@/components/auth-provider";
import { PlanStatusBadge } from "@/components/status-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState, ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import {
  useCreateMaintenancePlan,
  useGenerateMaintenanceWorkOrders,
} from "@/hooks/use-api-mutations";
import {
  useAssetCatalogQuery,
  useChecklistTemplatesQuery,
  useMaintenanceOptionsQuery,
  useMaintenancePlansQuery,
} from "@/hooks/use-api-queries";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { GenerationRequest, MaintenancePlanCreateRequest } from "@/lib/api/maintenance-schemas";
import { permissions } from "@/lib/auth";
import { formatDate } from "@/lib/formatters";
import { addDaysIso, recurrenceSummary, todayIso, type IntervalUnit } from "@/lib/maintenance";

export function MaintenancePlanWorkspace() {
  const auth = useAuth();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const plans = useMaintenancePlansQuery({
    search,
    status: status === "all" ? undefined : status,
    page_size: 100,
  });
  const dryRun = useGenerateMaintenanceWorkOrders(true);
  const generate = useGenerateMaintenanceWorkOrders(false);
  const [generationMessage, setGenerationMessage] = useState<string | null>(null);
  const items = useMemo(() => plans.data?.items ?? [], [plans.data?.items]);
  const counts = useMemo(() => ({
    active: items.filter((plan) => plan.status === "active").length,
    paused: items.filter((plan) => plan.status === "paused").length,
    dueSoon: items.filter((plan) => {
      if (!plan.next_due_date || plan.status !== "active") return false;
      return plan.next_due_date <= addDaysIso(todayIso(), plan.lead_time_days);
    }).length,
  }), [items]);

  async function runGeneration(isDryRun: boolean) {
    const request: GenerationRequest = { as_of_date: todayIso(), plan_id: null };
    if (!isDryRun && !window.confirm("Tạo lệnh công việc đến ngày hôm nay cho tất cả kế hoạch đủ điều kiện?")) return;
    try {
      const result = await (isDryRun ? dryRun : generate).mutateAsync(request);
      const count = isDryRun ? result.would_generate_count : result.generated_count;
      setGenerationMessage(
        isDryRun
          ? `Xem trước: ${count} lệnh công việc sẽ được tạo; ${result.skipped_count} kỳ bảo trì được bỏ qua.`
          : `Đã tạo ${count} lệnh công việc; ${result.skipped_count} kỳ bảo trì được bỏ qua.`,
      );
    } catch (error) {
      setGenerationMessage(getApiErrorMessage(error));
    }
  }

  if (plans.isPending) return <LoadingSkeleton />;
  if (plans.isError) {
    return <ErrorState title="Chưa tải được kế hoạch bảo trì" description={getApiErrorMessage(plans.error)} action={<RetryButton onClick={() => void plans.refetch()} />} />;
  }

  return (
    <div className="space-y-5">
      <section aria-label="Tóm tắt kế hoạch" className="grid gap-3 sm:grid-cols-3">
        <PlanMetric label="Kế hoạch đang áp dụng" value={counts.active} />
        <PlanMetric label="Kế hoạch tạm dừng" value={counts.paused} />
        <PlanMetric label="Đến kỳ phát hành" value={counts.dueSoon} tone={counts.dueSoon ? "warning" : "normal"} />
      </section>

      <section className="rounded-lg border bg-white p-3 sm:p-4" aria-label="Bộ lọc kế hoạch">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
          <div className="grid flex-1 gap-3 sm:grid-cols-[minmax(240px,1fr)_220px]">
            <div className="space-y-1.5">
              <Label htmlFor="plan-search">Tìm kế hoạch</Label>
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
                <Input id="plan-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Mã kế hoạch, tên hoặc thiết bị" className="pl-8" />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="plan-status">Trạng thái</Label>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger id="plan-status" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Tất cả trạng thái</SelectItem>
                  <SelectItem value="active">Đang áp dụng</SelectItem>
                  <SelectItem value="paused">Tạm dừng</SelectItem>
                  <SelectItem value="archived">Đã lưu trữ</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {auth.can(permissions.maintenanceGenerationRun) && (
              <>
                <Button type="button" variant="outline" disabled={dryRun.isPending || generate.isPending} onClick={() => void runGeneration(true)}><Eye aria-hidden="true" />Xem trước</Button>
                <Button type="button" variant="outline" disabled={dryRun.isPending || generate.isPending} onClick={() => void runGeneration(false)}><Sparkles aria-hidden="true" />Tạo đến hạn</Button>
              </>
            )}
            {auth.can(permissions.maintenancePlansCreate) && <Button asChild><Link href="/maintenance/plans/new"><Plus aria-hidden="true" />Tạo kế hoạch</Link></Button>}
          </div>
        </div>
        {generationMessage && <p role="status" className="mt-3 rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-800">{generationMessage}</p>}
      </section>

      {!items.length ? (
        <div className="rounded-lg border bg-white"><EmptyState title="Chưa có kế hoạch phù hợp" description="Điều chỉnh bộ lọc hoặc tạo kế hoạch bảo trì đầu tiên." /></div>
      ) : (
        <>
          <div className="hidden overflow-hidden rounded-lg border bg-white md:block">
            <Table>
              <TableHeader><TableRow><TableHead>Kế hoạch / thiết bị</TableHead><TableHead>Chu kỳ</TableHead><TableHead>Kỳ tiếp theo</TableHead><TableHead>Người phụ trách</TableHead><TableHead>Trạng thái</TableHead><TableHead><span className="sr-only">Thao tác</span></TableHead></TableRow></TableHeader>
              <TableBody>{items.map((plan) => <TableRow key={plan.id}><TableCell><Link href={`/maintenance/plans/${plan.id}`} className="font-mono text-xs font-semibold text-primary hover:underline">{plan.plan_code}</Link><p className="mt-1 font-medium">{plan.name}</p><p className="text-xs text-muted-foreground">{plan.asset_id} · {plan.asset_name}</p></TableCell><TableCell>{plan.recurrence_summary}</TableCell><TableCell>{formatDate(plan.next_due_date)}</TableCell><TableCell>{plan.default_assignee_name ?? "Chưa phân công"}</TableCell><TableCell><PlanStatusBadge status={plan.status} label={plan.status_display} /></TableCell><TableCell className="text-right"><Button asChild variant="ghost" size="sm"><Link href={`/maintenance/plans/${plan.id}`}>Mở</Link></Button></TableCell></TableRow>)}</TableBody>
            </Table>
          </div>
          <div className="grid gap-3 md:hidden">
            {items.map((plan) => <Link key={plan.id} href={`/maintenance/plans/${plan.id}`} className="rounded-lg border bg-white p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><div className="flex items-start justify-between gap-2"><div><p className="font-mono text-xs font-semibold text-primary">{plan.plan_code}</p><h2 className="mt-1 font-semibold">{plan.name}</h2></div><PlanStatusBadge status={plan.status} label={plan.status_display} /></div><p className="mt-2 text-sm text-muted-foreground">{plan.asset_id} · {plan.asset_name}</p><div className="mt-3 flex items-center justify-between text-sm"><span>{plan.recurrence_summary}</span><span>{formatDate(plan.next_due_date)}</span></div></Link>)}
          </div>
        </>
      )}
      <p className="text-xs text-muted-foreground">Ngày đến hạn được tính theo múi giờ của từng kế hoạch. Lệnh công việc chỉ được tạo qua quy trình được ủy quyền.</p>
    </div>
  );
}

export function MaintenancePlanCreateForm() {
  const auth = useAuth();
  const router = useRouter();
  const assets = useAssetCatalogQuery({ lifecycle_status: "active", page_size: 100 });
  const templates = useChecklistTemplatesQuery({ status: "active", page_size: 200 }, auth.can(permissions.checklistTemplatesRead));
  const options = useMaintenanceOptionsQuery();
  const create = useCreateMaintenancePlan();
  const startDate = todayIso();
  const [form, setForm] = useState({
    plan_code: "",
    name: "",
    description: "",
    asset_id: "",
    interval_value: "1",
    interval_unit: "month" as IntervalUnit,
    start_date: startDate,
    end_date: "",
    local_timezone: "Asia/Ho_Chi_Minh",
    lead_time_days: "7",
    grace_period_days: "0",
    estimated_duration_minutes: "60",
    default_priority: "medium" as "low" | "medium" | "high" | "critical",
    default_assignee_user_id: "none",
    checklist_template_id: "none",
    instructions: "",
  });

  if (!auth.can(permissions.maintenancePlansCreate)) return <PermissionDeniedNotice message="Vai trò hiện tại không được tạo kế hoạch bảo trì." />;
  if (assets.isPending || templates.isPending || options.isPending) return <LoadingSkeleton />;
  const queryError = assets.error ?? templates.error ?? options.error;
  if (queryError) return <ErrorState title="Chưa tải được dữ liệu biểu mẫu" description={getApiErrorMessage(queryError)} />;

  function setField(name: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [name]: value }));
  }

  function revealAdvancedSettings(event: React.InvalidEvent<HTMLInputElement>) {
    event.currentTarget.closest("details")?.setAttribute("open", "");
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const request: MaintenancePlanCreateRequest = {
      plan_code: form.plan_code.trim().toUpperCase(),
      name: form.name.trim(),
      description: form.description.trim() || null,
      asset_id: form.asset_id,
      interval_value: Number(form.interval_value),
      interval_unit: form.interval_unit,
      start_date: form.start_date,
      end_date: form.end_date || null,
      local_timezone: form.local_timezone,
      lead_time_days: Number(form.lead_time_days),
      grace_period_days: Number(form.grace_period_days),
      estimated_duration_minutes: Number(form.estimated_duration_minutes),
      default_priority: form.default_priority,
      default_assignee_user_id: form.default_assignee_user_id === "none" ? null : form.default_assignee_user_id,
      checklist_template_id: form.checklist_template_id === "none" ? null : form.checklist_template_id,
      instructions: form.instructions.trim() || null,
      recurrence_rule: null,
    };
    try {
      const created = await create.mutateAsync(request);
      router.push(`/maintenance/plans/${created.id}`);
    } catch {
      // Mutation state presents the user-safe API error below.
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <section className="rounded-lg border bg-white p-4 sm:p-5">
        <h2 className="font-semibold">Thông tin kế hoạch</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Field label="Mã kế hoạch" id="plan-code"><Input id="plan-code" required value={form.plan_code} onChange={(event) => setField("plan_code", event.target.value)} placeholder="PM-GEN-001" /></Field>
          <Field label="Tên kế hoạch" id="plan-name"><Input id="plan-name" required value={form.name} onChange={(event) => setField("name", event.target.value)} /></Field>
          <Field label="Thiết bị" id="plan-asset"><Select value={form.asset_id} onValueChange={(value) => setField("asset_id", value)}><SelectTrigger id="plan-asset" className="w-full"><SelectValue placeholder="Chọn thiết bị đang hoạt động" /></SelectTrigger><SelectContent>{assets.data?.items.map((asset) => <SelectItem key={asset.asset_id} value={asset.asset_id}>{asset.asset_id} · {asset.asset_name}</SelectItem>)}</SelectContent></Select></Field>
          <div className="md:col-span-2"><Field label="Mô tả" id="plan-description"><Textarea id="plan-description" value={form.description} onChange={(event) => setField("description", event.target.value)} /></Field></div>
        </div>
      </section>

      <section className="rounded-lg border bg-white p-4 sm:p-5">
        <div className="flex items-center justify-between gap-3"><h2 className="font-semibold">Lịch định kỳ có kiểm soát</h2><Badge variant="outline"><CalendarClock aria-hidden="true" />{recurrenceSummary(Number(form.interval_value) || 1, form.interval_unit)}</Badge></div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Chu kỳ" id="plan-interval"><Input id="plan-interval" type="number" min={1} max={366} required value={form.interval_value} onChange={(event) => setField("interval_value", event.target.value)} /></Field>
          <Field label="Đơn vị" id="plan-unit"><Select value={form.interval_unit} onValueChange={(value) => setField("interval_unit", value)}><SelectTrigger id="plan-unit" className="w-full"><SelectValue /></SelectTrigger><SelectContent>{options.data?.interval_units.map((option) => <SelectItem key={option.code} value={option.code}>{option.display_name}</SelectItem>)}</SelectContent></Select></Field>
          <Field label="Ngày bắt đầu" id="plan-start"><Input id="plan-start" type="date" required value={form.start_date} onChange={(event) => setField("start_date", event.target.value)} /></Field>
          <Field label="Ngày kết thúc" id="plan-end"><Input id="plan-end" type="date" min={form.start_date} value={form.end_date} onChange={(event) => setField("end_date", event.target.value)} /></Field>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">Với ngày 29–31, hệ thống dùng ngày cuối tháng khi cần và vẫn giữ mốc ngày ban đầu cho kỳ sau.</p>
      </section>

      <details className="group rounded-lg border bg-white">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 rounded-lg p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:p-5 [&::-webkit-details-marker]:hidden">
          <span className="min-w-0">
            <span className="block font-semibold">Thiết lập nâng cao</span>
            <span className="mt-1 block text-xs font-normal text-muted-foreground">
              Phát hành trước {form.lead_time_days || "0"} ngày · gia hạn {form.grace_period_days || "0"} ngày · {form.estimated_duration_minutes || "0"} phút
            </span>
          </span>
          <ChevronDown className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" aria-hidden="true" />
        </summary>
        <div className="border-t p-4 sm:p-5">
          <p className="text-sm font-medium">Phát hành và thời gian thực hiện</p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Tạo trước hạn (ngày)" id="plan-lead"><Input id="plan-lead" type="number" min={0} max={365} required value={form.lead_time_days} onInvalid={revealAdvancedSettings} onChange={(event) => setField("lead_time_days", event.target.value)} /></Field>
            <Field label="Thời gian gia hạn (ngày)" id="plan-grace"><Input id="plan-grace" type="number" min={0} max={365} required value={form.grace_period_days} onInvalid={revealAdvancedSettings} onChange={(event) => setField("grace_period_days", event.target.value)} /></Field>
            <Field label="Thời lượng dự kiến (phút)" id="plan-duration"><Input id="plan-duration" type="number" min={1} max={10080} required value={form.estimated_duration_minutes} onInvalid={revealAdvancedSettings} onChange={(event) => setField("estimated_duration_minutes", event.target.value)} /></Field>
            <Field label="Múi giờ" id="plan-timezone"><Input id="plan-timezone" required value={form.local_timezone} onInvalid={revealAdvancedSettings} onChange={(event) => setField("local_timezone", event.target.value)} /></Field>
          </div>

          <div className="mt-5 border-t pt-5">
            <p className="font-medium">Mặc định thực thi</p>
            <p className="mt-1 text-xs text-muted-foreground">Có thể để nguyên các giá trị mặc định và phân công sau trên từng lệnh công việc.</p>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <Field label="Mức ưu tiên mặc định" id="plan-priority"><Select value={form.default_priority} onValueChange={(value) => setField("default_priority", value)}><SelectTrigger id="plan-priority" className="w-full"><SelectValue /></SelectTrigger><SelectContent>{options.data?.priorities.map((option) => <SelectItem key={option.code} value={option.code}>{option.display_name}</SelectItem>)}</SelectContent></Select></Field>
              <Field label="Kỹ thuật viên mặc định" id="plan-assignee"><Select value={form.default_assignee_user_id} onValueChange={(value) => setField("default_assignee_user_id", value)}><SelectTrigger id="plan-assignee" className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">Chưa phân công</SelectItem>{options.data?.technicians.filter((user) => user.is_active).map((user) => <SelectItem key={user.id} value={user.id}>{user.display_name} · {user.technician_id}</SelectItem>)}</SelectContent></Select></Field>
              <Field label="Mẫu kiểm tra" id="plan-template"><Select value={form.checklist_template_id} onValueChange={(value) => setField("checklist_template_id", value)}><SelectTrigger id="plan-template" className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">Không dùng mẫu kiểm tra</SelectItem>{templates.data?.items.map((template) => <SelectItem key={template.id} value={template.id}>{template.name}</SelectItem>)}</SelectContent></Select></Field>
              <div className="md:col-span-2"><Field label="Hướng dẫn" id="plan-instructions"><Textarea id="plan-instructions" value={form.instructions} onChange={(event) => setField("instructions", event.target.value)} /></Field></div>
            </div>
          </div>
        </div>
      </details>

      {create.error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{getApiErrorMessage(create.error)}</p>}
      <div className="flex flex-wrap justify-end gap-2"><Button asChild type="button" variant="outline"><Link href="/maintenance/plans">Hủy</Link></Button><Button type="submit" disabled={create.isPending || !form.asset_id}>{create.isPending ? "Đang tạo…" : "Tạo kế hoạch bảo trì"}</Button></div>
    </form>
  );
}

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label htmlFor={id}>{label}</Label>{children}</div>;
}

function PlanMetric({ label, value, tone = "normal" }: { label: string; value: number; tone?: "normal" | "warning" }) {
  return <div className={`rounded-lg border bg-white p-4 ${tone === "warning" ? "border-amber-200" : ""}`}><p className="text-xs font-medium text-muted-foreground">{label}</p><p className="mt-2 text-2xl font-semibold">{value}</p></div>;
}
