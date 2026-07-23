"use client";

import Link from "next/link";
import { ArchiveRestore, CheckCircle2, Download, ExternalLink, FileUp, Pause, Play, RefreshCw, ShieldCheck, Trash2, TriangleAlert, UserRoundCheck, XCircle } from "lucide-react";
import { useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { CodePriorityBadge, WorkOrderStatusBadge } from "@/components/status-badges";
import { WorkOrderPartsPanel } from "@/components/work-order-parts-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState, ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import {
  useAssignWorkOrder,
  useCancelWorkOrder,
  useCompleteWorkOrder,
  useDeleteWorkOrderAttachment,
  useReopenWorkOrder,
  useTransitionWorkOrder,
  useUpdateWorkOrderChecklist,
  useUploadWorkOrderAttachment,
  useVerifyWorkOrder,
} from "@/hooks/use-api-mutations";
import {
  useMaintenanceOptionsQuery,
  useWorkOrderAttachmentsQuery,
  useWorkOrderQuery,
} from "@/hooks/use-api-queries";
import { maintenanceApi } from "@/lib/api/maintenance-endpoints";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { WorkOrder, WorkOrderChecklistUpdateRequest } from "@/lib/api/maintenance-schemas";
import { permissions } from "@/lib/auth";
import { formatDate, formatTimestamp } from "@/lib/formatters";
import { checklistValidationMessage, todayIso } from "@/lib/maintenance";
import { cn } from "@/lib/utils";

export function WorkOrderDetail({ workOrderId }: { workOrderId: string }) {
  const auth = useAuth();
  const workOrder = useWorkOrderQuery(workOrderId);
  const options = useMaintenanceOptionsQuery();
  const canReadEvidence = auth.can(permissions.workOrderAttachmentsRead);
  const attachments = useWorkOrderAttachmentsQuery(workOrderId, canReadEvidence);
  if (workOrder.isPending || options.isPending || (canReadEvidence && attachments.isPending)) return <LoadingSkeleton />;
  const error = workOrder.error ?? options.error ?? attachments.error;
  if (error || !workOrder.data || !options.data) return <ErrorState title="Chưa tải được work order" description={getApiErrorMessage(error)} action={<RetryButton onClick={() => void Promise.all([workOrder.refetch(), options.refetch(), attachments.refetch()])} />} />;

  const item = workOrder.data;
  return (
    <div className="space-y-5">
      <WorkOrderSummary workOrder={item} />
      <WorkOrderActions workOrder={item} technicians={options.data.technicians} onRefresh={() => void workOrder.refetch()} />
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(320px,0.6fr)]">
        <div className="space-y-5">
          <ChecklistExecution workOrder={item} />
          <WorkOrderPartsPanel workOrderId={item.id} />
          {item.status === "in_progress" && auth.can(permissions.workOrdersComplete) && <CompletionForm workOrder={item} />}
          {canReadEvidence && <EvidencePanel workOrder={item} attachments={attachments.data ?? []} />}
        </div>
        <div className="space-y-5">
          <ExecutionOutcome workOrder={item} />
          <WorkOrderTimeline workOrder={item} />
        </div>
      </div>
    </div>
  );
}

