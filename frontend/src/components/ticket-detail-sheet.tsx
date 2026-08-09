"use client";

import Link from "next/link";
import { ArrowRight, Bot, CheckCircle2, ClipboardCheck, Loader2, Save, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { PermissionDeniedNotice, useAuth } from "@/components/auth-provider";
import { MaintenanceResultSheet } from "@/components/maintenance-result-sheet";
import { TicketWorkOrdersPanel } from "@/components/ticket-work-orders-panel";
import { MutationError, RefreshWarning } from "@/components/ticket-create-sheet";
import { PriorityBadge, RiskBadge, TicketStatusBadge } from "@/components/status-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { useUpdateTicket } from "@/hooks/use-api-mutations";
import { adaptTicket } from "@/lib/adapters";
import { permissions } from "@/lib/auth";
import type { TicketUpdateRequest } from "@/lib/api/schemas";
import type { Asset, MaintenanceEvent, Ticket } from "@/lib/types";
import { ticketPriorities } from "@/lib/workflow";

export interface RefreshedTicketState {
  ticket: Ticket | null;
  linkedLogCount: number;
}

export function TicketDetailSheet({
  ticket,
  asset,
  linkedLogs,
  onClose,
  onRefreshState,
  onWriteConfirmed,
}: {
  ticket: Ticket | null;
  asset?: Asset;
  linkedLogs: MaintenanceEvent[];
  onClose: () => void;
  onRefreshState: () => Promise<RefreshedTicketState>;
  onWriteConfirmed?: () => void;
}) {
  return (
    <Sheet open={Boolean(ticket)} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        {ticket && (
          <TicketDetailPanel
            key={`${ticket.id}-${ticket.status}-${ticket.updatedAt}`}
            ticket={ticket}
            asset={asset}
            linkedLogs={linkedLogs}
            onRefreshState={onRefreshState}
            onWriteConfirmed={onWriteConfirmed}
          />
        )}
      </SheetContent>
    </Sheet>
  );
}

function TicketDetailPanel({
  ticket,
  asset,
  linkedLogs,
  onRefreshState,
  onWriteConfirmed,
}: {
  ticket: Ticket;
  asset?: Asset;
  linkedLogs: MaintenanceEvent[];
  onRefreshState: () => Promise<RefreshedTicketState>;
  onWriteConfirmed?: () => void;
}) {
  const auth = useAuth();
  const mutation = useUpdateTicket(ticket.id);
  const [technician, setTechnician] = useState(ticket.technician);
  const [priority, setPriority] = useState(ticket.priority);
  const [note, setNote] = useState(ticket.note ?? "");
  const [maintenanceOpen, setMaintenanceOpen] = useState(false);
  const [maintenanceSaved, setMaintenanceSaved] = useState(false);
  const [confirmResolve, setConfirmResolve] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const current = mutation.data ? adaptTicket(mutation.data) : ticket;
  const hasMaintenanceLog = linkedLogs.length > 0 || maintenanceSaved;
  const latestLog = linkedLogs.at(0);
  const canUpdate = auth.can(permissions.ticketsUpdate);
  const canAssign = auth.can(permissions.ticketsAssign);
  const canCreateLog = auth.can(permissions.maintenanceLogsCreate);
  const scopedTechnician = canCreateLog && !canAssign;
  const assignedToCurrent =
    !scopedTechnician ||
    Boolean(auth.user?.technician_id && auth.user.technician_id === current.technician);
  const canEditCurrent = canUpdate && assignedToCurrent;
  const canEditPriority = canAssign || (canUpdate && !canCreateLog);
  const canStart = canAssign || (scopedTechnician && assignedToCurrent);
  const canAddLog = canCreateLog && assignedToCurrent;
  const canResolve = auth.can(permissions.ticketsResolve) && assignedToCurrent;

  async function updateTicket(request: TicketUpdateRequest) {
    setLocalError(null);
    try {
      await mutation.mutateAsync(request);
      onWriteConfirmed?.();
      return true;
    } catch {
      return false;
    }
  }

  async function saveAssignment() {
    const request: TicketUpdateRequest = { note: note.trim() || null };
    if (canAssign) request.technician_id = technician;
    if (canEditPriority) request.priority = priority;
    await updateTicket(request);
  }

  async function resolveTicket() {
    setVerifying(true);
    setLocalError(null);
    try {
      const refreshed = await onRefreshState();
      if (!refreshed.ticket) {
        setLocalError("Ticket không còn trong danh sách mới nhất. Hãy đóng và mở lại workspace.");
        return;
      }
      if (refreshed.ticket.status !== "in_progress") {
        setLocalError("Ticket không còn ở trạng thái Đang xử lý sau khi refresh.");
        return;
      }
      if (refreshed.linkedLogCount === 0) {
        setLocalError("Cần ghi ít nhất một maintenance log hợp lệ trước khi resolve ticket.");
        return;
      }
      const succeeded = await updateTicket({ status: "Đã xử lý" });
      if (succeeded) setConfirmResolve(false);
    } catch {
      setLocalError("Không refresh được ticket và maintenance log. Chưa gửi yêu cầu resolve.");
    } finally {
      setVerifying(false);
    }
  }

  return (
    <>
      <SheetHeader className="text-left">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="font-mono">{current.id}</Badge>
          <PriorityBadge priority={current.priority} />
          <TicketStatusBadge status={current.status} />
        </div>
        <SheetTitle>{current.summary}</SheetTitle>
        <SheetDescription>{current.assetId} · {current.failureCategory}</SheetDescription>
      </SheetHeader>

      <div className="space-y-5 px-4 pb-6">
        <section className="rounded-lg border bg-muted/30 p-3">
          <h3 className="text-sm font-semibold">Thông tin ticket</h3>
          <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
            <Fact label="Kỹ thuật viên" value={current.technician} />
            <Fact label="Thời gian chờ / xử lý" value={current.waitingTime} />
            <Fact label="Tạo lúc" value={current.createdAt} />
            <Fact label={current.status === "resolved" ? "Resolved at" : "Cập nhật"} value={current.updatedAt} />
          </dl>
          <p className="mt-4 text-sm leading-6 text-muted-foreground">{current.description}</p>
        </section>

        {asset && (
          <section className="rounded-lg border p-3">
            <div className="flex items-start justify-between gap-3">
              <div><h3 className="text-sm font-semibold">Thiết bị liên quan</h3><p className="mt-1 text-xs text-muted-foreground">{asset.name} · {asset.location}</p></div>
              {asset.riskLevel ? <RiskBadge level={asset.riskLevel} /> : <span className="text-xs text-muted-foreground">Chưa có risk</span>}
            </div>
            <p className="mt-3 text-sm text-muted-foreground">Risk {asset.riskScore == null ? "chưa có dữ liệu" : asset.riskScore.toFixed(2)} · {asset.maintenanceStatus ?? "chưa có lịch bảo trì"}</p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <Button asChild variant="outline" className="justify-between"><Link href={`/assets/${asset.id}`}>Mở hồ sơ thiết bị<ArrowRight aria-hidden="true" /></Link></Button>
              {auth.can(permissions.copilotUse) && <Button asChild variant="outline"><Link href={`/copilot?asset=${asset.id}&ticket=${current.id}`}><Bot aria-hidden="true" />Mở Copilot checklist</Link></Button>}
            </div>
          </section>
        )}

        {auth.can(permissions.workOrdersRead) && <TicketWorkOrdersPanel ticket={current} />}

        {mutation.isError && <MutationError error={mutation.error} />}
        {mutation.refreshFailed && <RefreshWarning />}
        {localError && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-950">{localError}</div>}
        {current.status === "resolved" && latestLog?.followUp && (
          <div className="flex gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            Ticket đã resolve nhưng maintenance result gần nhất vẫn yêu cầu theo dõi.
          </div>
        )}

        {current.status !== "resolved" && canEditCurrent ? (
          <section aria-labelledby="ticket-actions" className="space-y-4">
            <Separator />
            <h3 id="ticket-actions" className="text-sm font-semibold">Phân công và ưu tiên</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              {canAssign && <div className="space-y-1.5"><Label htmlFor="ticket-technician">Mã kỹ thuật viên</Label><Input id="ticket-technician" value={technician} onChange={(event) => setTechnician(event.target.value)} /></div>}
              {canEditPriority && <div className="space-y-1.5"><Label htmlFor="ticket-priority-edit">Mức ưu tiên</Label><Select value={priority} onValueChange={(value) => setPriority(value as typeof priority)}><SelectTrigger id="ticket-priority-edit" className="w-full"><SelectValue /></SelectTrigger><SelectContent>{ticketPriorities.map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select></div>}
            </div>
            <div className="space-y-1.5"><Label htmlFor="ticket-note">Ghi chú cập nhật</Label><Textarea id="ticket-note" value={note} onChange={(event) => setNote(event.target.value)} rows={2} /></div>
            <Button type="button" variant="outline" disabled={mutation.isPending || (canAssign && !technician.trim())} onClick={() => void saveAssignment()}>{mutation.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}{canAssign ? "Lưu phân công" : "Lưu cập nhật"}</Button>
          </section>
        ) : current.status === "resolved" ? (
          <div className="rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-950"><p className="flex items-center gap-2 font-semibold"><CheckCircle2 className="size-4" aria-hidden="true" />Ticket đã xử lý</p><p className="mt-1">Trạng thái vận hành chỉ đọc; API không hỗ trợ mở lại ticket.</p></div>
        ) : <PermissionDeniedNotice message={scopedTechnician && !assignedToCurrent ? "Ticket này không được phân công cho kỹ thuật viên đang đăng nhập." : "Vai trò hiện tại không có permission cập nhật ticket này."} />}

        {current.status === "new" && canStart && (
          <section className="rounded-lg border border-blue-200 bg-blue-50 p-3">
            <h3 className="text-sm font-semibold text-blue-950">Bắt đầu xử lý</h3>
            <p className="mt-1 text-xs text-blue-900">Xác nhận phân công trước khi kỹ thuật viên ghi kết quả hiện trường.</p>
            <Button type="button" className="mt-3" disabled={mutation.isPending || (canAssign && !technician.trim())} onClick={() => void updateTicket(canAssign ? { status: "Đang xử lý", technician_id: technician, priority } : { status: "Đang xử lý" })}>Chuyển sang Đang xử lý<ArrowRight aria-hidden="true" /></Button>
          </section>
        )}

        {current.status === "in_progress" && asset && (canAddLog || canResolve) && (
          <section className="space-y-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
            <div><h3 className="text-sm font-semibold text-amber-950">Kết quả hiện trường</h3><p className="mt-1 text-xs text-amber-900">Đã có {linkedLogs.length + (maintenanceSaved && linkedLogs.length === 0 ? 1 : 0)} maintenance log liên kết.</p></div>
            {latestLog?.followUp && <div className="flex gap-2 rounded-lg border border-amber-300 bg-white p-2 text-xs text-amber-950"><TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />Log mới nhất vẫn yêu cầu theo dõi sau bảo trì.</div>}
            <div className="flex flex-wrap gap-2">
              {canAddLog && <Button type="button" variant="outline" onClick={() => setMaintenanceOpen(true)}><ClipboardCheck aria-hidden="true" />Ghi kết quả bảo trì</Button>}
              {canResolve && <Button type="button" variant="destructive" onClick={() => setConfirmResolve(true)} disabled={mutation.isPending}>Resolve ticket</Button>}
            </div>
            {canResolve && confirmResolve && (
              <div role="alertdialog" aria-label="Xác nhận resolve ticket" className="rounded-lg border border-red-200 bg-white p-3">
                <p className="text-sm font-semibold">Xác nhận resolve {current.id}?</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">Hệ thống sẽ refresh ticket và log trước, sau đó gửi trạng thái “Đã xử lý”. Risk/KPI không được tính lại ngay.</p>
                {!hasMaintenanceLog && <p className="mt-2 text-xs font-medium text-red-700">Chưa thấy maintenance log trong màn hình hiện tại.</p>}
                <div className="mt-3 flex gap-2"><Button type="button" variant="outline" onClick={() => setConfirmResolve(false)}>Hủy</Button><Button type="button" variant="destructive" disabled={verifying || mutation.isPending} onClick={() => void resolveTicket()}>{verifying || mutation.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : null}Kiểm tra và resolve</Button></div>
              </div>
            )}
          </section>
        )}
      </div>

      {current.status === "in_progress" && asset && canAddLog && (
        <MaintenanceResultSheet
          ticket={current}
          asset={asset}
          open={maintenanceOpen}
          onOpenChange={setMaintenanceOpen}
          onSaved={() => {
            setMaintenanceSaved(true);
            onWriteConfirmed?.();
          }}
        />
      )}
    </>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 font-medium">{value}</dd></div>;
}
