"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Inbox,
  Plus,
  Search,
  ShieldAlert,
} from "lucide-react";
import { type FormEvent, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { KpiCard } from "@/components/kpi-card";
import {
  SlaStatusBadge,
  TicketOperationsPriorityBadge,
  TicketOperationsStatusBadge,
} from "@/components/ticket-operations-badges";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState, ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import {
  useSlaSummaryQuery,
  useTicketingOptionsQuery,
  useTicketQueueQuery,
} from "@/hooks/use-ticketing";
import { getApiErrorMessage } from "@/lib/api/errors";
import type {
  TicketQueue,
  TicketStatusCode,
} from "@/lib/api/ticketing-schemas";
import { permissions } from "@/lib/auth";
import { formatTimestamp } from "@/lib/formatters";
import { cn } from "@/lib/utils";

const queueOrder: TicketQueue[] = [
  "unassigned",
  "assigned_to_me",
  "assigned_to_queue",
  "critical",
  "due_soon",
  "sla_breached",
  "waiting",
  "recently_resolved",
  "reopened",
];

interface QueueFilters {
  search: string;
  status: string;
  priority: string;
  category_id: string;
  support_group_id: string;
  assigned_user_id: string;
}

const defaultFilters: QueueFilters = {
  search: "",
  status: "all",
  priority: "all",
  category_id: "all",
  support_group_id: "all",
  assigned_user_id: "all",
};

export function TicketInbox() {
  const auth = useAuth();
  const [queue, setQueue] = useState<TicketQueue>("unassigned");
  const [draft, setDraft] = useState(defaultFilters);
  const [filters, setFilters] = useState(defaultFilters);
  const [page, setPage] = useState(1);
  const options = useTicketingOptionsQuery();
  const summary = useSlaSummaryQuery(auth.can(permissions.slaPoliciesRead));
  const queryFilters = {
    search: filters.search || undefined,
    status: filters.status === "all" ? undefined : filters.status,
    priority: filters.priority === "all" ? undefined : filters.priority,
    category_id:
      filters.category_id === "all" ? undefined : filters.category_id,
    support_group_id:
      filters.support_group_id === "all"
        ? undefined
        : filters.support_group_id,
    assigned_user_id:
      filters.assigned_user_id === "all"
        ? undefined
        : filters.assigned_user_id,
    page,
    page_size: 25,
  };
  const tickets = useTicketQueueQuery(queue, queryFilters);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPage(1);
    setFilters(draft);
  }

  function selectQueue(nextQueue: TicketQueue) {
    setQueue(nextQueue);
    setPage(1);
  }

  if (options.isPending) return <LoadingSkeleton />;
  if (options.isError) {
    return (
      <ErrorState
        title="Chưa tải được cấu hình queue"
        description={getApiErrorMessage(options.error)}
        action={<RetryButton onClick={() => void options.refetch()} />}
      />
    );
  }

  const queueLabels = new Map(
    options.data.queues.map((item) => [item.code, item.display_name]),
  );
  const totalPages = tickets.data
    ? Math.max(1, Math.ceil(tickets.data.total / tickets.data.page_size))
    : 1;

  return (
    <div className="space-y-5">
      {summary.data && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <KpiCard
            label="Ticket đang hoạt động"
            value={String(summary.data.active_count)}
            detail="Không gồm resolved/closed/cancelled"
            icon={Inbox}
            tone="blue"
          />
          <KpiCard
            label="Đang chờ"
            value={String(summary.data.waiting_count)}
            detail="SLA có thể tạm dừng theo policy"
            icon={Clock3}
            tone="orange"
          />
          <KpiCard
            label="Critical"
            value={String(summary.data.critical_count)}
            detail="Priority do backend tính"
            icon={AlertTriangle}
            tone="red"
          />
          <KpiCard
            label="Sắp đến hạn"
            value={String(summary.data.due_soon_count)}
            detail="Derived từ SLA snapshot"
            icon={Clock3}
            tone="amber"
          />
          <KpiCard
            label="Vi phạm SLA"
            value={String(summary.data.breached_count)}
            detail="Không phải cờ nhập thủ công"
            icon={ShieldAlert}
            tone="red"
          />
        </div>
      )}

      <section className="rounded-lg border bg-white">
        <div className="flex flex-col gap-4 border-b p-4 xl:flex-row">
          <nav
            aria-label="Ticket queues"
            className="grid min-w-0 flex-1 gap-2 sm:grid-cols-3 xl:grid-cols-5"
          >
            {queueOrder.map((item) => (
              <Button
                key={item}
                type="button"
                variant={queue === item ? "secondary" : "ghost"}
                className={cn("justify-start", queue === item && "ring-1 ring-border")}
                aria-pressed={queue === item}
                onClick={() => selectQueue(item)}
              >
                {queueLabels.get(item) ?? item}
              </Button>
            ))}
          </nav>
          {auth.can(permissions.ticketsCreate) && (
            <Button asChild className="shrink-0">
              <Link href="/tickets/new">
                <Plus aria-hidden="true" />
                Tiếp nhận ticket
              </Link>
            </Button>
          )}
        </div>

        <form
          onSubmit={applyFilters}
          aria-label="Bộ lọc ticket"
          className="grid gap-3 border-b bg-muted/20 p-4 md:grid-cols-2 xl:grid-cols-7"
        >
          <div className="space-y-1.5 md:col-span-2">
            <Label htmlFor="ticket-queue-search">Tìm kiếm</Label>
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <Input
                id="ticket-queue-search"
                className="pl-8"
                value={draft.search}
                onChange={(event) =>
                  setDraft({ ...draft, search: event.target.value })
                }
                placeholder="Ticket ID, asset hoặc mô tả"
              />
            </div>
          </div>
          <FilterSelect
            id="ticket-status-filter"
            label="Trạng thái"
            value={draft.status}
            items={options.data.statuses}
            onChange={(status) => setDraft({ ...draft, status })}
          />
          <FilterSelect
            id="ticket-priority-filter"
            label="Priority"
            value={draft.priority}
            items={options.data.priorities}
            onChange={(priority) => setDraft({ ...draft, priority })}
          />
          <FilterSelect
            id="ticket-category-filter"
            label="Category"
            value={draft.category_id}
            items={options.data.categories.map((item) => ({
              code: item.id,
              display_name: item.name,
            }))}
            onChange={(category_id) => setDraft({ ...draft, category_id })}
          />
          <FilterSelect
            id="ticket-group-filter"
            label="Support group"
            value={draft.support_group_id}
            items={options.data.support_groups.map((item) => ({
              code: item.id,
              display_name: item.name,
            }))}
            onChange={(support_group_id) =>
              setDraft({ ...draft, support_group_id })
            }
          />
          <div className="flex items-end">
            <Button type="submit" variant="outline" className="w-full">
              Áp dụng
            </Button>
          </div>
        </form>

        {tickets.isPending && <LoadingSkeleton />}
        {tickets.isError && (
          <ErrorState
            title="Chưa tải được ticket queue"
            description={getApiErrorMessage(tickets.error)}
            action={<RetryButton onClick={() => void tickets.refetch()} />}
          />
        )}
        {tickets.data && tickets.data.items.length === 0 && (
          <EmptyState
            title="Queue chưa có ticket"
            description="Điều chỉnh queue hoặc bộ lọc để xem các ticket khác."
          />
        )}
        {tickets.data && tickets.data.items.length > 0 && (
          <>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ticket / asset</TableHead>
                    <TableHead>Vấn đề</TableHead>
                    <TableHead>Trạng thái</TableHead>
                    <TableHead>Priority</TableHead>
                    <TableHead>Phân công</TableHead>
                    <TableHead>Resolution SLA</TableHead>
                    <TableHead>Cập nhật</TableHead>
                    <TableHead>
                      <span className="sr-only">Thao tác</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tickets.data.items.map((ticket) => (
                    <TableRow key={ticket.ticket_id}>
                      <TableCell>
                        <p className="font-mono text-xs font-semibold text-primary">
                          {ticket.ticket_id}
                        </p>
                        <p className="mt-1 font-mono text-xs text-muted-foreground">
                          {ticket.asset_id}
                        </p>
                      </TableCell>
                      <TableCell className="max-w-sm">
                        <p className="line-clamp-2 font-medium">
                          {ticket.issue_description}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {ticket.category_name ?? "Chưa phân loại"}
                        </p>
                      </TableCell>
                      <TableCell>
                        <TicketOperationsStatusBadge
                          status={ticket.status}
                          label={ticket.status_display}
                        />
                      </TableCell>
                      <TableCell>
                        <TicketOperationsPriorityBadge
                          priority={ticket.priority}
                          label={ticket.priority_display}
                        />
                      </TableCell>
                      <TableCell className="text-sm">
                        <p>{ticket.assigned_user_name ?? "Chưa phân công"}</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {ticket.support_group_name ?? "Chưa có group"}
                        </p>
                      </TableCell>
                      <TableCell>
                        {ticket.sla ? (
                          <div className="space-y-1.5">
                            <SlaStatusBadge
                              status={ticket.sla.resolution.status}
                              label={ticket.sla.resolution.status_display}
                            />
                            <p className="text-xs text-muted-foreground">
                              {formatRemaining(
                                ticket.sla.resolution.remaining_business_minutes,
                              )}
                            </p>
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground">
                            Chưa có SLA
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatTimestamp(ticket.updated_at)}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button asChild variant="ghost" size="sm">
                          <Link href={`/tickets/${ticket.ticket_id}`}>Mở</Link>
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <div className="flex items-center justify-between gap-3 border-t p-4 text-sm">
              <span className="text-muted-foreground">
                {tickets.data.total} ticket · trang {tickets.data.page}/{totalPages}
              </span>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((value) => Math.max(1, value - 1))}
                >
                  <ChevronLeft aria-hidden="true" />
                  Trước
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() =>
                    setPage((value) => Math.min(totalPages, value + 1))
                  }
                >
                  Sau
                  <ChevronRight aria-hidden="true" />
                </Button>
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function FilterSelect({
  id,
  label,
  value,
  items,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  items: { code: string; display_name: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Tất cả</SelectItem>
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

function formatRemaining(minutes: number | null) {
  if (minutes === null) return "Đã dừng";
  if (minutes <= 0) return "Đã đến hạn";
  if (minutes < 60) return `Còn ${minutes} phút làm việc`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return `Còn ${hours}h${remainder ? ` ${remainder}m` : ""} làm việc`;
}

export function isActiveTicketStatus(status: TicketStatusCode) {
  return ["open", "assigned", "in_progress", "waiting", "reopened"].includes(
    status,
  );
}