function WorkOrderSummary({ workOrder }: { workOrder: WorkOrder }) {
  return <section className="rounded-lg border bg-white p-4 sm:p-5"><div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start"><div><div className="flex flex-wrap items-center gap-2"><span className="font-mono text-sm font-semibold text-primary">{workOrder.work_order_number}</span><WorkOrderStatusBadge status={workOrder.status} label={workOrder.status_display} /><CodePriorityBadge priority={workOrder.priority} label={workOrder.priority_display} />{workOrder.is_overdue && <Badge className="bg-red-50 text-red-700 ring-1 ring-red-200"><TriangleAlert aria-hidden="true" />Quá hạn</Badge>}<Badge variant="outline">Version {workOrder.version}</Badge></div><h2 className="mt-2 text-xl font-semibold">{workOrder.title}</h2><p className="mt-1 text-sm text-muted-foreground">{workOrder.work_order_type_display}</p></div><div className="flex flex-wrap gap-2"><Button asChild variant="outline" size="sm"><Link href={`/assets/${workOrder.asset_id}`}>{workOrder.asset_id}<ExternalLink aria-hidden="true" /></Link></Button>{workOrder.source_ticket_id && <Button asChild variant="outline" size="sm"><Link href={`/tickets?ticket=${encodeURIComponent(workOrder.source_ticket_id)}`}>{workOrder.source_ticket_id}<ExternalLink aria-hidden="true" /></Link></Button>}{workOrder.preventive_plan_id && <Button asChild variant="outline" size="sm"><Link href={`/maintenance/plans/${workOrder.preventive_plan_id}`}>{workOrder.preventive_plan_code}<ExternalLink aria-hidden="true" /></Link></Button>}</div></div><dl className="mt-5 grid gap-4 border-t pt-4 sm:grid-cols-2 lg:grid-cols-4"><Detail label="Thiết bị" value={`${workOrder.asset_name} · ${workOrder.location ?? "Chưa có vị trí"}`} /><Detail label="Kỹ thuật viên" value={workOrder.assigned_to_name ?? "Chưa phân công"} /><Detail label="Đến hạn" value={`${formatDate(workOrder.due_date)} · grace ${workOrder.grace_period_days} ngày`} /><Detail label="Dự kiến" value={`${workOrder.estimated_duration_minutes} phút`} /><Detail label="Bắt đầu" value={formatTimestamp(workOrder.started_at)} /><Detail label="Hoàn tất" value={formatTimestamp(workOrder.completed_at)} /><Detail label="Xác minh" value={formatTimestamp(workOrder.verified_at)} /><Detail label="Maintenance log" value={workOrder.maintenance_log_id ?? "Chưa tạo"} /></dl>{workOrder.description && <p className="mt-4 whitespace-pre-wrap text-sm leading-6">{workOrder.description}</p>}</section>;
}

