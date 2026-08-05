"use client";

import {
  CheckCircle2,
  Pause,
  Play,
  RefreshCw,
  Save,
  Wrench,
  XCircle,
} from "lucide-react";
import { useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { MaintenanceResultSheet } from "@/components/maintenance-result-sheet";
import { TicketOperationsPriorityBadge } from "@/components/ticket-operations-badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  useSlaPoliciesQuery,
  useTicketActionMutation,
  useTicketPriorityPreviewQuery,
  useTicketingOptionsQuery,
} from "@/hooks/use-ticketing";
import { adaptAssetDetails } from "@/lib/adapters";
import type { TicketActionCommand } from "@/lib/api/ticketing-endpoints";
import { getApiErrorMessage, UserSafeApiError } from "@/lib/api/errors";
import type {
  TicketDetail,
  TicketImpact,
  TicketUrgency,
} from "@/lib/api/ticketing-schemas";
import { permissions } from "@/lib/auth";
import { formatTimestamp } from "@/lib/formatters";
import type { Ticket, TicketPriority } from "@/lib/types";

const activeStatuses = new Set([
  "open",
  "assigned",
  "in_progress",
  "waiting",
  "reopened",
]);

export function TicketActionPanel({
  ticket,
  options,
  onRefresh,
  asset,
}: {
  ticket: TicketDetail;
  options: ReturnType<typeof useTicketingOptionsQuery>["data"];
  onRefresh: () => void;
  asset: ReturnType<typeof adaptAssetDetails> | null;
}) {
  const auth = useAuth();
  const action = useTicketActionMutation(ticket.ticket_id);
  const policies = useSlaPoliciesQuery(auth.can(permissions.slaPoliciesManage));
  const [assignee, setAssignee] = useState(ticket.assigned_user_id ?? "none");
  const [group, setGroup] = useState(ticket.support_group_id ?? "none");
  const [reasonMode, setReasonMode] = useState<"hold" | "reopen" | "cancel" | null>(null);
  const [reason, setReason] = useState("");
  const [impact, setImpact] = useState<TicketImpact>(ticket.impact);
  const [urgency, setUrgency] = useState<TicketUrgency>(ticket.urgency);
  const [priorityReason, setPriorityReason] = useState("");
  const [policyId, setPolicyId] = useState(ticket.sla?.policy_id ?? "none");
  const [policyReason, setPolicyReason] = useState("");
  const [maintenanceOpen, setMaintenanceOpen] = useState(false);
  const preview = useTicketPriorityPreviewQuery(impact, urgency);

  async function run(command: TicketActionCommand) {
    try {
      await action.mutateAsync(command);
      setReasonMode(null);
      setReason("");
    } catch {
      // The mutation error is rendered below with a safe backend message.
    }
  }

  const canExecute = auth.can(permissions.ticketsExecute);
  const canResolve = auth.can(permissions.ticketsResolve);
  const active = activeStatuses.has(ticket.status);
  const legacyTicket = toLegacyTicket(ticket);
  const showAdvanced =
    (auth.can(permissions.ticketsAssign) && active) ||
    (auth.can(permissions.ticketsUpdate) && active) ||
    (auth.can(permissions.slaPoliciesManage) && Boolean(ticket.sla));

  return (
    <aside className="space-y-4">
      <section className="rounded-lg border bg-white p-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">Hành động tiếp theo</h2>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {auth.can(permissions.ticketsAcknowledge) && active && !ticket.first_response_at && (
            <Button type="button" variant="outline" size="sm" disabled={action.isPending} onClick={() => void run({ action: "acknowledge", request: { expected_version: ticket.version } })}>
              <CheckCircle2 aria-hidden="true" />
              Ghi nhận phản hồi
            </Button>
          )}
          {canExecute && ["open", "assigned", "reopened"].includes(ticket.status) && (
            <Button type="button" size="sm" disabled={action.isPending} onClick={() => void run({ action: "start", request: { expected_version: ticket.version } })}>
              <Play aria-hidden="true" />
              Bắt đầu
            </Button>
          )}
          {canExecute && ["assigned", "in_progress"].includes(ticket.status) && (
            <Button type="button" variant="outline" size="sm" onClick={() => setReasonMode("hold")}>
              <Pause aria-hidden="true" />
              Đặt chờ
            </Button>
          )}
          {canExecute && ticket.status === "waiting" && (
            <Button type="button" size="sm" disabled={action.isPending} onClick={() => void run({ action: "resume", request: { expected_version: ticket.version } })}>
              <Play aria-hidden="true" />
              Tiếp tục
            </Button>
          )}
          {ticket.status === "in_progress" && auth.can(permissions.maintenanceLogsCreate) && asset && (
            <Button type="button" variant="outline" size="sm" onClick={() => setMaintenanceOpen(true)}>
              <Wrench aria-hidden="true" />
              Ghi kết quả bảo trì
            </Button>
          )}
          {ticket.status === "in_progress" && canResolve && (
            <Button type="button" size="sm" disabled={action.isPending} onClick={() => void run({ action: "resolve", request: { expected_version: ticket.version, resolved_at: null } })}>
              <CheckCircle2 aria-hidden="true" />
              Đánh dấu đã xử lý
            </Button>
          )}
          {ticket.status === "resolved" && auth.can(permissions.ticketsClose) && (
            <Button type="button" size="sm" disabled={action.isPending} onClick={() => void run({ action: "close", request: { expected_version: ticket.version } })}>
              <CheckCircle2 aria-hidden="true" />
              Đóng phiếu
            </Button>
          )}
          {["resolved", "closed"].includes(ticket.status) && auth.can(permissions.ticketsReopen) && (
            <Button type="button" variant="outline" size="sm" onClick={() => setReasonMode("reopen")}>
              <RefreshCw aria-hidden="true" />
              Mở lại
            </Button>
          )}
          {active && auth.can(permissions.ticketsCancel) && (
            <Button type="button" variant="destructive" size="sm" onClick={() => setReasonMode("cancel")}>
              <XCircle aria-hidden="true" />
              Hủy
            </Button>
          )}
        </div>

        {reasonMode && (
          <form
            className="mt-4 space-y-3 rounded-lg border bg-muted/30 p-3"
            onSubmit={(event) => {
              event.preventDefault();
              void run({ action: reasonMode, request: { expected_version: ticket.version, reason } });
            }}
          >
            <Label htmlFor="ticket-action-reason">
              {reasonMode === "hold" ? "Lý do đặt chờ" : reasonMode === "reopen" ? "Lý do mở lại" : "Lý do hủy phiếu"}
            </Label>
            <Textarea id="ticket-action-reason" value={reason} minLength={3} required onChange={(event) => setReason(event.target.value)} />
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" size="sm" onClick={() => setReasonMode(null)}>Bỏ qua</Button>
              <Button type="submit" size="sm" disabled={action.isPending}>
                {reasonMode === "hold" ? "Xác nhận đặt chờ" : reasonMode === "reopen" ? "Xác nhận mở lại" : "Xác nhận hủy phiếu"}
              </Button>
            </div>
          </form>
        )}

        {action.isError && <ActionError error={action.error} onRefresh={onRefresh} />}
      </section>

      {showAdvanced && (
        <details className="group rounded-lg border bg-white p-4">
          <summary className="cursor-pointer list-none rounded-md text-sm font-semibold text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            Điều phối và thiết lập bổ sung
          </summary>
          <div className="mt-4 space-y-4 border-t pt-4">
            {auth.can(permissions.ticketsAssign) && active && options && (
              <section className="rounded-lg border bg-white p-4">
                <h2 className="text-sm font-semibold">Phân công</h2>
                <div className="mt-3 space-y-3">
                  <Select value={assignee} onValueChange={setAssignee}>
                    <SelectTrigger aria-label="Người được phân công" className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">Chưa phân công</SelectItem>
                      {options.assignees.map((item) => <SelectItem key={item.id} value={item.id}>{item.display_name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <Select value={group} onValueChange={setGroup}>
                    <SelectTrigger aria-label="Support group" className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">Chưa có group</SelectItem>
                      {options.support_groups.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <Button type="button" variant="outline" size="sm" disabled={action.isPending} onClick={() => void run({ action: "assign", request: { expected_version: ticket.version, assigned_user_id: assignee === "none" ? null : assignee, support_group_id: group === "none" ? null : group } })}>
                    <Save aria-hidden="true" />
                    Lưu phân công
                  </Button>
                </div>
              </section>
            )}

            {auth.can(permissions.ticketsUpdate) && active && options && (
              <section className="rounded-lg border bg-white p-4">
                <h2 className="text-sm font-semibold">Điều chỉnh mức ưu tiên</h2>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <OptionSelect label="Mức ảnh hưởng" value={impact} items={options.impacts} onChange={(value) => setImpact(value as TicketImpact)} />
                  <OptionSelect label="Độ khẩn cấp" value={urgency} items={options.urgencies} onChange={(value) => setUrgency(value as TicketUrgency)} />
                </div>
                <div className="mt-3 flex items-center justify-between rounded-lg bg-muted/40 p-3">
                  <span className="text-xs text-muted-foreground">Mức ưu tiên mới</span>
                  {preview.data && <TicketOperationsPriorityBadge priority={preview.data.priority} label={preview.data.priority_display} />}
                </div>
                <Input className="mt-3" aria-label="Lý do đổi mức ưu tiên" placeholder="Lý do thay đổi" value={priorityReason} onChange={(event) => setPriorityReason(event.target.value)} />
                <Button type="button" variant="outline" size="sm" className="mt-3" disabled={action.isPending || priorityReason.trim().length < 3} onClick={() => void run({ action: "priority", request: { expected_version: ticket.version, impact, urgency, reason: priorityReason } })}>
                  Lưu mức ưu tiên
                </Button>
              </section>
            )}

            {auth.can(permissions.slaPoliciesManage) && ticket.sla && (
              <section className="rounded-lg border bg-white p-4">
                <h2 className="text-sm font-semibold">Đổi chính sách thời hạn</h2>
                <Select value={policyId} onValueChange={setPolicyId}>
                  <SelectTrigger aria-label="SLA policy" className="mt-3 w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Chọn policy</SelectItem>
                    {policies.data?.filter((item) => item.is_active).map((item) => <SelectItem key={item.id} value={item.id}>{item.code} · {item.name}</SelectItem>)}
                  </SelectContent>
                </Select>
                <Input className="mt-3" aria-label="Lý do đổi chính sách thời hạn" placeholder="Lý do thay đổi" value={policyReason} onChange={(event) => setPolicyReason(event.target.value)} />
                <Button type="button" variant="outline" size="sm" className="mt-3" disabled={action.isPending || policyId === "none" || policyReason.trim().length < 3} onClick={() => void run({ action: "sla-policy", request: { expected_version: ticket.version, policy_id: policyId, reason: policyReason } })}>
                  Áp dụng chính sách
                </Button>
              </section>
            )}
          </div>
        </details>
      )}

      {asset && ticket.status === "in_progress" && legacyTicket && (
        <MaintenanceResultSheet ticket={legacyTicket} asset={asset} open={maintenanceOpen} onOpenChange={setMaintenanceOpen} onSaved={onRefresh} />
      )}
    </aside>
  );
}

function OptionSelect({
  label,
  value,
  items,
  onChange,
}: {
  label: string;
  value: string;
  items: { code: string; display_name: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger aria-label={label} className="w-full"><SelectValue /></SelectTrigger>
        <SelectContent>{items.map((item) => <SelectItem key={item.code} value={item.code}>{item.display_name}</SelectItem>)}</SelectContent>
      </Select>
    </div>
  );
}

function ActionError({ error, onRefresh }: { error: unknown; onRefresh: () => void }) {
  const stale = error instanceof UserSafeApiError && error.code === "conflict";
  return (
    <div role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">
      <p>{getApiErrorMessage(error)}</p>
      {stale && (
        <Button type="button" variant="outline" size="sm" className="mt-3" onClick={onRefresh}>
          <RefreshCw aria-hidden="true" />
          Tải trạng thái mới
        </Button>
      )}
    </div>
  );
}

function toLegacyTicket(ticket: TicketDetail): Ticket | null {
  if (ticket.status !== "in_progress") return null;
  return {
    id: ticket.ticket_id,
    assetId: ticket.asset_id,
    summary: ticket.issue_description,
    description: ticket.issue_description,
    failureCategory: ticket.failure_category_display,
    priority: ticket.priority_display as TicketPriority,
    status: "in_progress",
    technician: ticket.technician_id,
    createdAt: formatTimestamp(ticket.created_at),
    createdAtIso: ticket.created_at,
    resolvedAtIso: ticket.resolved_at,
    updatedAt: formatTimestamp(ticket.updated_at),
    waitingTime: "",
    managerNote: ticket.manager_note,
    note: ticket.note,
  };
}
