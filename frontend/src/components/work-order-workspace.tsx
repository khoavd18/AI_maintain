"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { CalendarDays, ClipboardList, Filter, Plus, Search, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { PermissionDeniedNotice, useAuth } from "@/components/auth-provider";
import { CodePriorityBadge, WorkOrderStatusBadge } from "@/components/status-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState, ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import { useCreateWorkOrder } from "@/hooks/use-api-mutations";
import {
  useAssetCatalogQuery,
  useChecklistTemplatesQuery,
  useMaintenanceOptionsQuery,
  useWorkOrderMetricsQuery,
  useWorkOrdersQuery,
} from "@/hooks/use-api-queries";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { WorkOrderCreateRequest } from "@/lib/api/maintenance-schemas";
import { permissions } from "@/lib/auth";
import { formatDate } from "@/lib/formatters";
import { addDaysIso, todayIso } from "@/lib/maintenance";
import { resolveStatusPresentation, workOrderStatusCatalog } from "@/lib/status-terminology";

export function WorkOrderWorkspace() {
  const auth = useAuth();
  const [filters, setFilters] = useState({ search: "", status: "all", work_order_type: "all", assigned_to_user_id: "all", overdue: "all", due_from: "", due_to: "", asset_id: "", source_ticket_id: "", preventive_plan_id: "" });
  const [showCreate, setShowCreate] = useState(false);
  const queryFilters = {
    search: filters.search,
    status: filters.status === "all" ? undefined : filters.status,
    work_order_type: filters.work_order_type === "all" ? undefined : filters.work_order_type,
    assigned_to_user_id: filters.assigned_to_user_id === "all" ? undefined : filters.assigned_to_user_id,
    overdue: filters.overdue === "all" ? undefined : filters.overdue === "yes",
    due_from: filters.due_from,
    due_to: filters.due_to,
    asset_id: filters.asset_id,
    source_ticket_id: filters.source_ticket_id,
    preventive_plan_id: filters.preventive_plan_id,
    page_size: 200,
  };
  const workOrders = useWorkOrdersQuery(queryFilters);
  const options = useMaintenanceOptionsQuery();
  const metrics = useWorkOrderMetricsQuery(todayIso());
  const items = workOrders.data?.items ?? [];
  const error = workOrders.error ?? options.error;

  function resetFilters() {
    setFilters({ search: "", status: "all", work_order_type: "all", assigned_to_user_id: "all", overdue: "all", due_from: "", due_to: "", asset_id: "", source_ticket_id: "", preventive_plan_id: "" });
  }

  if (workOrders.isPending || options.isPending) return <LoadingSkeleton />;
  if (error) return <ErrorState title="Chưa tải được lệnh công việc" description={getApiErrorMessage(error)} action={<RetryButton onClick={() => void Promise.all([workOrders.refetch(), options.refetch()])} />} />;

  return (
    <div className="space-y-5">
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-label="Tóm tắt lệnh công việc">
        <Metric label="Tổng lệnh công việc" value={metrics.data?.total_work_orders} />
        <Metric label="Quá hạn" value={metrics.data?.overdue_count} tone={(metrics.data?.overdue_count ?? 0) > 0 ? "danger" : "normal"} />
        <Metric label="Bảo trì sắp tới" value={metrics.data?.upcoming_preventive_count} />
        <Metric label="Chờ xác nhận" value={metrics.data?.completed_count} />
        <Metric label="Đã xác nhận" value={metrics.data?.verified_count} />
      </section>

      <section className="rounded-lg border bg-white p-3 sm:p-4">
        <div className="mb-4 flex flex-wrap items-center justify-end gap-2">
          <Button asChild variant="outline"><Link href="/work-orders/calendar"><CalendarDays aria-hidden="true" />Lịch đến hạn</Link></Button>
          {auth.can(permissions.workOrdersCreate) && <Button type="button" onClick={() => setShowCreate((value) => !value)}><Plus aria-hidden="true" />{showCreate ? "Đóng biểu mẫu" : "Tạo lệnh công việc"}</Button>}
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <Field id="wo-search" label="Tìm lệnh công việc"><div className="relative"><Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" /><Input id="wo-search" className="pl-8" value={filters.search} onChange={(event) => setFilters({ ...filters, search: event.target.value })} placeholder="Mã lệnh, tiêu đề hoặc thiết bị" /></div></Field>
          <Field id="wo-status-filter" label="Trạng thái"><Select value={filters.status} onValueChange={(value) => setFilters({ ...filters, status: value })}><SelectTrigger id="wo-status-filter" className="w-full"><Filter aria-hidden="true" /><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Tất cả trạng thái</SelectItem>{options.data?.work_order_statuses.map((option) => <SelectItem key={option.code} value={option.code}>{resolveStatusPresentation(workOrderStatusCatalog, option.code, option.display_name).label}</SelectItem>)}</SelectContent></Select></Field>
          <Field id="wo-type-filter" label="Loại công việc"><Select value={filters.work_order_type} onValueChange={(value) => setFilters({ ...filters, work_order_type: value })}><SelectTrigger id="wo-type-filter" className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Tất cả loại</SelectItem>{options.data?.work_order_types.map((option) => <SelectItem key={option.code} value={option.code}>{option.display_name}</SelectItem>)}</SelectContent></Select></Field>
          <Field id="wo-technician-filter" label="Kỹ thuật viên"><Select value={filters.assigned_to_user_id} onValueChange={(value) => setFilters({ ...filters, assigned_to_user_id: value })}><SelectTrigger id="wo-technician-filter" className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Tất cả kỹ thuật viên</SelectItem>{options.data?.technicians.map((user) => <SelectItem key={user.id} value={user.id}>{user.display_name}</SelectItem>)}</SelectContent></Select></Field>
          <Field id="wo-overdue-filter" label="Quá hạn"><Select value={filters.overdue} onValueChange={(value) => setFilters({ ...filters, overdue: value })}><SelectTrigger id="wo-overdue-filter" className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Tất cả</SelectItem><SelectItem value="yes">Chỉ quá hạn</SelectItem><SelectItem value="no">Chưa quá hạn</SelectItem></SelectContent></Select></Field>
        </div>
        <details className="group mt-3 border-t pt-3">
          <summary className="w-fit cursor-pointer rounded-md text-sm font-medium text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Bộ lọc thêm</summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Field id="wo-due-from" label="Đến hạn từ"><Input id="wo-due-from" type="date" value={filters.due_from} onChange={(event) => setFilters({ ...filters, due_from: event.target.value })} /></Field>
          <Field id="wo-due-to" label="Đến hạn đến"><Input id="wo-due-to" type="date" min={filters.due_from || undefined} value={filters.due_to} onChange={(event) => setFilters({ ...filters, due_to: event.target.value })} /></Field>
          <Field id="wo-asset-filter" label="Mã thiết bị"><Input id="wo-asset-filter" value={filters.asset_id} onChange={(event) => setFilters({ ...filters, asset_id: event.target.value })} placeholder="GENERATOR_002" /></Field>
        </div>
        <div className="mt-3 flex flex-wrap items-end justify-between gap-3 border-t pt-3">
          <div className="grid flex-1 gap-3 sm:grid-cols-2 xl:max-w-2xl"><Field id="wo-ticket-filter" label="Phiếu sự cố liên quan"><Input id="wo-ticket-filter" value={filters.source_ticket_id} onChange={(event) => setFilters({ ...filters, source_ticket_id: event.target.value })} /></Field><Field id="wo-plan-filter" label="Kế hoạch định kỳ"><Input id="wo-plan-filter" value={filters.preventive_plan_id} onChange={(event) => setFilters({ ...filters, preventive_plan_id: event.target.value })} /></Field></div>
          <Button type="button" variant="ghost" onClick={resetFilters}>Đặt lại bộ lọc</Button>
        </div>
        </details>
        <p className="mt-3 text-xs text-muted-foreground">{workOrders.data?.total ?? 0} kết quả · công việc quá hạn được xác định từ ngày đến hạn và thời gian gia hạn.</p>
      </section>

      {showCreate && <WorkOrderCreateForm onCreated={() => setShowCreate(false)} />}
      {!auth.can(permissions.workOrdersCreate) && <PermissionDeniedNotice message="Vai trò hiện tại có thể xem lệnh công việc nhưng không được tạo mới." />}

      {!items.length ? (
        <div className="rounded-lg border bg-white">
          <EmptyState title="Không có lệnh công việc phù hợp" description="Điều chỉnh bộ lọc hoặc kiểm tra lịch bảo trì định kỳ." />
        </div>
      ) : (
        <>
          <div className="hidden overflow-hidden rounded-lg border bg-white lg:block">
            <Table className="table-fixed">
              <colgroup>
                <col className="w-[25%]" />
                <col className="w-[13%]" />
                <col className="w-[13%]" />
                <col className="w-[12%]" />
                <col className="w-[13%]" />
                <col className="w-[11%]" />
                <col className="w-[13%]" />
              </colgroup>
              <TableHeader><TableRow><TableHead>Lệnh công việc</TableHead><TableHead>Loại / nguồn</TableHead><TableHead>Thiết bị / vị trí</TableHead><TableHead>Kỹ thuật viên</TableHead><TableHead>Đến hạn</TableHead><TableHead>Ưu tiên</TableHead><TableHead>Trạng thái</TableHead></TableRow></TableHeader>
              <TableBody>{items.map((item) => <TableRow key={item.id}><TableCell className="min-w-0 whitespace-normal align-top"><Link className="whitespace-nowrap font-mono text-xs font-semibold text-primary hover:underline" href={`/work-orders/${item.id}`}>{item.work_order_number}</Link><p className="mt-1 line-clamp-2 break-words font-medium leading-5" title={item.title}>{item.title}</p></TableCell><TableCell className="min-w-0 whitespace-normal align-top"><p className="break-words leading-5">{item.work_order_type_display}</p><p className="break-words text-xs leading-5 text-muted-foreground">{item.preventive_plan_code ?? item.source_ticket_id ?? "Tạo thủ công"}</p></TableCell><TableCell className="min-w-0 whitespace-normal align-top"><p className="break-words font-mono text-xs leading-5">{item.asset_id}</p><p className="break-words text-xs leading-5 text-muted-foreground">{item.location ?? "Chưa có vị trí"}</p></TableCell><TableCell className="min-w-0 whitespace-normal align-top"><p className="break-words leading-5">{item.assigned_to_name ?? "Chưa phân công"}</p></TableCell><TableCell className="whitespace-nowrap align-top"><p>{formatDate(item.due_date)}</p>{item.is_overdue && <Badge className="mt-1 bg-red-50 text-red-700 ring-1 ring-red-200"><TriangleAlert aria-hidden="true" />Quá hạn</Badge>}</TableCell><TableCell className="whitespace-nowrap align-top"><CodePriorityBadge priority={item.priority} label={item.priority_display} /></TableCell><TableCell className="whitespace-nowrap align-top"><WorkOrderStatusBadge status={item.status} label={item.status_display} /></TableCell></TableRow>)}</TableBody>
            </Table>
          </div>
          <div className="grid gap-3 lg:hidden">{items.map((item) => <Link key={item.id} href={`/work-orders/${item.id}`} className="rounded-lg border bg-white p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><div className="flex items-start justify-between gap-2"><div><p className="font-mono text-xs font-semibold text-primary">{item.work_order_number}</p><h2 className="mt-1 font-semibold">{item.title}</h2></div><WorkOrderStatusBadge status={item.status} label={item.status_display} /></div><p className="mt-2 text-sm text-muted-foreground">{item.asset_id} · {item.location ?? "Chưa có vị trí"}</p><div className="mt-3 flex flex-wrap items-center gap-2"><CodePriorityBadge priority={item.priority} label={item.priority_display} /><Badge variant="outline">{item.work_order_type_display}</Badge>{item.is_overdue && <Badge className="bg-red-50 text-red-700 ring-1 ring-red-200">Quá hạn</Badge>}</div><p className="mt-3 text-sm">Đến hạn {formatDate(item.due_date)} · {item.assigned_to_name ?? "Chưa phân công"}</p></Link>)}</div>
        </>
      )}
      {metrics.data && <p className="text-xs text-muted-foreground">Số liệu phục vụ vận hành thử nội bộ.</p>}
    </div>
  );
}

function WorkOrderCreateForm({ onCreated }: { onCreated: (id: string) => void }) {
  const auth = useAuth();
  const router = useRouter();
  const assets = useAssetCatalogQuery({ lifecycle_status: "active", page_size: 100 });
  const templates = useChecklistTemplatesQuery({ status: "active", page_size: 200 }, auth.can(permissions.checklistTemplatesRead));
  const options = useMaintenanceOptionsQuery();
  const create = useCreateWorkOrder();
  const [form, setForm] = useState({ title: "", description: "", work_order_type: "inspection" as WorkOrderCreateRequest["work_order_type"], asset_id: "", assigned_to_user_id: "none", priority: "medium" as WorkOrderCreateRequest["priority"], due_date: addDaysIso(todayIso(), 7), local_timezone: "Asia/Ho_Chi_Minh", grace_period_days: "0", estimated_duration_minutes: "60", checklist_template_id: "none" });
  if (!auth.can(permissions.workOrdersCreate)) return null;
  if (assets.isPending || templates.isPending || options.isPending) return <LoadingSkeleton />;
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      const created = await create.mutateAsync({ title: form.title.trim(), description: form.description.trim() || null, work_order_type: form.work_order_type, asset_id: form.asset_id, preventive_plan_id: null, source_ticket_id: null, assigned_to_user_id: form.assigned_to_user_id === "none" ? null : form.assigned_to_user_id, priority: form.priority, scheduled_start_at: null, scheduled_end_at: null, due_date: form.due_date, local_timezone: form.local_timezone, grace_period_days: Number(form.grace_period_days), estimated_duration_minutes: Number(form.estimated_duration_minutes), checklist_template_id: form.checklist_template_id === "none" ? null : form.checklist_template_id });
      onCreated(created.id);
      router.push(`/work-orders/${created.id}`);
    } catch { /* Render safe error. */ }
  }
  return (
    <form onSubmit={submit} className="rounded-lg border bg-white p-4 sm:p-5">
      <div>
        <h2 className="font-semibold">Tạo lệnh công việc</h2>
        <p className="mt-1 text-xs text-muted-foreground">Nếu công việc xuất phát từ sự cố, hãy tạo từ trang chi tiết sự cố để hệ thống tự liên kết.</p>
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="md:col-span-2"><Field id="wo-title" label="Tiêu đề"><Input id="wo-title" required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></Field></div>
        <Field id="wo-asset" label="Thiết bị"><Select value={form.asset_id} onValueChange={(value) => setForm({ ...form, asset_id: value })}><SelectTrigger id="wo-asset" className="w-full"><SelectValue placeholder="Chọn thiết bị" /></SelectTrigger><SelectContent>{assets.data?.items.map((asset) => <SelectItem key={asset.asset_id} value={asset.asset_id}>{asset.asset_id} · {asset.asset_name}</SelectItem>)}</SelectContent></Select></Field>
        <Field id="wo-type" label="Loại công việc"><Select value={form.work_order_type} onValueChange={(value) => setForm({ ...form, work_order_type: value as WorkOrderCreateRequest["work_order_type"] })}><SelectTrigger id="wo-type" className="w-full"><SelectValue /></SelectTrigger><SelectContent>{options.data?.work_order_types.map((option) => <SelectItem key={option.code} value={option.code}>{option.display_name}</SelectItem>)}</SelectContent></Select></Field>
        <Field id="wo-priority" label="Mức ưu tiên"><Select value={form.priority} onValueChange={(value) => setForm({ ...form, priority: value as WorkOrderCreateRequest["priority"] })}><SelectTrigger id="wo-priority" className="w-full"><SelectValue /></SelectTrigger><SelectContent>{options.data?.priorities.map((option) => <SelectItem key={option.code} value={option.code}>{option.display_name}</SelectItem>)}</SelectContent></Select></Field>
        <Field id="wo-assignee" label="Kỹ thuật viên"><Select value={form.assigned_to_user_id} onValueChange={(value) => setForm({ ...form, assigned_to_user_id: value })}><SelectTrigger id="wo-assignee" className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">Chưa phân công</SelectItem>{options.data?.technicians.filter((user) => user.is_active).map((user) => <SelectItem key={user.id} value={user.id}>{user.display_name}</SelectItem>)}</SelectContent></Select></Field>
        <Field id="wo-due" label="Ngày đến hạn"><Input id="wo-due" required type="date" value={form.due_date} onChange={(event) => setForm({ ...form, due_date: event.target.value })} /></Field>
        <div className="md:col-span-2 xl:col-span-4"><Field id="wo-description" label="Mô tả"><Textarea id="wo-description" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></Field></div>
      </div>
      <details className="group mt-4 border-t pt-4">
        <summary className="w-fit cursor-pointer rounded-md text-sm font-medium text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Thiết lập bổ sung</summary>
        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Field id="wo-duration" label="Thời gian dự kiến (phút)"><Input id="wo-duration" required type="number" min={1} value={form.estimated_duration_minutes} onChange={(event) => setForm({ ...form, estimated_duration_minutes: event.target.value })} /></Field>
          <Field id="wo-grace" label="Thời gian gia hạn (ngày)"><Input id="wo-grace" required type="number" min={0} value={form.grace_period_days} onChange={(event) => setForm({ ...form, grace_period_days: event.target.value })} /></Field>
          <Field id="wo-timezone" label="Múi giờ"><Input id="wo-timezone" required value={form.local_timezone} onChange={(event) => setForm({ ...form, local_timezone: event.target.value })} /></Field>
          <Field id="wo-template" label="Danh sách kiểm tra"><Select value={form.checklist_template_id} onValueChange={(value) => setForm({ ...form, checklist_template_id: value })}><SelectTrigger id="wo-template" className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">Không dùng danh sách kiểm tra</SelectItem>{templates.data?.items.map((template) => <SelectItem key={template.id} value={template.id}>{template.name ?? template.code}</SelectItem>)}</SelectContent></Select></Field>
        </div>
      </details>
      {create.error && <p role="alert" className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-800">{getApiErrorMessage(create.error)}</p>}
      <div className="mt-4 flex justify-end"><Button type="submit" disabled={create.isPending || !form.asset_id}><ClipboardList aria-hidden="true" />{create.isPending ? "Đang tạo…" : "Tạo lệnh công việc"}</Button></div>
    </form>
  );
}

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) { return <div className="space-y-1.5"><Label htmlFor={id}>{label}</Label>{children}</div>; }
function Metric({ label, value, tone = "normal" }: { label: string; value: number | undefined; tone?: "normal" | "danger" }) { return <div className={`rounded-lg border bg-white p-4 ${tone === "danger" ? "border-red-200" : ""}`}><p className="text-xs font-medium text-muted-foreground">{label}</p><p className="mt-2 text-2xl font-semibold">{value ?? "—"}</p></div>; }