function WorkOrderActions({ workOrder, technicians, onRefresh }: { workOrder: WorkOrder; technicians: Array<{ id: string; display_name: string; technician_id: string; is_active: boolean }>; onRefresh: () => void }) {
  const auth = useAuth();
  const assign = useAssignWorkOrder(workOrder.id);
  const transition = useTransitionWorkOrder(workOrder.id);
  const verify = useVerifyWorkOrder(workOrder.id);
  const cancel = useCancelWorkOrder(workOrder.id);
  const reopen = useReopenWorkOrder(workOrder.id);
  const [assignee, setAssignee] = useState(workOrder.assigned_to_user_id ?? "none");
  const [message, setMessage] = useState<string | null>(null);
  const pending = assign.isPending || transition.isPending || verify.isPending || cancel.isPending || reopen.isPending;

  async function run(action: "assign" | "start" | "hold" | "resume" | "verify" | "cancel" | "reopen") {
    try {
      if (action === "assign") {
        if (assignee === "none") { setMessage("Hãy chọn một kỹ thuật viên đủ điều kiện."); return; }
        await assign.mutateAsync({ assigned_to_user_id: assignee, expected_version: workOrder.version });
      }
      if (action === "start") await transition.mutateAsync({ target_status: "in_progress", hold_reason: null, expected_version: workOrder.version });
      if (action === "hold") {
        const reason = window.prompt("Lý do tạm dừng:");
        if (!reason) return;
        await transition.mutateAsync({ target_status: "on_hold", hold_reason: reason, expected_version: workOrder.version });
      }
      if (action === "resume") await transition.mutateAsync({ target_status: workOrder.started_at ? "in_progress" : "assigned", hold_reason: null, expected_version: workOrder.version });
      if (action === "verify") {
        if (!window.confirm("Xác minh kết quả kỹ thuật và cập nhật ngày bảo trì thiết bị?")) return;
        await verify.mutateAsync(workOrder.version);
        setMessage("Đã xác minh. Maintenance log được giữ nguyên và ngày bảo trì thiết bị đã cập nhật theo transaction.");
      }
      if (action === "cancel") {
        const reason = window.prompt("Lý do hủy work order:");
        if (!reason) return;
        await cancel.mutateAsync({ cancellation_reason: reason, expected_version: workOrder.version });
      }
      if (action === "reopen") {
        const reason = window.prompt("Lý do mở lại work order đã hoàn tất:");
        if (!reason || !window.confirm("Mở lại work order này để kỹ thuật viên tiếp tục xử lý?")) return;
        await reopen.mutateAsync({ reason, expected_version: workOrder.version });
      }
      if (action !== "verify") setMessage("Đã cập nhật work order.");
    } catch (error) { setMessage(getApiErrorMessage(error)); }
  }

  const canCancel = auth.can(permissions.workOrdersCancel) && ["planned", "assigned", "on_hold"].includes(workOrder.status);
  return <section className="rounded-lg border bg-white p-4"><div className="flex flex-col gap-4 xl:flex-row xl:items-end"><div className="flex-1"><h2 className="font-semibold">Điều khiển workflow</h2><p className="mt-1 text-xs text-muted-foreground">Backend kiểm tra permission, ownership, transition và optimistic version.</p></div>{auth.can(permissions.workOrdersAssign) && ["planned", "assigned"].includes(workOrder.status) && <div className="flex min-w-0 flex-1 gap-2 sm:max-w-md"><Select value={assignee} onValueChange={setAssignee}><SelectTrigger aria-label="Kỹ thuật viên được giao" className="min-w-0 flex-1"><SelectValue placeholder="Chọn kỹ thuật viên" /></SelectTrigger><SelectContent><SelectItem value="none">Chưa phân công</SelectItem>{technicians.filter((user) => user.is_active).map((user) => <SelectItem key={user.id} value={user.id}>{user.display_name} · {user.technician_id}</SelectItem>)}</SelectContent></Select><Button type="button" variant="outline" disabled={pending || assignee === "none"} onClick={() => void run("assign")}><UserRoundCheck aria-hidden="true" />Giao việc</Button></div>}<div className="flex flex-wrap gap-2">{auth.can(permissions.workOrdersExecute) && workOrder.status === "assigned" && <Button type="button" disabled={pending} onClick={() => void run("start")}><Play aria-hidden="true" />Bắt đầu</Button>}{auth.can(permissions.workOrdersExecute) && workOrder.status === "in_progress" && <Button type="button" variant="outline" disabled={pending} onClick={() => void run("hold")}><Pause aria-hidden="true" />Tạm dừng</Button>}{auth.can(permissions.workOrdersExecute) && workOrder.status === "on_hold" && <Button type="button" disabled={pending} onClick={() => void run("resume")}><Play aria-hidden="true" />Tiếp tục</Button>}{auth.can(permissions.workOrdersVerify) && workOrder.status === "completed" && <Button type="button" disabled={pending} onClick={() => void run("verify")}><ShieldCheck aria-hidden="true" />Xác minh kỹ thuật</Button>}{auth.can(permissions.workOrdersReopen) && workOrder.status === "completed" && <Button type="button" variant="outline" disabled={pending} onClick={() => void run("reopen")}><ArchiveRestore aria-hidden="true" />Mở lại</Button>}{canCancel && <Button type="button" variant="outline" disabled={pending} onClick={() => void run("cancel")}><XCircle aria-hidden="true" />Hủy</Button>}</div></div>{message && <div role="status" className={cn("mt-3 flex items-center justify-between gap-2 rounded-md px-3 py-2 text-sm", message.startsWith("Đã") ? "bg-blue-50 text-blue-800" : "bg-red-50 text-red-800")}><span>{message}</span>{!message.startsWith("Đã") && <Button type="button" size="sm" variant="outline" onClick={onRefresh}><RefreshCw aria-hidden="true" />Tải trạng thái mới</Button>}</div>}</section>;
}

