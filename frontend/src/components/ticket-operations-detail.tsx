"use client";

import Link from "next/link";
import {
  Bot,
  CheckCircle2,
  Loader2,
  MessageSquarePlus,
  Pause,
  Play,
  RefreshCw,
  Save,
  Send,
  Wrench,
  XCircle,
} from "lucide-react";
import { type FormEvent, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { MaintenanceResultSheet } from "@/components/maintenance-result-sheet";
import {
  SlaStatusBadge,
  TicketOperationsPriorityBadge,
  TicketOperationsStatusBadge,
} from "@/components/ticket-operations-badges";
import { TicketWorkOrdersPanel } from "@/components/ticket-work-orders-panel";
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
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import { useAssetDetailsQuery } from "@/hooks/use-api-queries";
import {
  useSlaPoliciesQuery,
  useTicketActionMutation,
  useTicketCommentMutation,
  useTicketDetailQuery,
  useTicketingOptionsQuery,
  useTicketPriorityPreviewQuery,
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

const activeStatuses = new Set(["open", "assigned", "in_progress", "waiting", "reopened"]);

export function TicketOperationsDetail({ ticketId }: { ticketId: string }) {
  const ticket = useTicketDetailQuery(ticketId);
  const options = useTicketingOptionsQuery();
  const assetDetails = useAssetDetailsQuery(ticket.data?.asset_id ?? "", 10);

  if (ticket.isPending || options.isPending) return <LoadingSkeleton />;
  if (ticket.isError || options.isError) {
    return (
      <ErrorState
        title="Chưa tải được ticket"
        description={getApiErrorMessage(ticket.error ?? options.error)}
        action={
          <RetryButton
            onClick={() => {
              void ticket.refetch();
              void options.refetch();
            }}
          />
        }
      />
    );
  }

  const asset = assetDetails.data ? adaptAssetDetails(assetDetails.data) : null;
  return (
    <div className="space-y-5">
      <TicketSummary ticket={ticket.data} />

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Tổng quan</TabsTrigger>
          <TabsTrigger value="communication">
            Trao đổi ({ticket.data.comments.length})
          </TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4 space-y-5">
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
            <div className="space-y-5">
              <TicketFacts ticket={ticket.data} />
              <TicketWorkOrdersPanel
                ticket={{
                  id: ticket.data.ticket_id,
                  assetId: ticket.data.asset_id,
                  summary: ticket.data.issue_description,
                  description: ticket.data.issue_description,
                  priority: ticket.data.priority_display as TicketPriority,
                  priorityCode: ticket.data.priority,
                  status: ticket.data.status,
                }}
              />
            </div>
            <TicketActionPanel
              key={`${ticket.data.ticket_id}-${ticket.data.version}`}
              ticket={ticket.data}
              options={options.data}
              onRefresh={() => void ticket.refetch()}
              asset={asset}
            />
          </div>
        </TabsContent>

        <TabsContent value="communication" className="mt-4">
          <TicketCommunication
            key={`${ticket.data.ticket_id}-${ticket.data.comments.length}`}
            ticket={ticket.data}
          />
        </TabsContent>

        <TabsContent value="timeline" className="mt-4">
          <TicketTimeline ticket={ticket.data} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function TicketSummary({ ticket }: { ticket: TicketDetail }) {
  const auth = useAuth();
  return (
    <section className="rounded-lg border bg-white p-4 sm:p-5">
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs font-semibold text-primary">
              {ticket.ticket_id}
            </span>
            <TicketOperationsStatusBadge
              status={ticket.status}
              label={ticket.status_display}
            />
            <TicketOperationsPriorityBadge
              priority={ticket.priority}
              label={ticket.priority_display}
            />
          </div>
          <h2 className="mt-3 text-lg font-semibold">{ticket.issue_description}</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {ticket.asset_id} · {ticket.category_name ?? "Chưa phân loại"} ·{" "}
            {ticket.failure_category_display}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href={`/assets/${ticket.asset_id}`}>
              <Wrench aria-hidden="true" />
              Hồ sơ thiết bị
            </Link>
          </Button>
          {auth.can(permissions.copilotUse) && (
            <Button asChild variant="outline" size="sm">
              <Link
                href={`/copilot?asset=${encodeURIComponent(ticket.asset_id)}&ticket=${encodeURIComponent(ticket.ticket_id)}`}
              >
                <Bot aria-hidden="true" />
                Copilot checklist
              </Link>
            </Button>
          )}
        </div>
      </div>
    </section>
  );
}

function TicketFacts({ ticket }: { ticket: TicketDetail }) {
  return (
    <section className="rounded-lg border bg-white p-4 sm:p-5">
      <h2 className="text-sm font-semibold">Thông tin ticket</h2>
      <dl className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Fact label="Impact" value={ticket.impact_display} />
        <Fact label="Urgency" value={ticket.urgency_display} />
        <Fact label="Subcategory" value={ticket.subcategory_name ?? "Chưa chọn"} />
        <Fact
          label="Support group"
          value={ticket.support_group_name ?? "Chưa phân nhóm"}
        />
        <Fact
          label="Người phụ trách"
          value={ticket.assigned_user_name ?? "Chưa phân công"}
        />
        <Fact label="Nguồn tiếp nhận" value={ticket.intake_source_name ?? "Chưa ghi"} />
        <Fact label="Tạo lúc" value={formatTimestamp(ticket.created_at)} />
        <Fact
          label="First response"
          value={formatTimestamp(ticket.first_response_at)}
        />
        <Fact label="Reopen" value={`${ticket.reopen_count} lần`} />
      </dl>

      <Separator className="my-5" />
      <div className="grid gap-5 lg:grid-cols-2">
        <ReporterFacts ticket={ticket} />
        <SlaFacts ticket={ticket} />
      </div>

      {ticket.waiting_reason && (
        <div className="mt-4 rounded-lg border border-orange-200 bg-orange-50 p-3 text-sm text-orange-950">
          <strong>Lý do chờ:</strong> {ticket.waiting_reason}
        </div>
      )}
      {ticket.manager_note && (
        <div className="mt-4 rounded-lg border bg-muted/30 p-3 text-sm">
          <strong>Ghi chú quản lý:</strong> {ticket.manager_note}
        </div>
      )}
    </section>
  );
}

function ReporterFacts({ ticket }: { ticket: TicketDetail }) {
  return (
    <section aria-labelledby="reporter-heading">
      <div className="flex items-center gap-2">
        <h3 id="reporter-heading" className="text-sm font-semibold">
          Người báo sự cố
        </h3>
        {ticket.reporter_redacted && (
          <span className="rounded bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600">
            Đã ẩn theo quyền
          </span>
        )}
      </div>
      <dl className="mt-3 space-y-3">
        <Fact label="Họ tên" value={ticket.reporter_name ?? "Không hiển thị"} />
        <Fact label="Email" value={ticket.reporter_email ?? "Không hiển thị"} />
        <Fact label="Điện thoại" value={ticket.reporter_phone ?? "Không hiển thị"} />
      </dl>
    </section>
  );
}

function SlaFacts({ ticket }: { ticket: TicketDetail }) {
  if (!ticket.sla) {
    return (
      <section aria-labelledby="sla-heading">
        <h3 id="sla-heading" className="text-sm font-semibold">
          SLA
        </h3>
        <p className="mt-3 text-sm text-muted-foreground">
          Ticket chưa có SLA snapshot.
        </p>
      </section>
    );
  }
  return (
    <section aria-labelledby="sla-heading">
      <div className="flex items-center justify-between gap-2">
        <h3 id="sla-heading" className="text-sm font-semibold">
          SLA · {ticket.sla.policy_code}
        </h3>
        <span className="text-xs text-muted-foreground">
          Lần {ticket.sla.occurrence_number}
        </span>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <SlaClock
          label="First response"
          clock={ticket.sla.first_response}
          target={ticket.sla.first_response_target_minutes}
        />
        <SlaClock
          label="Resolution"
          clock={ticket.sla.resolution}
          target={ticket.sla.resolution_target_minutes}
        />
      </div>
      <p className="mt-3 text-xs leading-5 text-muted-foreground">
        {ticket.sla.calendar_code} · {ticket.sla.timezone} ·{" "}
        {ticket.sla.pause_on_waiting
          ? "pause khi waiting"
          : "không pause khi waiting"}
      </p>
    </section>
  );
}

function SlaClock({
  label,
  clock,
  target,
}: {
  label: string;
  clock: TicketDetail["sla"] extends infer T
    ? T extends { first_response: infer C }
      ? C
      : never
    : never;
  target: number;
}) {
  return (
    <div className="rounded-lg border p-3">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <div className="mt-2">
        <SlaStatusBadge status={clock.status} label={clock.status_display} />
      </div>
      <p className="mt-2 text-xs">{formatBusinessMinutes(clock.remaining_business_minutes)}</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Hạn {formatTimestamp(clock.due_at)} · target {target} phút
      </p>
    </div>
  );
}

function TicketActionPanel({
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
  const [reasonMode, setReasonMode] = useState<"hold" | "reopen" | "cancel" | null>(
    null,
  );
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

  return (
    <aside className="space-y-4">
      <section className="rounded-lg border bg-white p-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">Thao tác ticket</h2>
          <span className="text-xs text-muted-foreground">v{ticket.version}</span>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {auth.can(permissions.ticketsAcknowledge) &&
            active &&
            !ticket.first_response_at && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={action.isPending}
                onClick={() =>
                  void run({
                    action: "acknowledge",
                    request: { expected_version: ticket.version },
                  })
                }
              >
                <CheckCircle2 aria-hidden="true" />
                Ghi nhận phản hồi
              </Button>
            )}
          {canExecute &&
            ["open", "assigned", "reopened"].includes(ticket.status) && (
              <Button
                type="button"
                size="sm"
                disabled={action.isPending}
                onClick={() =>
                  void run({
                    action: "start",
                    request: { expected_version: ticket.version },
                  })
                }
              >
                <Play aria-hidden="true" />
                Bắt đầu
              </Button>
            )}
          {canExecute &&
            ["assigned", "in_progress"].includes(ticket.status) && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setReasonMode("hold")}
              >
                <Pause aria-hidden="true" />
                Đặt chờ
              </Button>
            )}
          {canExecute && ticket.status === "waiting" && (
            <Button
              type="button"
              size="sm"
              disabled={action.isPending}
              onClick={() =>
                void run({
                  action: "resume",
                  request: { expected_version: ticket.version },
                })
              }
            >
              <Play aria-hidden="true" />
              Tiếp tục
            </Button>
          )}
          {ticket.status === "in_progress" &&
            auth.can(permissions.maintenanceLogsCreate) &&
            asset && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setMaintenanceOpen(true)}
              >
                <Wrench aria-hidden="true" />
                Ghi kết quả bảo trì
              </Button>
            )}
          {ticket.status === "in_progress" && canResolve && (
            <Button
              type="button"
              size="sm"
              disabled={action.isPending}
              onClick={() =>
                void run({
                  action: "resolve",
                  request: {
                    expected_version: ticket.version,
                    resolved_at: null,
                  },
                })
              }
            >
              <CheckCircle2 aria-hidden="true" />
              Resolve
            </Button>
          )}
          {ticket.status === "resolved" && auth.can(permissions.ticketsClose) && (
            <Button
              type="button"
              size="sm"
              disabled={action.isPending}
              onClick={() =>
                void run({
                  action: "close",
                  request: { expected_version: ticket.version },
                })
              }
            >
              <CheckCircle2 aria-hidden="true" />
              Close
            </Button>
          )}
          {["resolved", "closed"].includes(ticket.status) &&
            auth.can(permissions.ticketsReopen) && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setReasonMode("reopen")}
              >
                <RefreshCw aria-hidden="true" />
                Reopen
              </Button>
            )}
          {active && auth.can(permissions.ticketsCancel) && (
            <Button
              type="button"
              variant="destructive"
              size="sm"
              onClick={() => setReasonMode("cancel")}
            >
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
              void run({
                action: reasonMode,
                request: { expected_version: ticket.version, reason },
              });
            }}
          >
            <Label htmlFor="ticket-action-reason">
              Lý do {reasonMode === "hold" ? "đặt chờ" : reasonMode}
            </Label>
            <Textarea
              id="ticket-action-reason"
              value={reason}
              minLength={3}
              required
              onChange={(event) => setReason(event.target.value)}
            />
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setReasonMode(null)}
              >
                Bỏ qua
              </Button>
              <Button type="submit" size="sm" disabled={action.isPending}>
                Xác nhận
              </Button>
            </div>
          </form>
        )}

        {action.isError && (
          <ActionError error={action.error} onRefresh={onRefresh} />
        )}
      </section>

      {auth.can(permissions.ticketsAssign) && active && options && (
        <section className="rounded-lg border bg-white p-4">
          <h2 className="text-sm font-semibold">Phân công</h2>
          <div className="mt-3 space-y-3">
            <Select value={assignee} onValueChange={setAssignee}>
              <SelectTrigger aria-label="Người được phân công" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Chưa phân công</SelectItem>
                {options.assignees.map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    {item.display_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={group} onValueChange={setGroup}>
              <SelectTrigger aria-label="Support group" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Chưa có group</SelectItem>
                {options.support_groups.map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    {item.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={action.isPending}
              onClick={() =>
                void run({
                  action: "assign",
                  request: {
                    expected_version: ticket.version,
                    assigned_user_id: assignee === "none" ? null : assignee,
                    support_group_id: group === "none" ? null : group,
                  },
                })
              }
            >
              <Save aria-hidden="true" />
              Lưu phân công
            </Button>
          </div>
        </section>
      )}

      {auth.can(permissions.ticketsUpdate) && active && options && (
        <section className="rounded-lg border bg-white p-4">
          <h2 className="text-sm font-semibold">Điều chỉnh priority</h2>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <OptionSelect
              label="Impact"
              value={impact}
              items={options.impacts}
              onChange={(value) => setImpact(value as TicketImpact)}
            />
            <OptionSelect
              label="Urgency"
              value={urgency}
              items={options.urgencies}
              onChange={(value) => setUrgency(value as TicketUrgency)}
            />
          </div>
          <div className="mt-3 flex items-center justify-between rounded-lg bg-muted/40 p-3">
            <span className="text-xs text-muted-foreground">Backend preview</span>
            {preview.data && (
              <TicketOperationsPriorityBadge
                priority={preview.data.priority}
                label={preview.data.priority_display}
              />
            )}
          </div>
          <Input
            className="mt-3"
            aria-label="Lý do đổi priority"
            placeholder="Lý do thay đổi"
            value={priorityReason}
            onChange={(event) => setPriorityReason(event.target.value)}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-3"
            disabled={action.isPending || priorityReason.trim().length < 3}
            onClick={() =>
              void run({
                action: "priority",
                request: {
                  expected_version: ticket.version,
                  impact,
                  urgency,
                  reason: priorityReason,
                },
              })
            }
          >
            Lưu priority
          </Button>
        </section>
      )}

      {auth.can(permissions.slaPoliciesManage) && ticket.sla && (
        <section className="rounded-lg border bg-white p-4">
          <h2 className="text-sm font-semibold">Override SLA policy</h2>
          <Select value={policyId} onValueChange={setPolicyId}>
            <SelectTrigger aria-label="SLA policy" className="mt-3 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">Chọn policy</SelectItem>
              {policies.data?.filter((item) => item.is_active).map((item) => (
                <SelectItem key={item.id} value={item.id}>
                  {item.code} · {item.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            className="mt-3"
            aria-label="Lý do override SLA"
            placeholder="Lý do override"
            value={policyReason}
            onChange={(event) => setPolicyReason(event.target.value)}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-3"
            disabled={
              action.isPending ||
              policyId === "none" ||
              policyReason.trim().length < 3
            }
            onClick={() =>
              void run({
                action: "sla-policy",
                request: {
                  expected_version: ticket.version,
                  policy_id: policyId,
                  reason: policyReason,
                },
              })
            }
          >
            Áp dụng policy
          </Button>
        </section>
      )}

      {asset && ticket.status === "in_progress" && legacyTicket && (
        <MaintenanceResultSheet
          ticket={legacyTicket}
          asset={asset}
          open={maintenanceOpen}
          onOpenChange={setMaintenanceOpen}
          onSaved={onRefresh}
        />
      )}
    </aside>
  );
}

function TicketCommunication({ ticket }: { ticket: TicketDetail }) {
  const auth = useAuth();
  const mutation = useTicketCommentMutation(ticket.ticket_id);
  const canInternal = auth.can(permissions.ticketCommentsInternal);
  const canRequester = auth.can(permissions.ticketCommentsRequester);
  const [visibility, setVisibility] = useState<"internal" | "requester">(
    canInternal ? "internal" : "requester",
  );
  const [body, setBody] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await mutation.mutateAsync({
        visibility,
        body,
        asset_attachment_ids: [],
        work_order_attachment_ids: [],
      });
      setBody("");
    } catch {
      // Safe error rendered below.
    }
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
      <section className="rounded-lg border bg-white">
        <header className="border-b p-4">
          <h2 className="text-sm font-semibold">Lịch sử trao đổi</h2>
        </header>
        {ticket.comments.length ? (
          <div className="divide-y">
            {[...ticket.comments].reverse().map((comment) => (
              <article key={comment.id} className="p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold">{comment.author_name}</span>
                    <span className="rounded bg-muted px-2 py-0.5 text-xs">
                      {comment.visibility === "internal"
                        ? "Nội bộ"
                        : "Hiển thị cho requester"}
                    </span>
                  </div>
                  <time className="text-xs text-muted-foreground">
                    {formatTimestamp(comment.created_at)}
                  </time>
                </div>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-6">
                  {comment.body}
                </p>
              </article>
            ))}
          </div>
        ) : (
          <p className="p-6 text-sm text-muted-foreground">
            Chưa có comment cho ticket này.
          </p>
        )}
      </section>

      {(canInternal || canRequester) && !["closed", "cancelled"].includes(ticket.status) && (
        <form onSubmit={submit} className="h-fit rounded-lg border bg-white p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <MessageSquarePlus className="size-4" aria-hidden="true" />
            Thêm cập nhật
          </h2>
          {canInternal && canRequester && (
            <Select
              value={visibility}
              onValueChange={(value) =>
                setVisibility(value as "internal" | "requester")
              }
            >
              <SelectTrigger aria-label="Phạm vi comment" className="mt-3 w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="internal">Ghi chú nội bộ</SelectItem>
                <SelectItem value="requester">Cập nhật cho requester</SelectItem>
              </SelectContent>
            </Select>
          )}
          <Textarea
            className="mt-3"
            aria-label="Nội dung comment"
            rows={6}
            value={body}
            onChange={(event) => setBody(event.target.value)}
            placeholder="Ghi nhận thông tin mới, không chỉnh sửa lịch sử cũ."
          />
          {mutation.isError && (
            <p role="alert" className="mt-3 text-sm text-red-700">
              {getApiErrorMessage(mutation.error)}
            </p>
          )}
          <Button
            type="submit"
            className="mt-3"
            disabled={mutation.isPending || !body.trim()}
          >
            {mutation.isPending ? (
              <Loader2 className="animate-spin" aria-hidden="true" />
            ) : (
              <Send aria-hidden="true" />
            )}
            Gửi cập nhật
          </Button>
        </form>
      )}
    </div>
  );
}

function TicketTimeline({ ticket }: { ticket: TicketDetail }) {
  const items = useMemo(
    () =>
      [
        ...ticket.comments.map((item) => ({
          id: `comment-${item.id}`,
          at: item.created_at,
          title:
            item.visibility === "internal"
              ? "Ghi chú nội bộ"
              : "Cập nhật requester",
          detail: `${item.author_name}: ${item.body}`,
          tone: "comment",
        })),
        ...ticket.sla_events.map((item) => ({
          id: `sla-${item.id}`,
          at: item.occurred_at,
          title: slaEventLabel(item.event_type),
          detail: item.clock_type
            ? `${item.clock_type} · SLA occurrence ${item.occurrence_number}`
            : `SLA occurrence ${item.occurrence_number}`,
          tone: "sla",
        })),
        ...ticket.escalations.map((item) => ({
          id: `escalation-${item.id}`,
          at: item.detected_at,
          title: `Escalation: ${item.rule_code}`,
          detail: item.clock_type ?? "Ticket-level escalation",
          tone: "escalation",
        })),
      ].sort((left, right) => right.at.localeCompare(left.at)),
    [ticket.comments, ticket.escalations, ticket.sla_events],
  );

  return (
    <section className="rounded-lg border bg-white">
      <header className="border-b p-4">
        <h2 className="text-sm font-semibold">Timeline append-only</h2>
      </header>
      {items.length ? (
        <ol className="divide-y">
          {items.map((item) => (
            <li key={item.id} className="flex gap-3 p-4">
              <span
                className={`mt-1 size-2 shrink-0 rounded-full ${
                  item.tone === "escalation"
                    ? "bg-red-600"
                    : item.tone === "sla"
                      ? "bg-blue-600"
                      : "bg-green-600"
                }`}
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap justify-between gap-2">
                  <p className="text-sm font-semibold">{item.title}</p>
                  <time className="text-xs text-muted-foreground">
                    {formatTimestamp(item.at)}
                  </time>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">{item.detail}</p>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="p-6 text-sm text-muted-foreground">
          Chưa có timeline event.
        </p>
      )}
    </section>
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
        <SelectTrigger aria-label={label} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {items.map((item) => (
            <SelectItem key={item.code} value={item.code}>
              {item.display_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function ActionError({ error, onRefresh }: { error: unknown; onRefresh: () => void }) {
  const stale = error instanceof UserSafeApiError && error.code === "conflict";
  return (
    <div
      role="alert"
      className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900"
    >
      <p>{getApiErrorMessage(error)}</p>
      {stale && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={onRefresh}
        >
          <RefreshCw aria-hidden="true" />
          Tải trạng thái mới
        </Button>
      )}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-sm font-medium">{value}</dd>
    </div>
  );
}

function formatBusinessMinutes(minutes: number | null) {
  if (minutes === null) return "Clock đã dừng";
  if (minutes <= 0) return "Đã đến hoặc quá hạn";
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return hours
    ? `Còn ${hours} giờ${remainder ? ` ${remainder} phút` : ""} làm việc`
    : `Còn ${remainder} phút làm việc`;
}

function slaEventLabel(eventType: string) {
  return (
    {
      policy_applied: "Áp dụng SLA policy",
      clock_started: "Bắt đầu SLA clock",
      paused: "Tạm dừng SLA",
      resumed: "Tiếp tục SLA",
      first_response_recorded: "Ghi nhận first response",
      target_met: "Đạt SLA target",
      breached: "Phát hiện SLA breach",
      resolved: "Dừng resolution SLA",
      reopened: "Mở lại SLA occurrence",
      stopped: "Dừng SLA clock",
    }[eventType] ?? eventType
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
