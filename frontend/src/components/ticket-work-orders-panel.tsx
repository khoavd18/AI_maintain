"use client";

import Link from "next/link";
import { ClipboardPlus, ExternalLink } from "lucide-react";
import { useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { WorkOrderStatusBadge } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useCreateCorrectiveWorkOrder } from "@/hooks/use-api-mutations";
import { useChecklistTemplatesQuery, useMaintenanceOptionsQuery, useTicketWorkOrdersQuery } from "@/hooks/use-api-queries";
import { getApiErrorMessage } from "@/lib/api/errors";
import { permissions } from "@/lib/auth";
import { formatDate } from "@/lib/formatters";
import { addDaysIso, todayIso } from "@/lib/maintenance";
import type { Ticket } from "@/lib/types";

const priorityCodes = { "Thấp": "low", "Trung bình": "medium", "Cao": "high", "Khẩn cấp": "critical" } as const;

export function TicketWorkOrdersPanel({ ticket }: { ticket: Ticket }) {
  const auth = useAuth();
  const linked = useTicketWorkOrdersQuery(ticket.id);
  const options = useMaintenanceOptionsQuery(auth.can(permissions.workOrdersCreate));
  const templates = useChecklistTemplatesQuery({ status: "active", page_size: 100 }, auth.can(permissions.workOrdersCreate) && auth.can(permissions.checklistTemplatesRead));
  const create = useCreateCorrectiveWorkOrder(ticket.id);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ assigned_to_user_id: "none", due_date: addDaysIso(todayIso(), 3), estimated_duration_minutes: "90", checklist_template_id: "none" });

  if (linked.isPending) return <section className="rounded-lg border p-3 text-sm text-muted-foreground">Đang tải linked work order…</section>;
  if (linked.isError) return <section className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{getApiErrorMessage(linked.error)}</section>;
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      await create.mutateAsync({ title: `Xử lý ${ticket.id}: ${ticket.summary}`, description: ticket.description, assigned_to_user_id: form.assigned_to_user_id === "none" ? null : form.assigned_to_user_id, priority: priorityCodes[ticket.priority], scheduled_start_at: null, scheduled_end_at: null, due_date: form.due_date, local_timezone: "Asia/Ho_Chi_Minh", grace_period_days: 0, estimated_duration_minutes: Number(form.estimated_duration_minutes), checklist_template_id: form.checklist_template_id === "none" ? null : form.checklist_template_id });
      setShowForm(false);
    } catch { /* Render safe error. */ }
  }

  return <section className="rounded-lg border p-3"><div className="flex items-start justify-between gap-3"><div><h3 className="text-sm font-semibold">Corrective work order</h3><p className="mt-1 text-xs text-muted-foreground">Tạo WO không tự resolve ticket; asset linkage được backend kiểm tra.</p></div>{auth.can(permissions.workOrdersCreate) && ticket.status !== "resolved" && <Button type="button" variant="outline" size="sm" onClick={() => setShowForm((value) => !value)}><ClipboardPlus aria-hidden="true" />{showForm ? "Đóng" : "Tạo WO"}</Button>}</div>{linked.data?.length ? <div className="mt-3 space-y-2">{linked.data.map((workOrder) => <Link key={workOrder.id} href={`/work-orders/${workOrder.id}`} className="flex items-center justify-between gap-3 rounded-md bg-muted/50 p-3 hover:bg-muted"><div className="min-w-0"><p className="truncate font-mono text-xs font-semibold text-primary">{workOrder.work_order_number}</p><p className="mt-1 truncate text-sm">{workOrder.title}</p><p className="mt-1 text-xs text-muted-foreground">Đến hạn {formatDate(workOrder.due_date)}</p></div><div className="flex shrink-0 items-center gap-2"><WorkOrderStatusBadge status={workOrder.status} label={workOrder.status_display} /><ExternalLink className="size-4 text-muted-foreground" aria-hidden="true" /></div></Link>)}</div> : <p className="mt-3 text-sm text-muted-foreground">Ticket chưa có linked work order.</p>}{showForm && <form onSubmit={submit} className="mt-4 space-y-3 border-t pt-4"><div className="grid gap-3 sm:grid-cols-2"><Field id="corrective-assignee" label="Kỹ thuật viên"><Select value={form.assigned_to_user_id} onValueChange={(value) => setForm({ ...form, assigned_to_user_id: value })}><SelectTrigger id="corrective-assignee" className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">Chưa phân công</SelectItem>{options.data?.technicians.filter((user) => user.is_active).map((user) => <SelectItem key={user.id} value={user.id}>{user.display_name}</SelectItem>)}</SelectContent></Select></Field><Field id="corrective-due" label="Ngày đến hạn"><Input id="corrective-due" type="date" required min={todayIso()} value={form.due_date} onChange={(event) => setForm({ ...form, due_date: event.target.value })} /></Field><Field id="corrective-duration" label="Thời lượng dự kiến"><Input id="corrective-duration" type="number" min={1} required value={form.estimated_duration_minutes} onChange={(event) => setForm({ ...form, estimated_duration_minutes: event.target.value })} /></Field><Field id="corrective-template" label="Checklist"><Select value={form.checklist_template_id} onValueChange={(value) => setForm({ ...form, checklist_template_id: value })}><SelectTrigger id="corrective-template" className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">Không dùng checklist</SelectItem>{templates.data?.items.map((template) => <SelectItem key={template.id} value={template.id}>{template.code} v{template.version_number}</SelectItem>)}</SelectContent></Select></Field></div>{create.error && <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-800">{getApiErrorMessage(create.error)}</p>}<div className="flex justify-end"><Button type="submit" disabled={create.isPending}>{create.isPending ? "Đang tạo…" : "Tạo corrective work order"}</Button></div></form>}</section>;
}

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) { return <div className="space-y-1.5"><Label htmlFor={id}>{label}</Label>{children}</div>; }
