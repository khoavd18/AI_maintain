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
  if (query.isError) return <ErrorState title="Chưa tải được nhật ký kiểm toán" description={getApiErrorMessage(query.error)} action={<RetryButton onClick={() => void query.refetch()} />} />;
  if (!query.data) return <LoadingSkeleton />;

  return (
    <div className="space-y-4">
      <section className="grid gap-3 rounded-lg border bg-white p-4 md:grid-cols-3">
        <div className="space-y-1.5"><Label htmlFor="audit-action">Mã hành động</Label><div className="relative"><Filter className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" /><Input id="audit-action" className="pl-8" value={action} onChange={(event) => { setAction(event.target.value); setPage(1); }} placeholder="ticket.created" /></div></div>
        <div className="space-y-1.5"><Label htmlFor="audit-resource">Loại tài nguyên</Label><Select value={resourceType} onValueChange={(value) => { setResourceType(value); setPage(1); }}><SelectTrigger id="audit-resource" className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Tất cả tài nguyên</SelectItem><SelectItem value="authentication">Xác thực</SelectItem><SelectItem value="user">Người dùng</SelectItem><SelectItem value="ticket">Phiếu sự cố</SelectItem><SelectItem value="maintenance_log">Nhật ký bảo trì</SelectItem></SelectContent></Select></div>
        <div className="space-y-1.5"><Label htmlFor="audit-outcome">Kết quả</Label><Select value={outcome} onValueChange={(value) => { setOutcome(value); setPage(1); }}><SelectTrigger id="audit-outcome" className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Tất cả kết quả</SelectItem><SelectItem value="success">Thành công</SelectItem><SelectItem value="rejected">Bị từ chối</SelectItem></SelectContent></Select></div>
      </section>

      {query.data.items.length ? (
        <div className="overflow-hidden rounded-lg border bg-white">
          <div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead>Thời gian</TableHead><TableHead>Người thực hiện / mã yêu cầu</TableHead><TableHead>Hành động</TableHead><TableHead>Tài nguyên</TableHead><TableHead>Kết quả</TableHead><TableHead className="w-[32%]">Chi tiết thay đổi</TableHead></TableRow></TableHeader><TableBody>{query.data.items.map((event) => <AuditRow key={event.id} event={event} />)}</TableBody></Table></div>
          <div className="flex items-center justify-between border-t px-4 py-3 text-sm"><span>{query.data.total} sự kiện · trang {query.data.page}/{Math.max(1, query.data.total_pages)}</span><div className="flex gap-2"><Button type="button" variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft aria-hidden="true" />Trước</Button><Button type="button" variant="outline" size="sm" disabled={page >= query.data.total_pages} onClick={() => setPage((value) => value + 1)}>Sau<ChevronRight aria-hidden="true" /></Button></div></div>
        </div>
      ) : <div className="rounded-lg border bg-white"><EmptyState title="Không có sự kiện kiểm toán" description="Điều chỉnh bộ lọc để xem sự kiện khác." /></div>}
    </div>
  );
}

function AuditRow({ event }: { event: AuditLogRecord }) {
  return <TableRow><TableCell className="whitespace-nowrap text-xs">{formatTimestamp(event.occurred_at)}</TableCell><TableCell><p className="text-sm font-medium">{event.actor_display_name ?? "Hệ thống / chưa xác thực"}</p><p className="mt-1 text-[11px] text-muted-foreground"><span>Mã yêu cầu: </span><span className="font-mono">{event.request_id}</span></p></TableCell><TableCell className="font-mono text-xs">{event.action}</TableCell><TableCell><p className="font-mono text-xs">{event.resource_type}</p><p className="mt-1 font-mono text-xs text-muted-foreground">{event.resource_id ?? "-"}</p></TableCell><TableCell><Badge variant={event.outcome === "success" ? "outline" : "secondary"}>{outcomeLabel(event.outcome)}</Badge></TableCell><TableCell className="text-xs text-muted-foreground">{changeSummary(event)}</TableCell></TableRow>;
}

function changeSummary(event: AuditLogRecord) {
  const before = event.before_state ?? {};
  const after = event.after_state ?? {};
  const changed = Array.from(new Set([...Object.keys(before), ...Object.keys(after)])).filter((key) => before[key] !== after[key]);
  if (changed.length) return `Trường thay đổi: ${changed.join(", ")}`;
  const metadataKeys = Object.keys(event.metadata ?? {});
  return metadataKeys.length ? `Dữ liệu bổ sung: ${metadataKeys.join(", ")}` : "Không có chi tiết trạng thái";
}

function outcomeLabel(outcome: string) {
  if (outcome === "success") return "Thành công";
  if (outcome === "rejected") return "Bị từ chối";
  return outcome;
}
