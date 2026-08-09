"use client";

import { CheckCircle2, ClipboardCheck, Loader2 } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";

import { MutationError, RefreshWarning } from "@/components/ticket-create-sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { useCreateMaintenanceLog } from "@/hooks/use-api-mutations";
import { UserSafeApiError } from "@/lib/api/errors";
import { maintenanceLogCreateRequestSchema, type MaintenanceLogCreateRequest } from "@/lib/api/schemas";
import type { Asset, Ticket } from "@/lib/types";
import { addDays, latestDateOnly, maintenanceResults, todayInVietnam, zodFieldErrors } from "@/lib/workflow";

interface MaintenanceResultSheetProps {
  ticket: Ticket;
  asset: Asset;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved?: (logId: string) => void;
}

export function MaintenanceResultSheet(props: MaintenanceResultSheetProps) {
  return (
    <Sheet open={props.open} onOpenChange={props.onOpenChange}>
      <SheetContent className="w-full gap-0 p-0 data-[side=right]:w-full sm:max-w-xl">
        {props.open && <MaintenanceResultForm key={props.ticket.id} {...props} />}
      </SheetContent>
    </Sheet>
  );
}

function MaintenanceResultForm({ ticket, asset, onOpenChange, onSaved }: MaintenanceResultSheetProps) {
  const mutation = useCreateMaintenanceLog();
  const submittingRef = useRef(false);
  const today = todayInVietnam();
  const minimumDate = latestDateOnly(ticket.createdAtIso?.slice(0, 10), asset.lastMaintenanceDateIso);
  const initialDate = minimumDate > today ? minimumDate : today;
  const interval = asset.maintenanceIntervalDays ?? 0;
  const [form, setForm] = useState<MaintenanceLogCreateRequest>({
    ticket_id: ticket.id,
    asset_id: asset.id,
    maintenance_date: initialDate,
    inspection_result: "",
    actions_taken: "",
    parts_replaced: null,
    technician_note: "",
    maintenance_result: "Đã xử lý",
    follow_up_required: false,
    next_maintenance_date: interval > 0 ? addDays(initialDate, interval) : "",
  });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  function setMaintenanceDate(maintenance_date: string) {
    setForm({
      ...form,
      maintenance_date,
      next_maintenance_date: interval > 0 ? addDays(maintenance_date, interval) : "",
    });
  }

  function setResult(maintenance_result: MaintenanceLogCreateRequest["maintenance_result"]) {
    setForm({
      ...form,
      maintenance_result,
      follow_up_required: maintenance_result !== "Đã xử lý",
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mutation.isPending || submittingRef.current) return;
    const request = { ...form, parts_replaced: form.parts_replaced?.trim() || null };
    const parsed = maintenanceLogCreateRequestSchema.safeParse(request);
    if (!parsed.success) {
      setFieldErrors(zodFieldErrors(parsed.error.issues));
      return;
    }
    setFieldErrors({});
    submittingRef.current = true;
    try {
      const log = await mutation.mutateAsync(parsed.data);
      onSaved?.(log.log_id);
    } catch (error) {
      submittingRef.current = false;
      if (error instanceof UserSafeApiError) setFieldErrors(error.fieldErrors);
    }
  }

  const createdLog = mutation.data;
  const chronologyUnavailable = interval <= 0 || minimumDate > today;
  return (
    <>
      <SheetHeader className="border-b px-4 py-4 text-left sm:px-5">
        <SheetTitle>Ghi kết quả bảo trì</SheetTitle>
        <SheetDescription>{ticket.id} · {asset.id}. ID được khóa theo ticket đang chọn.</SheetDescription>
      </SheetHeader>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-5">
        <div className="grid gap-3 rounded-lg border bg-muted/30 p-3 text-sm sm:grid-cols-2">
          <Fact label="Kỹ thuật viên" value={ticket.technician} />
          <Fact label="Chu kỳ bảo trì" value={interval > 0 ? `${interval} ngày` : "Thiếu dữ liệu"} />
        </div>
        {createdLog && (
          <div role="status" className="mt-4 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-950">
            <p className="flex items-center gap-2 font-semibold"><CheckCircle2 className="size-4" aria-hidden="true" />Đã tạo maintenance log {createdLog.log_id}</p>
            <p className="mt-2 leading-5">Dữ liệu bảo trì đã được ghi nhận. Risk Score và KPI sẽ được cập nhật trong lần chạy analytics tiếp theo.</p>
          </div>
        )}
        {mutation.isError && <MutationError error={mutation.error} />}
        {mutation.refreshFailed && <RefreshWarning />}
        {chronologyUnavailable && <div role="alert" className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">Không thể xác định ngày hợp lệ từ dữ liệu thiết bị hiện tại. Hãy refresh asset trước khi ghi log.</div>}

        <form id="maintenance-result-form" onSubmit={handleSubmit} className="mt-5 space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="maintenance-date" label="Ngày bảo trì" error={fieldErrors.maintenance_date}><Input id="maintenance-date" type="date" min={minimumDate} max={today} value={form.maintenance_date} onChange={(event) => setMaintenanceDate(event.target.value)} /></Field>
            <Field id="next-maintenance-date" label="Ngày bảo trì kế tiếp" error={fieldErrors.next_maintenance_date}><Input id="next-maintenance-date" type="date" value={form.next_maintenance_date} readOnly /></Field>
          </div>
          <Field id="inspection-result" label="Kết quả kiểm tra" error={fieldErrors.inspection_result}><Textarea id="inspection-result" value={form.inspection_result} onChange={(event) => setForm({ ...form, inspection_result: event.target.value })} rows={3} /></Field>
          <Field id="actions-taken" label="Hành động đã thực hiện" error={fieldErrors.actions_taken}><Textarea id="actions-taken" value={form.actions_taken} onChange={(event) => setForm({ ...form, actions_taken: event.target.value })} rows={3} /></Field>
          <Field id="parts-replaced" label="Linh kiện đã thay (mô tả, không quản lý tồn kho)" error={fieldErrors.parts_replaced}><Input id="parts-replaced" value={form.parts_replaced ?? ""} onChange={(event) => setForm({ ...form, parts_replaced: event.target.value })} placeholder="Để trống nếu không thay" /></Field>
          <Field id="technician-note" label="Ghi chú kỹ thuật viên" error={fieldErrors.technician_note}><Textarea id="technician-note" value={form.technician_note} onChange={(event) => setForm({ ...form, technician_note: event.target.value })} rows={3} /></Field>
          <Field id="maintenance-result" label="Kết quả bảo trì" error={fieldErrors.maintenance_result}><Select value={form.maintenance_result} onValueChange={setResult}><SelectTrigger id="maintenance-result" className="w-full"><SelectValue /></SelectTrigger><SelectContent>{maintenanceResults.map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select></Field>
          <div className="rounded-lg border p-3 text-sm"><p className="font-medium">Theo dõi tiếp: {form.follow_up_required ? "Có" : "Không"}</p><p className="mt-1 text-xs text-muted-foreground">Tự động theo contract: mọi kết quả khác “Đã xử lý” đều cần theo dõi.</p>{fieldErrors.follow_up_required && <p role="alert" className="mt-1 text-xs text-destructive">{fieldErrors.follow_up_required}</p>}</div>
        </form>
      </div>
      <SheetFooter className="border-t bg-white p-4 sm:flex-row sm:justify-end">
        <Button type="button" variant="outline" disabled={mutation.isPending} onClick={() => onOpenChange(false)}>Đóng</Button>
        <Button type="submit" form="maintenance-result-form" disabled={mutation.isPending || Boolean(createdLog) || chronologyUnavailable}>
          {mutation.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <ClipboardCheck aria-hidden="true" />}
          {mutation.isPending ? "Đang lưu..." : createdLog ? "Đã ghi log" : "Ghi kết quả"}
        </Button>
      </SheetFooter>
    </>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 font-medium">{value}</p></div>;
}

function Field({ id, label, error, children }: { id: string; label: string; error?: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label htmlFor={id}>{label}</Label>{children}{error && <p role="alert" className="text-xs text-destructive">{error}</p>}</div>;
}
