"use client";

import Link from "next/link";
import { AlertTriangle, CheckCircle2, Loader2, TicketPlus } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { MaintenanceBadge, RiskBadge } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { useCreateTicket } from "@/hooks/use-api-mutations";
import { getApiErrorMessage, UserSafeApiError } from "@/lib/api/errors";
import { permissions } from "@/lib/auth";
import { ticketCreateRequestSchema, type TicketCreateRequest } from "@/lib/api/schemas";
import type { Asset } from "@/lib/types";
import {
  suggestedFailureCategory,
  suggestedIssueDescription,
  suggestedPriority,
  ticketFailureCategories,
  ticketPriorities,
  zodFieldErrors,
} from "@/lib/workflow";

interface TicketCreateSheetProps {
  asset: Asset;
  latestAnomaly?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (ticketId: string) => void;
}

export function TicketCreateSheet(props: TicketCreateSheetProps) {
  return (
    <Sheet open={props.open} onOpenChange={props.onOpenChange}>
      <SheetContent className="w-full gap-0 p-0 data-[side=right]:w-full sm:max-w-xl">
        {props.open && <TicketCreateForm key={props.asset.id} {...props} />}
      </SheetContent>
    </Sheet>
  );
}

function TicketCreateForm({ asset, latestAnomaly, onOpenChange, onCreated }: TicketCreateSheetProps) {
  const auth = useAuth();
  const canAssign = auth.can(permissions.ticketsAssign);
  const mutation = useCreateTicket();
  const submittingRef = useRef(false);
  const [form, setForm] = useState<TicketCreateRequest>({
    asset_id: asset.id,
    issue_description: suggestedIssueDescription(asset, latestAnomaly),
    priority: suggestedPriority(asset),
    failure_category: suggestedFailureCategory(asset, latestAnomaly),
    technician_id: canAssign ? "" : "UNASSIGNED",
    manager_note: null,
  });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mutation.isPending || submittingRef.current) return;
    const request = { ...form, manager_note: form.manager_note?.trim() || null };
    const parsed = ticketCreateRequestSchema.safeParse(request);
    if (!parsed.success) {
      setFieldErrors(zodFieldErrors(parsed.error.issues));
      return;
    }
    setFieldErrors({});
    submittingRef.current = true;
    try {
      const ticket = await mutation.mutateAsync(parsed.data);
      onCreated?.(ticket.ticket_id);
    } catch (error) {
      submittingRef.current = false;
      if (error instanceof UserSafeApiError) setFieldErrors(error.fieldErrors);
    }
  }

  const createdTicket = mutation.data;
  return (
    <>
      <SheetHeader className="border-b px-4 py-4 text-left sm:px-5">
        <SheetTitle>Tạo ticket kiểm tra</SheetTitle>
        <SheetDescription>Ticket chỉ được ghi nhận sau khi FastAPI xác nhận thành công.</SheetDescription>
      </SheetHeader>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-5">
        <section aria-labelledby="ticket-facts" className="rounded-lg border border-orange-200 bg-orange-50 p-3">
          <h3 id="ticket-facts" className="flex items-center gap-2 text-xs font-semibold uppercase text-orange-900"><AlertTriangle className="size-4" aria-hidden="true" />Dữ liệu đo được</h3>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <Fact label="Thiết bị" value={asset.id} mono />
            <div><p className="text-xs text-orange-800">Risk</p><div className="mt-1 flex items-center gap-2"><strong>{asset.riskScore?.toFixed(2) ?? "--"}</strong>{asset.riskLevel && <RiskBadge level={asset.riskLevel} />}</div></div>
            <div><p className="text-xs text-orange-800">Bảo trì</p><div className="mt-1">{asset.maintenanceStatus ? <MaintenanceBadge status={asset.maintenanceStatus} /> : "Chưa có lịch"}</div></div>
          </div>
          <p className="mt-3 text-xs leading-5 text-orange-900">{asset.contributingFactors}</p>
          {latestAnomaly && <p className="mt-1 text-xs leading-5 text-orange-900">Anomaly: {latestAnomaly}</p>}
        </section>
        <section className="mt-3 rounded-lg border border-blue-200 bg-blue-50 p-3">
          <p className="text-xs font-semibold uppercase text-blue-900">Khuyến nghị hỗ trợ quyết định</p>
          <p className="mt-1 text-sm leading-5 text-blue-950">{asset.recommendedAction}</p>
        </section>

        {createdTicket && (
          <div role="status" className="mt-4 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-950">
            <p className="flex items-center gap-2 font-semibold"><CheckCircle2 className="size-4" aria-hidden="true" />Đã tạo ticket {createdTicket.ticket_id}</p>
            <Button asChild size="sm" className="mt-3"><Link href={`/tickets?ticket=${createdTicket.ticket_id}`}>Mở ticket vừa tạo</Link></Button>
          </div>
        )}
        {mutation.isError && <MutationError error={mutation.error} />}
        {mutation.refreshFailed && <RefreshWarning />}

        <form id="live-ticket-create-form" onSubmit={handleSubmit} className="mt-5 space-y-4">
          <Field id="create-ticket-asset" label="Asset ID" error={fieldErrors.asset_id}><Input id="create-ticket-asset" value={form.asset_id} readOnly /></Field>
          <Field id="create-ticket-description" label="Mô tả vấn đề" error={fieldErrors.issue_description}><Textarea id="create-ticket-description" value={form.issue_description} onChange={(event) => setForm({ ...form, issue_description: event.target.value })} rows={5} aria-invalid={Boolean(fieldErrors.issue_description)} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="create-ticket-priority" label="Mức ưu tiên" error={fieldErrors.priority}><Select value={form.priority} onValueChange={(priority: TicketCreateRequest["priority"]) => setForm({ ...form, priority })}><SelectTrigger id="create-ticket-priority" className="w-full"><SelectValue /></SelectTrigger><SelectContent>{ticketPriorities.map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select></Field>
            <Field id="create-ticket-category" label="Nhóm lỗi" error={fieldErrors.failure_category}><Select value={form.failure_category} onValueChange={(failure_category: TicketCreateRequest["failure_category"]) => setForm({ ...form, failure_category })}><SelectTrigger id="create-ticket-category" className="w-full"><SelectValue /></SelectTrigger><SelectContent>{ticketFailureCategories.map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select></Field>
          </div>
          {canAssign ? <Field id="create-ticket-technician" label="Mã kỹ thuật viên" error={fieldErrors.technician_id}><Input id="create-ticket-technician" value={form.technician_id} onChange={(event) => setForm({ ...form, technician_id: event.target.value })} placeholder="Ví dụ: TECH_003" aria-invalid={Boolean(fieldErrors.technician_id)} /></Field> : <div className="rounded-lg border bg-muted/40 p-3 text-sm"><p className="font-medium">Chưa phân công kỹ thuật viên</p><p className="mt-1 text-xs text-muted-foreground">Vai trò hiện tại có thể tạo ticket nhưng không có permission phân công.</p></div>}
          <Field id="create-ticket-manager-note" label="Ghi chú quản lý (không bắt buộc)" error={fieldErrors.manager_note}><Textarea id="create-ticket-manager-note" value={form.manager_note ?? ""} onChange={(event) => setForm({ ...form, manager_note: event.target.value })} rows={3} /></Field>
        </form>
      </div>
      <SheetFooter className="border-t bg-white p-4 sm:flex-row sm:justify-end">
        <Button type="button" variant="outline" disabled={mutation.isPending} onClick={() => onOpenChange(false)}>Đóng</Button>
        <Button type="submit" form="live-ticket-create-form" disabled={mutation.isPending || Boolean(createdTicket)}>
          {mutation.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <TicketPlus aria-hidden="true" />}
          {mutation.isPending ? "Đang gửi..." : createdTicket ? "Đã tạo ticket" : "Tạo ticket"}
        </Button>
      </SheetFooter>
    </>
  );
}

function Fact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div><p className="text-xs text-orange-800">{label}</p><p className={`mt-1 text-sm font-semibold ${mono ? "font-mono" : ""}`}>{value}</p></div>;
}

function Field({ id, label, error, children }: { id: string; label: string; error?: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label htmlFor={id}>{label}</Label>{children}{error && <p role="alert" className="text-xs text-destructive">{error}</p>}</div>;
}

export function MutationError({ error }: { error: unknown }) {
  const ambiguous = error instanceof UserSafeApiError && error.ambiguousWrite;
  return <div role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-950"><p className="font-semibold">{ambiguous ? "Chưa xác định trạng thái ghi" : "Chưa lưu được dữ liệu"}</p><p className="mt-1 leading-5">{getApiErrorMessage(error)}</p></div>;
}

export function RefreshWarning() {
  return <div role="alert" className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">Dữ liệu đã được ghi thành công, nhưng màn hình mới nhất chưa tải lại được. Không gửi lại; hãy kiểm tra kết nối rồi refresh trang.</div>;
}
