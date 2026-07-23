"use client";

import Link from "next/link";
import { CalendarDays, ChevronLeft, ChevronRight, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";

import { WorkOrderStatusBadge } from "@/components/status-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { EmptyState, ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import { useAssetCatalogQuery, useMaintenanceOptionsQuery, useWorkOrderScheduleQuery } from "@/hooks/use-api-queries";
import { getApiErrorMessage } from "@/lib/api/errors";
import { formatDate } from "@/lib/formatters";
import { addDaysIso, todayIso } from "@/lib/maintenance";

export function WorkOrderCalendar() {
  const today = todayIso();
  const [dateFrom, setDateFrom] = useState(today);
  const [dateTo, setDateTo] = useState(addDaysIso(today, 30));
  const [assetId, setAssetId] = useState("all");
  const [technicianId, setTechnicianId] = useState("all");
  const schedule = useWorkOrderScheduleQuery({ date_from: dateFrom, date_to: dateTo, asset_id: assetId === "all" ? undefined : assetId, assigned_to_user_id: technicianId === "all" ? undefined : technicianId });
  const assets = useAssetCatalogQuery({ lifecycle_status: "active", page_size: 200 });
  const options = useMaintenanceOptionsQuery();
  const groups = useMemo(() => {
    const rows = [
      ...(schedule.data?.work_orders.map((workOrder) => ({ date: workOrder.due_date, type: "work_order" as const, workOrder })) ?? []),
      ...(schedule.data?.upcoming_occurrences.map((occurrence) => ({ date: occurrence.due_date, type: "occurrence" as const, occurrence })) ?? []),
    ].sort((left, right) => left.date.localeCompare(right.date));
    return rows.reduce((grouped, row) => {
      const existing = grouped.get(row.date) ?? [];
      existing.push(row);
      grouped.set(row.date, existing);
      return grouped;
    }, new Map<string, typeof rows>());
  }, [schedule.data]);

  function moveWindow(days: number) { setDateFrom(addDaysIso(dateFrom, days)); setDateTo(addDaysIso(dateTo, days)); }
  if (schedule.isPending || assets.isPending || options.isPending) return <LoadingSkeleton />;
  const error = schedule.error ?? assets.error ?? options.error;
  if (error) return <ErrorState title="Chưa tải được lịch bảo trì" description={getApiErrorMessage(error)} action={<RetryButton onClick={() => void schedule.refetch()} />} />;

  return <div className="space-y-5"><section className="rounded-lg border bg-white p-4"><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Field id="calendar-from" label="Từ ngày"><Input id="calendar-from" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></Field><Field id="calendar-to" label="Đến ngày"><Input id="calendar-to" type="date" min={dateFrom} value={dateTo} onChange={(event) => setDateTo(event.target.value)} /></Field><Field id="calendar-asset" label="Thiết bị"><Select value={assetId} onValueChange={setAssetId}><SelectTrigger id="calendar-asset" className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Tất cả thiết bị</SelectItem>{assets.data?.items.map((asset) => <SelectItem key={asset.asset_id} value={asset.asset_id}>{asset.asset_id}</SelectItem>)}</SelectContent></Select></Field><Field id="calendar-tech" label="Kỹ thuật viên"><Select value={technicianId} onValueChange={setTechnicianId}><SelectTrigger id="calendar-tech" className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Tất cả kỹ thuật viên</SelectItem>{options.data?.technicians.map((user) => <SelectItem key={user.id} value={user.id}>{user.display_name}</SelectItem>)}</SelectContent></Select></Field></div><div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t pt-3"><div className="flex gap-2"><Button type="button" variant="outline" size="sm" onClick={() => moveWindow(-30)}><ChevronLeft aria-hidden="true" />30 ngày</Button><Button type="button" variant="outline" size="sm" onClick={() => moveWindow(30)}>30 ngày<ChevronRight aria-hidden="true" /></Button></div><Button type="button" variant="ghost" size="sm" onClick={() => { setDateFrom(today); setDateTo(addDaysIso(today, 30)); }}><CalendarDays aria-hidden="true" />Hôm nay</Button></div></section>{groups.size ? <div className="space-y-5">{Array.from(groups.entries()).map(([date, rows]) => <section key={date}><div className="mb-2 flex items-center gap-2"><h2 className="text-sm font-semibold">{formatDate(date)}</h2><Badge variant="outline">{rows.length} mục</Badge></div><div className="grid gap-2 lg:grid-cols-2">{rows.map((row) => row.type === "work_order" ? <Link key={`wo-${row.workOrder.id}`} href={`/work-orders/${row.workOrder.id}`} className="rounded-lg border bg-white p-3 hover:border-primary/40"><div className="flex flex-wrap items-center justify-between gap-2"><span className="font-mono text-xs font-semibold text-primary">{row.workOrder.work_order_number}</span><WorkOrderStatusBadge status={row.workOrder.status} label={row.workOrder.status_display} /></div><p className="mt-2 font-medium">{row.workOrder.title}</p><p className="mt-1 text-xs text-muted-foreground">{row.workOrder.asset_id} · {row.workOrder.assigned_to_name ?? "Chưa phân công"}</p>{row.workOrder.is_overdue && <p className="mt-2 flex items-center gap-1 text-xs font-medium text-red-700"><TriangleAlert className="size-3.5" aria-hidden="true" />Quá hạn theo grace period</p>}</Link> : <Link key={`occurrence-${row.occurrence.plan_id}-${row.occurrence.due_date}`} href={`/maintenance/plans/${row.occurrence.plan_id}`} className="rounded-lg border border-dashed bg-blue-50/40 p-3 hover:border-primary/40"><div className="flex flex-wrap items-center justify-between gap-2"><span className="font-mono text-xs font-semibold text-primary">{row.occurrence.plan_code}</span><Badge variant="outline">Occurrence chưa phát hành</Badge></div><p className="mt-2 font-medium">{row.occurrence.plan_name}</p><p className="mt-1 text-xs text-muted-foreground">{row.occurrence.asset_id} · phát hành từ {formatDate(row.occurrence.generation_release_date)}</p></Link>)}</div></section>)}</div> : <div className="rounded-lg border bg-white"><EmptyState title="Không có lịch trong khoảng này" description="Điều chỉnh date range, asset hoặc technician." /></div>}<p className="text-xs text-muted-foreground">Calendar chỉ là projection: schedule source of truth vẫn là preventive plan và work order. Không hỗ trợ kéo-thả hoặc thay đổi lịch ngầm.</p></div>;
}

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) { return <div className="space-y-1.5"><Label htmlFor={id}>{label}</Label>{children}</div>; }
