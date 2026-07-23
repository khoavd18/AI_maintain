"use client";

import { ChevronLeft, ChevronRight, Filter } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import { useAuditLogsQuery } from "@/hooks/use-api-queries";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { AuditLogRecord } from "@/lib/api/schemas";
import { formatTimestamp } from "@/lib/formatters";

export function AuditLogWorkspace() {
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");
  const [resourceType, setResourceType] = useState("all");
  const [outcome, setOutcome] = useState("all");
  const query = useAuditLogsQuery({
    page,
    page_size: 25,
    action: action.trim() || undefined,
    resource_type: resourceType === "all" ? undefined : resourceType,
    outcome: outcome === "all" ? undefined : outcome,
  });

  if (query.isPending) return <LoadingSkeleton />;
  if (query.isError) return <ErrorState title="Chưa tải được audit log" description={getApiErrorMessage(query.error)} action={<RetryButton onClick={() => void query.refetch()} />} />;
  if (!query.data) return <LoadingSkeleton />;

  return (
    <div className="space-y-4">
      <section className="grid gap-3 rounded-lg border bg-white p-4 md:grid-cols-3">
        <div className="space-y-1.5"><Label htmlFor="audit-action">Action</Label><div className="relative"><Filter className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" /><Input id="audit-action" className="pl-8" value={action} onChange={(event) => { setAction(event.target.value); setPage(1); }} placeholder="ticket.created" /></div></div>
        <div className="space-y-1.5"><Label>Resource</Label><Select value={resourceType} onValueChange={(value) => { setResourceType(value); setPage(1); }}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Tất cả</SelectItem><SelectItem value="authentication">Authentication</SelectItem><SelectItem value="user">User</SelectItem><SelectItem value="ticket">Ticket</SelectItem><SelectItem value="maintenance_log">Maintenance log</SelectItem></SelectContent></Select></div>
        <div className="space-y-1.5"><Label>Outcome</Label><Select value={outcome} onValueChange={(value) => { setOutcome(value); setPage(1); }}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Tất cả</SelectItem><SelectItem value="success">Success</SelectItem><SelectItem value="rejected">Rejected</SelectItem></SelectContent></Select></div>
      </section>

      {query.data.items.length ? (
        <div className="overflow-hidden rounded-lg border bg-white">
          <div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead>Thời gian</TableHead><TableHead>Actor</TableHead><TableHead>Action</TableHead><TableHead>Resource</TableHead><TableHead>Outcome</TableHead><TableHead className="w-[32%]">Thay đổi an toàn</TableHead></TableRow></TableHeader><TableBody>{query.data.items.map((event) => <AuditRow key={event.id} event={event} />)}</TableBody></Table></div>
          <div className="flex items-center justify-between border-t px-4 py-3 text-sm"><span>{query.data.total} sự kiện · trang {query.data.page}/{Math.max(1, query.data.total_pages)}</span><div className="flex gap-2"><Button type="button" variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft aria-hidden="true" />Trước</Button><Button type="button" variant="outline" size="sm" disabled={page >= query.data.total_pages} onClick={() => setPage((value) => value + 1)}>Sau<ChevronRight aria-hidden="true" /></Button></div></div>
        </div>
      ) : <div className="rounded-lg border bg-white"><EmptyState title="Không có audit event" description="Điều chỉnh bộ lọc để xem sự kiện khác." /></div>}
    </div>
  );
}

function AuditRow({ event }: { event: AuditLogRecord }) {
  return <TableRow><TableCell className="whitespace-nowrap text-xs">{formatTimestamp(event.occurred_at)}</TableCell><TableCell><p className="text-sm font-medium">{event.actor_display_name ?? "Hệ thống / chưa xác thực"}</p><p className="font-mono text-[11px] text-muted-foreground">{event.request_id}</p></TableCell><TableCell className="font-mono text-xs">{event.action}</TableCell><TableCell><p className="text-sm">{event.resource_type}</p><p className="font-mono text-xs text-muted-foreground">{event.resource_id ?? "-"}</p></TableCell><TableCell><Badge variant={event.outcome === "success" ? "outline" : "secondary"}>{event.outcome}</Badge></TableCell><TableCell className="text-xs text-muted-foreground">{changeSummary(event)}</TableCell></TableRow>;
}

function changeSummary(event: AuditLogRecord) {
  const before = event.before_state ?? {};
  const after = event.after_state ?? {};
  const changed = Array.from(new Set([...Object.keys(before), ...Object.keys(after)])).filter((key) => before[key] !== after[key]);
  if (changed.length) return `Thay đổi: ${changed.join(", ")}`;
  const metadataKeys = Object.keys(event.metadata ?? {});
  return metadataKeys.length ? `Metadata: ${metadataKeys.join(", ")}` : "Không có state chi tiết";
}