function ChecklistExecution({ workOrder }: { workOrder: WorkOrder }) {
  const auth = useAuth();
  const mutation = useUpdateWorkOrderChecklist(workOrder.id);
  const [message, setMessage] = useState<string | null>(null);
  const [responses, setResponses] = useState<WorkOrderChecklistUpdateRequest["responses"]>(() => workOrder.checklist.filter((item) => item.result_status !== "pending").map((item) => ({ item_id: item.id, result_status: item.result_status as "completed" | "pass" | "fail" | "not_applicable", boolean_value: item.boolean_value, numeric_value: item.numeric_value, text_value: item.text_value, note: item.note })));
  const canEdit = auth.can(permissions.workOrdersExecute) && ["in_progress", "on_hold"].includes(workOrder.status);
  const byId = useMemo(() => new Map(responses.map((response) => [response.item_id, response])), [responses]);
  function setResponse(itemId: string, updates: Partial<WorkOrderChecklistUpdateRequest["responses"][number]>) {
    setResponses((current) => {
      const existing = current.find((response) => response.item_id === itemId);
      const base = existing ?? { item_id: itemId, result_status: "completed" as const, boolean_value: null, numeric_value: null, text_value: null, note: null };
      return existing ? current.map((response) => response.item_id === itemId ? { ...response, ...updates } : response) : [...current, { ...base, ...updates }];
    });
  }
  async function save() {
    if (!responses.length) { setMessage("Chưa có phản hồi checklist để lưu."); return; }
    try { await mutation.mutateAsync({ expected_version: workOrder.version, responses }); setMessage("Đã lưu checklist trong transaction của work order."); } catch (error) { setMessage(getApiErrorMessage(error)); }
  }
  if (!workOrder.checklist.length) return <section className="rounded-lg border bg-white"><EmptyState title="Không có checklist" description="Work order này không gắn checklist template." /></section>;
  return <section className="rounded-lg border bg-white p-4 sm:p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold">Checklist thực thi</h2><p className="mt-1 text-xs text-muted-foreground">Các bước là snapshot tại thời điểm tạo work order.</p></div>{canEdit && <Button type="button" variant="outline" onClick={() => void save()} disabled={mutation.isPending}>Lưu checklist</Button>}</div><ol className="mt-4 space-y-3">{workOrder.checklist.map((item) => { const response = byId.get(item.id); return <li key={item.id} className={cn("rounded-md border p-3", item.safety_critical && "border-red-200 bg-red-50/40")}><div className="flex items-start gap-3"><span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-neutral-100 text-xs font-semibold">{item.sequence}</span><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><p className="font-medium">{item.instruction}</p>{item.is_required && <Badge variant="outline">Bắt buộc</Badge>}{item.safety_critical && <Badge className="bg-red-50 text-red-700 ring-1 ring-red-200"><TriangleAlert aria-hidden="true" />An toàn</Badge>}</div>{item.guidance && <p className="mt-1 text-sm text-muted-foreground">{item.guidance}</p>}<div className="mt-3 max-w-xl">{item.response_type === "checkbox" && <label className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={!canEdit} checked={response?.boolean_value ?? false} onChange={(event) => setResponse(item.id, { result_status: "completed", boolean_value: event.target.checked })} className="size-4" />Đã thực hiện</label>}{item.response_type === "pass_fail" && <Select disabled={!canEdit} value={response?.result_status ?? "pending"} onValueChange={(value) => setResponse(item.id, { result_status: value as "pass" | "fail" | "not_applicable" })}><SelectTrigger aria-label={`Kết quả bước ${item.sequence}`} className="w-full sm:w-64"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="pending">Chưa thực hiện</SelectItem><SelectItem value="pass">Đạt</SelectItem><SelectItem value="fail">Không đạt</SelectItem>{item.allow_not_applicable && <SelectItem value="not_applicable">Không áp dụng</SelectItem>}</SelectContent></Select>}{item.response_type === "numeric" && <div className="flex items-center gap-2"><Input aria-label={`Số đo bước ${item.sequence}`} disabled={!canEdit} type="number" min={item.minimum_value ?? undefined} max={item.maximum_value ?? undefined} value={response?.numeric_value ?? ""} onChange={(event) => setResponse(item.id, { result_status: "completed", numeric_value: event.target.value === "" ? null : Number(event.target.value) })} /><span className="shrink-0 text-sm text-muted-foreground">{item.expected_unit}</span></div>}{item.response_type === "text" && <Textarea aria-label={`Nội dung bước ${item.sequence}`} disabled={!canEdit} value={response?.text_value ?? ""} onChange={(event) => setResponse(item.id, { result_status: "completed", text_value: event.target.value })} />}</div>{response?.result_status === "fail" && item.safety_critical && <p className="mt-2 text-sm font-medium text-red-700">Không đạt bước an toàn; backend sẽ chặn hoàn tất.</p>}</div></div></li>; })}</ol>{message && <p role="status" className={cn("mt-4 rounded-md p-3 text-sm", message.startsWith("Đã") ? "bg-blue-50 text-blue-800" : "bg-red-50 text-red-800")}>{message}</p>}</section>;
}

function CompletionForm({ workOrder }: { workOrder: WorkOrder }) {
  const mutation = useCompleteWorkOrder(workOrder.id);
  const [form, setForm] = useState({ maintenance_date: todayIso(), inspection_result: "", actions_taken: "", parts_replaced: "", technician_note: "", maintenance_result: "resolved" as "resolved" | "partially_resolved" | "monitoring_required" | "vendor_required", follow_up_required: false, completion_summary: "", safety_notes: "", labor_minutes: "60" });
  const [clientError, setClientError] = useState<string | null>(null);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const currentResponses = workOrder.checklist.filter((item) => item.result_status !== "pending").map((item) => ({ item_id: item.id, result_status: item.result_status as "completed" | "pass" | "fail" | "not_applicable", boolean_value: item.boolean_value, numeric_value: item.numeric_value, text_value: item.text_value, note: item.note }));
    const validation = checklistValidationMessage(workOrder.checklist, currentResponses);
    if (validation) { setClientError(validation); return; }
    setClientError(null);
    try { await mutation.mutateAsync({ expected_version: workOrder.version, maintenance_date: form.maintenance_date, inspection_result: form.inspection_result.trim(), actions_taken: form.actions_taken.trim(), parts_replaced: form.parts_replaced.trim() || null, technician_note: form.technician_note.trim(), maintenance_result: form.maintenance_result, follow_up_required: form.follow_up_required, completion_summary: form.completion_summary.trim(), safety_notes: form.safety_notes.trim() || null, labor_minutes: Number(form.labor_minutes) }); } catch { /* Render safe error. */ }
  }
  if (mutation.isSuccess) return <section className="rounded-lg border border-green-200 bg-green-50 p-4 text-green-900"><div className="flex gap-3"><CheckCircle2 className="mt-0.5 size-5 shrink-0" aria-hidden="true" /><div><h2 className="font-semibold">Đã ghi nhận kết quả bảo trì</h2><p className="mt-1 text-sm">Maintenance log đã được tạo đúng một lần. Work order chờ người khác xác minh kỹ thuật.</p><p className="mt-2 text-xs">Risk Score và KPI analytics sẽ cập nhật ở batch tiếp theo; hệ thống không giả lập recalculation tức thời.</p></div></div></section>;
  return <form onSubmit={submit} className="rounded-lg border bg-white p-4 sm:p-5"><h2 className="font-semibold">Hoàn tất công việc</h2><p className="mt-1 text-xs text-muted-foreground">Thao tác này tạo đúng một MaintenanceLog; chưa cập nhật ngày bảo trì asset cho đến bước verify.</p><div className="mt-4 grid gap-4 sm:grid-cols-2"><Field id="completion-date" label="Ngày bảo trì"><Input id="completion-date" type="date" required max={todayIso()} value={form.maintenance_date} onChange={(event) => setForm({ ...form, maintenance_date: event.target.value })} /></Field><Field id="completion-result" label="Kết quả"><Select value={form.maintenance_result} onValueChange={(value) => setForm({ ...form, maintenance_result: value as typeof form.maintenance_result })}><SelectTrigger id="completion-result" className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="resolved">Đã xử lý</SelectItem><SelectItem value="partially_resolved">Xử lý một phần</SelectItem><SelectItem value="monitoring_required">Cần theo dõi</SelectItem><SelectItem value="vendor_required">Cần hỗ trợ bên ngoài</SelectItem></SelectContent></Select></Field><Field id="completion-inspection" label="Kết quả kiểm tra"><Textarea id="completion-inspection" required value={form.inspection_result} onChange={(event) => setForm({ ...form, inspection_result: event.target.value })} /></Field><Field id="completion-actions" label="Hành động đã thực hiện"><Textarea id="completion-actions" required value={form.actions_taken} onChange={(event) => setForm({ ...form, actions_taken: event.target.value })} /></Field><Field id="completion-parts" label="Vật tư đã thay (ghi nhận lịch sử)"><Textarea id="completion-parts" value={form.parts_replaced} onChange={(event) => setForm({ ...form, parts_replaced: event.target.value })} /></Field><Field id="completion-note" label="Ghi chú kỹ thuật viên"><Textarea id="completion-note" required value={form.technician_note} onChange={(event) => setForm({ ...form, technician_note: event.target.value })} /></Field><Field id="completion-summary" label="Tóm tắt hoàn tất"><Textarea id="completion-summary" required value={form.completion_summary} onChange={(event) => setForm({ ...form, completion_summary: event.target.value })} /></Field><Field id="completion-safety" label="Ghi chú an toàn"><Textarea id="completion-safety" value={form.safety_notes} onChange={(event) => setForm({ ...form, safety_notes: event.target.value })} /></Field><Field id="completion-labor" label="Thời gian thực tế (phút)"><Input id="completion-labor" type="number" min={0} max={10080} required value={form.labor_minutes} onChange={(event) => setForm({ ...form, labor_minutes: event.target.value })} /></Field><label className="flex items-center gap-2 self-end pb-2 text-sm"><input type="checkbox" checked={form.follow_up_required} onChange={(event) => setForm({ ...form, follow_up_required: event.target.checked })} className="size-4" />Cần theo dõi thêm</label></div>{(clientError || mutation.error) && <p role="alert" className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-800">{clientError ?? getApiErrorMessage(mutation.error)}</p>}<div className="mt-4 flex justify-end"><Button type="submit" disabled={mutation.isPending}><CheckCircle2 aria-hidden="true" />{mutation.isPending ? "Đang ghi…" : "Hoàn tất và tạo log"}</Button></div></form>;
}

function EvidencePanel({ workOrder, attachments }: { workOrder: WorkOrder; attachments: Array<{ id: string; original_filename: string; category: string; category_display: string; size_bytes: number; checksum: string; created_at: string }> }) {
  const auth = useAuth();
  const upload = useUploadWorkOrderAttachment(workOrder.id);
  const remove = useDeleteWorkOrderAttachment(workOrder.id);
  const [category, setCategory] = useState("before_photo");
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  async function uploadFile() { if (!file) return; try { await upload.mutateAsync({ category, file }); setFile(null); setMessage("Đã tải evidence và ghi checksum."); } catch (error) { setMessage(getApiErrorMessage(error)); } }
  async function downloadFile(attachmentId: string, filename: string) { try { const blob = await maintenanceApi.downloadAttachment(workOrder.id, attachmentId); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click(); URL.revokeObjectURL(url); } catch (error) { setMessage(getApiErrorMessage(error)); } }
  async function deleteFile(attachmentId: string) { if (!window.confirm("Xóa mềm evidence này? Metadata audit vẫn được giữ.")) return; try { await remove.mutateAsync(attachmentId); setMessage("Đã xóa mềm evidence."); } catch (error) { setMessage(getApiErrorMessage(error)); } }
  return <section className="rounded-lg border bg-white p-4 sm:p-5"><div><h2 className="font-semibold">Evidence đính kèm</h2><p className="mt-1 text-xs text-muted-foreground">Tải xuống được bảo vệ; nội dung file không ghi vào audit metadata.</p></div>{auth.can(permissions.workOrderAttachmentsCreate) && <div className="mt-4 grid gap-3 sm:grid-cols-[200px_minmax(0,1fr)_auto]"><Select value={category} onValueChange={setCategory}><SelectTrigger aria-label="Loại evidence" className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="before_photo">Ảnh trước bảo trì</SelectItem><SelectItem value="after_photo">Ảnh sau bảo trì</SelectItem><SelectItem value="inspection_document">Tài liệu kiểm tra</SelectItem><SelectItem value="completion_document">Biên bản hoàn tất</SelectItem><SelectItem value="safety_document">Tài liệu an toàn</SelectItem><SelectItem value="other">Khác</SelectItem></SelectContent></Select><Input aria-label="Chọn file evidence" type="file" accept="image/jpeg,image/png,application/pdf,text/plain" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /><Button type="button" variant="outline" disabled={!file || upload.isPending} onClick={() => void uploadFile()}><FileUp aria-hidden="true" />Tải lên</Button></div>}<div className="mt-4 space-y-2">{attachments.length ? attachments.map((attachment) => <div key={attachment.id} className="flex flex-col justify-between gap-3 rounded-md border p-3 sm:flex-row sm:items-center"><div className="min-w-0"><p className="truncate text-sm font-medium">{attachment.original_filename}</p><p className="mt-1 text-xs text-muted-foreground">{attachment.category_display} · {(attachment.size_bytes / 1024).toFixed(1)} KB · SHA-256 {attachment.checksum.slice(0, 10)}…</p></div><div className="flex gap-1"><Button type="button" variant="ghost" size="icon" title="Tải xuống" aria-label={`Tải ${attachment.original_filename}`} onClick={() => void downloadFile(attachment.id, attachment.original_filename)}><Download aria-hidden="true" /></Button>{auth.can(permissions.workOrderAttachmentsDelete) && <Button type="button" variant="ghost" size="icon" title="Xóa" aria-label={`Xóa ${attachment.original_filename}`} onClick={() => void deleteFile(attachment.id)}><Trash2 aria-hidden="true" /></Button>}</div></div>) : <EmptyState title="Chưa có evidence" description="Tải ảnh hoặc tài liệu kiểm tra khi cần." />}</div>{message && <p role="status" className="mt-3 rounded-md bg-blue-50 p-3 text-sm text-blue-800">{message}</p>}</section>;
}

function ExecutionOutcome({ workOrder }: { workOrder: WorkOrder }) {
  return <section className="rounded-lg border bg-white p-4"><h2 className="font-semibold">Kết quả thực thi</h2>{workOrder.completion_summary ? <dl className="mt-4 space-y-4"><Detail label="Tóm tắt" value={workOrder.completion_summary} /><Detail label="Ghi chú an toàn" value={workOrder.safety_notes ?? "Không có"} /><Detail label="Thời gian thực tế" value={workOrder.labor_minutes == null ? "Chưa có" : `${workOrder.labor_minutes} phút`} /><Detail label="Người xác minh" value={workOrder.verified_by_name ?? "Chưa xác minh"} /></dl> : <p className="mt-3 text-sm text-muted-foreground">Chưa có kết quả hoàn tất.</p>}{workOrder.source_ticket_id && <p className="mt-4 rounded-md bg-amber-50 p-3 text-xs text-amber-900">Hoàn tất hoặc xác minh work order không tự resolve ticket. Ticket chỉ thay đổi qua workflow được ủy quyền.</p>}</section>;
}

function WorkOrderTimeline({ workOrder }: { workOrder: WorkOrder }) {
  return <section className="rounded-lg border bg-white p-4"><h2 className="font-semibold">Timeline và audit</h2><div className="mt-4 space-y-4">{workOrder.history.length ? workOrder.history.map((event, index) => <div key={event.id} className="relative pl-5"><span className="absolute left-0 top-1.5 size-2 rounded-full bg-primary" aria-hidden="true" />{index < workOrder.history.length - 1 && <span className="absolute bottom-[-18px] left-[3px] top-4 w-px bg-border" aria-hidden="true" />}<p className="text-sm font-medium">{event.action}</p><p className="mt-0.5 text-xs text-muted-foreground">{formatTimestamp(event.occurred_at)} · {event.actor_display_name ?? "Hệ thống"}</p></div>) : <p className="text-sm text-muted-foreground">Chưa có event hiển thị.</p>}</div><p className="mt-4 border-t pt-3 text-xs text-muted-foreground">Audit record append-only; payload checklist và file body không được sao chép vào audit.</p></section>;
}

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) { return <div className="space-y-1.5"><Label htmlFor={id}>{label}</Label>{children}</div>; }
function Detail({ label, value }: { label: string; value: string }) { return <div><dt className="text-xs font-medium text-muted-foreground">{label}</dt><dd className="mt-1 whitespace-pre-wrap text-sm font-medium">{value}</dd></div>; }
