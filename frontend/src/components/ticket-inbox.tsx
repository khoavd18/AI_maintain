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
import {
  priorityStatusCatalog,
  resolveStatusPresentation,
  ticketStatusCatalog,
} from "@/lib/status-terminology";

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

  function resetFilters() {
    setDraft(defaultFilters);
    setFilters(defaultFilters);
    setPage(1);
  }

  if (options.isPending) return <LoadingSkeleton />;
  if (options.isError) {
    return (
      <ErrorState
        title="Chưa tải được cấu hình nhóm xử lý"
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
            label="Sự cố đang xử lý"
            value={String(summary.data.active_count)}
            detail="Cần tiếp tục theo dõi"
            icon={Inbox}
            tone="blue"
          />
          <KpiCard
            label="Đang chờ"
            value={String(summary.data.waiting_count)}
            detail="Đang chờ thông tin hoặc điều kiện"
            icon={Clock3}
            tone="orange"
          />
          <KpiCard
            label="Khẩn cấp"
            value={String(summary.data.critical_count)}
            detail="Cần ưu tiên điều phối"
            icon={AlertTriangle}
            tone="red"
          />
          <KpiCard
            label="Sắp đến hạn"
            value={String(summary.data.due_soon_count)}
            detail="Cần xử lý sớm"
            icon={Clock3}
            tone="amber"
          />
          <KpiCard
            label="Đã quá hạn"
            value={String(summary.data.breached_count)}
            detail="Cần điều phối ngay"
            icon={ShieldAlert}
            tone="red"
          />
        </div>
      )}

      <section className="rounded-lg border bg-white">
        <div className="flex flex-col gap-4 border-b p-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="w-full space-y-1.5 sm:max-w-sm">
            <Label htmlFor="ticket-queue">Nhóm cần xử lý</Label>
            <Select value={queue} onValueChange={(value) => selectQueue(value as TicketQueue)}>
              <SelectTrigger id="ticket-queue" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>{queueOrder.map((item) => <SelectItem key={item} value={item}>{queueLabels.get(item) ?? "Nhóm sự cố"}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          {auth.can(permissions.ticketsCreate) && (
            <Button asChild className="shrink-0">
              <Link href="/tickets/new">
                <Plus aria-hidden="true" />
                Báo sự cố
              </Link>
            </Button>
          )}
        </div>

        <form
          onSubmit={applyFilters}
          aria-label="Bộ lọc sự cố"
          className="grid gap-3 border-b bg-muted/20 p-4 md:grid-cols-2 xl:grid-cols-5"
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
                placeholder="Mã phiếu, thiết bị hoặc mô tả"
              />
            </div>
          </div>
          <FilterSelect
            id="ticket-status-filter"
            label="Trạng thái"
            value={draft.status}
            items={options.data.statuses.map((item) => ({
              ...item,
              display_name: resolveStatusPresentation(
                ticketStatusCatalog,
                item.code,
                item.display_name,
              ).label,
            }))}
            onChange={(status) => setDraft({ ...draft, status })}
          />
          <FilterSelect
            id="ticket-priority-filter"
            label="Mức ưu tiên"
            value={draft.priority}
            items={options.data.priorities.map((item) => ({
              ...item,
              display_name: resolveStatusPresentation(
                priorityStatusCatalog,
                item.code,
                item.display_name,
              ).label,
            }))}
            onChange={(priority) => setDraft({ ...draft, priority })}
          />
          <div className="flex items-end">
            <Button type="submit" className="w-full">
              Lọc danh sách
            </Button>
          </div>
          <details className="group md:col-span-2 xl:col-span-5">
            <summary className="w-fit cursor-pointer rounded-md text-sm font-medium text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Bộ lọc thêm</summary>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:max-w-3xl">
              <FilterSelect id="ticket-category-filter" label="Nhóm sự cố" value={draft.category_id} items={options.data.categories.map((item) => ({ code: item.id, display_name: item.name }))} onChange={(category_id) => setDraft({ ...draft, category_id })} />
              <FilterSelect id="ticket-group-filter" label="Nhóm xử lý" value={draft.support_group_id} items={options.data.support_groups.map((item) => ({ code: item.id, display_name: item.name }))} onChange={(support_group_id) => setDraft({ ...draft, support_group_id })} />
              <Button type="button" variant="ghost" className="w-fit" onClick={resetFilters}>Đặt lại bộ lọc</Button>
            </div>
          </details>
        </form>

        {tickets.isPending && <LoadingSkeleton />}
        {tickets.isError && (
          <ErrorState
            title="Chưa tải được danh sách sự cố"
            description={getApiErrorMessage(tickets.error)}
            action={<RetryButton onClick={() => void tickets.refetch()} />}
          />
        )}
        {tickets.data && tickets.data.items.length === 0 && (
          <EmptyState
            title="Nhóm này chưa có sự cố"
            description="Chọn nhóm khác hoặc điều chỉnh bộ lọc."
          />
        )}
        {tickets.data && tickets.data.items.length > 0 && (
          <>
            <div>
              <Table className="block lg:table">
                <TableHeader className="hidden lg:table-header-group">
                  <TableRow>
                    <TableHead>Phiếu / thiết bị</TableHead>
                    <TableHead>Vấn đề</TableHead>
                    <TableHead>Trạng thái</TableHead>
                    <TableHead>Ưu tiên</TableHead>
                    <TableHead>Phân công</TableHead>
                    <TableHead>Hạn xử lý</TableHead>
                    <TableHead>
                      <span className="sr-only">Thao tác</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody className="block space-y-3 p-3 lg:table-row-group lg:space-y-0 lg:p-0">
                  {tickets.data.items.map((ticket) => (
                    <TableRow
                      key={ticket.ticket_id}
                      className="grid grid-cols-2 gap-4 rounded-lg border bg-card p-4 shadow-sm lg:table-row lg:rounded-none lg:border-x-0 lg:border-t-0 lg:bg-transparent lg:p-0 lg:shadow-none"
                    >
                      <TableCell className="col-span-2 block whitespace-normal p-0 lg:table-cell lg:p-2 lg:whitespace-nowrap">
                        <p className="font-mono text-xs font-semibold text-primary">
                          {ticket.ticket_id}
                        </p>
                        <p className="mt-1 font-mono text-xs text-muted-foreground">
                          {ticket.asset_id}
                        </p>
                      </TableCell>
                      <TableCell className="col-span-2 block max-w-none whitespace-normal p-0 lg:table-cell lg:max-w-sm lg:p-2">
                        <MobileFieldLabel>Mô tả sự cố</MobileFieldLabel>
                        <p className="line-clamp-2 font-medium">
                          {ticket.issue_description}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {ticket.category_name ?? "Chưa phân loại"}
                        </p>
                      </TableCell>
                      <TableCell className="block whitespace-normal p-0 lg:table-cell lg:p-2 lg:whitespace-nowrap">
                        <MobileFieldLabel>Trạng thái</MobileFieldLabel>
                        <TicketOperationsStatusBadge
                          status={ticket.status}
                          label={ticket.status_display}
                        />
                      </TableCell>
                      <TableCell className="block whitespace-normal p-0 lg:table-cell lg:p-2 lg:whitespace-nowrap">
                        <MobileFieldLabel>Mức ưu tiên</MobileFieldLabel>
                        <TicketOperationsPriorityBadge
                          priority={ticket.priority}
                          label={ticket.priority_display}
                        />
                      </TableCell>
                      <TableCell className="col-span-2 block whitespace-normal p-0 text-sm sm:col-span-1 lg:table-cell lg:p-2 lg:whitespace-nowrap">
                        <MobileFieldLabel>Phân công</MobileFieldLabel>
                        <p>{ticket.assigned_user_name ?? "Chưa phân công"}</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {ticket.support_group_name ?? "Chưa có nhóm"}
                        </p>
                      </TableCell>
                      <TableCell className="col-span-2 block whitespace-normal p-0 sm:col-span-1 lg:table-cell lg:p-2 lg:whitespace-nowrap">
                        <MobileFieldLabel>Hạn xử lý</MobileFieldLabel>
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
                            Chưa có thời hạn
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="col-span-2 block whitespace-normal p-0 text-right lg:table-cell lg:p-2 lg:whitespace-nowrap">
                        <Button asChild variant="outline" size="sm" className="w-full lg:w-auto">
                          <Link href={`/tickets/${ticket.ticket_id}`}>Xem phiếu</Link>
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <div className="flex items-center justify-between gap-3 border-t p-4 text-sm">
              <span className="text-muted-foreground">
                {tickets.data.total} phiếu · trang {tickets.data.page}/{totalPages}
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

function MobileFieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="mb-1 block text-xs font-medium text-muted-foreground lg:hidden">
      {children}
    </span>
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
