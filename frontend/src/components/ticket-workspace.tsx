"use client";

import { Columns3, Filter, List, Plus, Search, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";

import { PermissionDeniedNotice, useAuth } from "@/components/auth-provider";
import { PriorityBadge, TicketStatusBadge } from "@/components/status-badges";
import { TicketCard } from "@/components/ticket-card";
import { TicketCreateSheet } from "@/components/ticket-create-sheet";
import { TicketDetailSheet, type RefreshedTicketState } from "@/components/ticket-detail-sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import { useAssetsQuery, useMaintenanceLogsQuery, useTicketsQuery } from "@/hooks/use-api-queries";
import { adaptAsset, adaptMaintenanceLog, adaptTicket } from "@/lib/adapters";
import { getApiErrorMessage } from "@/lib/api/errors";
import { permissions } from "@/lib/auth";
import type { Asset, Ticket, TicketStatus } from "@/lib/types";

const columns: { status: TicketStatus; label: string; accent: string }[] = [
  { status: "new", label: "Mới tạo", accent: "bg-blue-500" },
  { status: "in_progress", label: "Đang xử lý", accent: "bg-amber-500" },
  { status: "resolved", label: "Đã xử lý", accent: "bg-green-600" },
];

export function TicketWorkspace({
  initialCreateAssetId,
  initialTicketId,
}: {
  initialCreateAssetId?: string;
  initialTicketId?: string;
}) {
  const auth = useAuth();
  const canCreate = auth.can(permissions.ticketsCreate);
  const ticketsQuery = useTicketsQuery({ limit: 1000 });
  const assetsQuery = useAssetsQuery();
  const logsQuery = useMaintenanceLogsQuery({ limit: 1000 });
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(initialTicketId ?? null);
  const [createAssetId, setCreateAssetId] = useState<string | null>(initialCreateAssetId ?? null);
  const [search, setSearch] = useState(initialCreateAssetId ?? initialTicketId ?? "");
  const [priority, setPriority] = useState("all");
  const [viewMode, setViewMode] = useState<"board" | "table">("board");
  const [analyticsStale, setAnalyticsStale] = useState(false);
  const ticketItems = useMemo(() => (ticketsQuery.data ?? []).map(adaptTicket), [ticketsQuery.data]);
  const assets = useMemo(() => (assetsQuery.data ?? []).map(adaptAsset), [assetsQuery.data]);
  const logItems = useMemo(() => (logsQuery.data ?? []).map(adaptMaintenanceLog), [logsQuery.data]);
  const selectedTicket = ticketItems.find((ticket) => ticket.id === selectedTicketId) ?? null;
  const relatedAsset = assets.find((asset) => asset.id === selectedTicket?.assetId);
  const linkedLogs = logItems.filter((log) => log.ticketId === selectedTicketId);
  const createAsset = canCreate ? assets.find((asset) => asset.id === createAssetId) ?? null : null;
  const defaultAsset = [...assets].sort((left, right) => (right.riskScore ?? -1) - (left.riskScore ?? -1))[0];
  const filteredTickets = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase("vi");
    return ticketItems.filter((ticket) => {
      const matchesSearch = !normalizedSearch || [ticket.id, ticket.assetId, ticket.summary, ticket.technician].some((value) => value.toLocaleLowerCase("vi").includes(normalizedSearch));
      return matchesSearch && (priority === "all" || ticket.priority === priority);
    });
  }, [priority, search, ticketItems]);

  if (ticketsQuery.isPending || assetsQuery.isPending || logsQuery.isPending) return <LoadingSkeleton />;
  const failedQuery = [ticketsQuery, assetsQuery, logsQuery].find((query) => query.isError);
  if (failedQuery) return <ErrorState title="Chưa tải được ticket workspace" description={getApiErrorMessage(failedQuery.error)} action={<RetryButton onClick={() => void Promise.all([ticketsQuery.refetch(), assetsQuery.refetch(), logsQuery.refetch()])} />} />;

  async function refreshSelectedState(): Promise<RefreshedTicketState> {
    const [ticketResult, logResult] = await Promise.all([ticketsQuery.refetch(), logsQuery.refetch()]);
    if (ticketResult.error || logResult.error) throw ticketResult.error ?? logResult.error;
    const refreshedTicketRecord = ticketResult.data?.find((ticket) => ticket.ticket_id === selectedTicketId);
    return {
      ticket: refreshedTicketRecord ? adaptTicket(refreshedTicketRecord) : null,
      linkedLogCount: (logResult.data ?? []).filter((log) => log.ticket_id === selectedTicketId).length,
    };
  }

  function startCreate(asset?: Asset) {
    if (asset) setCreateAssetId(asset.id);
  }

  return (
    <>
      {analyticsStale && <div role="status" className="mb-4 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm font-medium text-amber-950"><TriangleAlert className="size-4" aria-hidden="true" />Dữ liệu phân tích chưa được chạy lại. Risk Score và KPI vẫn thuộc batch gần nhất.</div>}

      <section aria-label="Điều khiển ticket" className="mb-4 rounded-lg border bg-white p-3 sm:p-4">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-end">
          <div className="grid flex-1 gap-3 sm:grid-cols-[minmax(240px,1fr)_220px]">
            <div className="space-y-1.5"><Label htmlFor="ticket-search">Tìm ticket</Label><div className="relative"><Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" /><Input id="ticket-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Ticket ID, asset ID hoặc kỹ thuật viên" className="pl-8" /></div></div>
            <div className="space-y-1.5"><Label htmlFor="ticket-priority">Mức ưu tiên</Label><Select value={priority} onValueChange={setPriority}><SelectTrigger id="ticket-priority" className="w-full"><Filter aria-hidden="true" /><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Tất cả mức ưu tiên</SelectItem><SelectItem value="Khẩn cấp">Khẩn cấp</SelectItem><SelectItem value="Cao">Cao</SelectItem><SelectItem value="Trung bình">Trung bình</SelectItem><SelectItem value="Thấp">Thấp</SelectItem></SelectContent></Select></div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 xl:justify-end">
            <div className="inline-flex rounded-lg border bg-muted p-0.5" aria-label="Kiểu hiển thị"><Button type="button" size="sm" variant={viewMode === "board" ? "secondary" : "ghost"} aria-pressed={viewMode === "board"} onClick={() => setViewMode("board")}><Columns3 aria-hidden="true" />Board</Button><Button type="button" size="sm" variant={viewMode === "table" ? "secondary" : "ghost"} aria-pressed={viewMode === "table"} onClick={() => setViewMode("table")}><List aria-hidden="true" />Table</Button></div>
            {canCreate && <Button type="button" disabled={!defaultAsset} onClick={() => startCreate(createAsset ?? defaultAsset)}><Plus aria-hidden="true" />Tạo ticket</Button>}
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t pt-3 text-xs text-muted-foreground"><span>{filteredTickets.length} / {ticketItems.length} ticket phù hợp</span><span>Live FastAPI · PostgreSQL transactions</span></div>
      </section>

      {!canCreate && <div className="mb-4"><PermissionDeniedNotice message="Vai trò hiện tại có thể xem ticket nhưng không có permission tạo ticket." /></div>}

      {viewMode === "board" ? <TicketBoard tickets={filteredTickets} onSelect={(ticket) => setSelectedTicketId(ticket.id)} /> : <TicketTable tickets={filteredTickets} onSelect={(ticket) => setSelectedTicketId(ticket.id)} />}
      <TicketDetailSheet ticket={selectedTicket} asset={relatedAsset} linkedLogs={linkedLogs} onClose={() => setSelectedTicketId(null)} onRefreshState={refreshSelectedState} onWriteConfirmed={() => setAnalyticsStale(true)} />
      {createAsset && <TicketCreateSheet asset={createAsset} open={Boolean(createAssetId)} onOpenChange={(open) => !open && setCreateAssetId(null)} onCreated={(ticketId) => { setSelectedTicketId(ticketId); setSearch(ticketId); setAnalyticsStale(true); }} />}
    </>
  );
}

function TicketBoard({ tickets, onSelect }: { tickets: Ticket[]; onSelect: (ticket: Ticket) => void }) {
  return <div className="grid items-start gap-4 lg:grid-cols-3">{columns.map((column) => { const items = tickets.filter((ticket) => ticket.status === column.status); return <section key={column.status} aria-labelledby={`column-${column.status}`} className="rounded-lg bg-neutral-100/80 p-3 ring-1 ring-neutral-200"><header className="mb-3 flex items-center justify-between gap-2 px-1"><div className="flex items-center gap-2"><span className={`size-2 rounded-full ${column.accent}`} aria-hidden="true" /><h2 id={`column-${column.status}`} className="text-sm font-semibold">{column.label}</h2></div><span className="flex size-6 items-center justify-center rounded-full bg-white text-xs font-semibold ring-1 ring-neutral-200">{items.length}</span></header><div className="space-y-3">{items.length ? items.map((ticket) => <TicketCard key={ticket.id} ticket={ticket} onSelect={onSelect} compact />) : <div className="rounded-lg border border-dashed bg-white py-2"><EmptyState title="Không có ticket" description="Không có kết quả phù hợp trong nhóm này." /></div>}</div></section>; })}</div>;
}

function TicketTable({ tickets, onSelect }: { tickets: Ticket[]; onSelect: (ticket: Ticket) => void }) {
  if (!tickets.length) return <div className="rounded-lg border bg-white"><EmptyState title="Không có ticket" description="Điều chỉnh từ khóa hoặc mức ưu tiên để xem kết quả khác." /></div>;
  return <div className="overflow-hidden rounded-lg border bg-white"><div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead>Ticket / thiết bị</TableHead><TableHead>Vấn đề</TableHead><TableHead>Trạng thái</TableHead><TableHead>Ưu tiên</TableHead><TableHead>Phụ trách</TableHead><TableHead>Thời gian</TableHead><TableHead><span className="sr-only">Thao tác</span></TableHead></TableRow></TableHeader><TableBody>{tickets.map((ticket) => <TableRow key={ticket.id}><TableCell><p className="font-mono text-xs font-medium text-primary">{ticket.id}</p><p className="mt-1 font-mono text-xs text-muted-foreground">{ticket.assetId}</p></TableCell><TableCell className="max-w-sm font-medium">{ticket.summary}</TableCell><TableCell><TicketStatusBadge status={ticket.status} /></TableCell><TableCell><PriorityBadge priority={ticket.priority} /></TableCell><TableCell>{ticket.technician}</TableCell><TableCell className="text-xs text-muted-foreground">{ticket.status === "resolved" ? "Xử lý" : "Chờ"} {ticket.waitingTime}</TableCell><TableCell className="text-right"><Button type="button" variant="ghost" size="sm" onClick={() => onSelect(ticket)}>Mở</Button></TableCell></TableRow>)}</TableBody></Table></div></div>;
}
