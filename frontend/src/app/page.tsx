"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CircleCheckBig,
  Clock3,
  Repeat2,
  TicketCheck,
  TicketPlus,
  Wrench,
} from "lucide-react";

import { DataTableShell } from "@/components/data-table-shell";
import { OverviewCharts, type DistributionDatum } from "@/components/dashboard-charts";
import { KpiCard } from "@/components/kpi-card";
import { PageHeader } from "@/components/page-header";
import { MaintenanceBadge, PriorityBadge, RiskBadge, TicketStatusBadge } from "@/components/status-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import {
  useAssetsQuery,
  useMaintenanceKpisQuery,
  usePreventiveQuery,
  useTicketsQuery,
} from "@/hooks/use-api-queries";
import { adaptAsset, adaptTicket } from "@/lib/adapters";
import { getApiErrorMessage } from "@/lib/api/errors";
import { formatDurationHours, formatPercentage } from "@/lib/formatters";

const riskOrder = ["Thấp", "Trung bình", "Cao", "Khẩn cấp"] as const;
const riskColors = ["#16a34a", "#d97706", "#ea580c", "#dc2626"];
const ticketOrder = ["Mới tạo", "Đang xử lý", "Đã xử lý"] as const;
const ticketColors = ["#2563eb", "#d97706", "#16a34a"];
const preventiveOrder = ["Chưa đến hạn", "Sắp đến hạn", "Quá hạn"] as const;
const preventiveColors = ["#16a34a", "#d97706", "#dc2626"];

export default function OverviewPage() {
  const assetsQuery = useAssetsQuery();
  const ticketsQuery = useTicketsQuery({ limit: 1000 });
  const kpisQuery = useMaintenanceKpisQuery();
  const preventiveQuery = usePreventiveQuery();
  const queries = [assetsQuery, ticketsQuery, kpisQuery, preventiveQuery];

  if (queries.some((query) => query.isPending)) {
    return <LoadingSkeleton />;
  }

  const failedQuery = queries.find((query) => query.isError);
  if (failedQuery) {
    return (
      <ErrorState
        title="Chưa tải được tổng quan"
        description={getApiErrorMessage(failedQuery.error)}
        action={<RetryButton onClick={() => void Promise.all(queries.map((query) => query.refetch()))} />}
      />
    );
  }

  if (!assetsQuery.data || !ticketsQuery.data || !kpisQuery.data || !preventiveQuery.data) {
    return <LoadingSkeleton />;
  }

  const assets = assetsQuery.data.map(adaptAsset);
  const tickets = ticketsQuery.data.map(adaptTicket);
  const kpis = kpisQuery.data;
  const priorityAssets = assets
    .filter((asset) => asset.riskScore !== null)
    .sort((a, b) => (b.riskScore ?? -1) - (a.riskScore ?? -1))
    .slice(0, 5);
  const latestTickets = tickets.slice(0, 3);
  const riskDistribution = buildDistribution(
    riskOrder,
    riskColors,
    assets.map((asset) => asset.riskLevel).filter((level): level is NonNullable<typeof level> => level !== null),
  );
  const ticketDistribution = buildDistribution(
    ticketOrder,
    ticketColors,
    ticketsQuery.data.map((ticket) => ticket.status),
  );
  const preventiveDistribution = buildDistribution(
    preventiveOrder,
    preventiveColors,
    preventiveQuery.data.map((record) => record.maintenance_status_display),
  );

  return (
    <>
      <PageHeader
        title="Tổng quan bảo trì"
        description="Ưu tiên thiết bị cần kiểm tra từ risk score, ticket và lịch bảo trì trong batch mới nhất."
        breadcrumbs={[{ label: "Tổng quan" }]}
        actions={<Button asChild variant="outline"><Link href="/assets">Xem thiết bị<ArrowRight aria-hidden="true" /></Link></Button>}
      />

      <section aria-label="Chỉ số cần chú ý" className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <KpiCard label="Tổng thiết bị" value={String(assets.length)} detail="Danh mục đang theo dõi" icon={Wrench} tone="blue" />
        <KpiCard label="Ticket đang mở" value={String(kpis.open_tickets)} detail={`${kpis.total_tickets} ticket trong dữ liệu`} icon={TicketCheck} tone="amber" />
        <KpiCard label="Thiết bị quá hạn" value={String(kpis.overdue_asset_count)} detail="Theo lịch preventive" icon={CalendarClock} tone="orange" />
        <KpiCard label="Risk Cao / Khẩn cấp" value={String(kpis.high_critical_risk_asset_count)} detail="Ưu tiên kiểm tra" icon={AlertTriangle} tone="red" />
      </section>

      <section aria-label="Chỉ số hỗ trợ" className="mt-4 grid grid-cols-2 divide-x divide-y rounded-lg border bg-white md:grid-cols-4 md:divide-y-0">
        <SecondaryStat label="Tỷ lệ ticket đã xử lý" value={formatPercentage(kpis.ticket_resolution_rate_percent)} icon={CircleCheckBig} />
        <SecondaryStat label="Thời gian xử lý trung bình" value={formatDurationHours(kpis.average_resolution_time_hours)} icon={Clock3} />
        <SecondaryStat label="Nhóm lỗi lặp lại" value={String(kpis.recurring_issue_count)} icon={Repeat2} />
        <SecondaryStat label="Log cần theo dõi" value={String(kpis.follow_up_required_maintenance_count)} icon={CalendarClock} />
      </section>

      <section aria-labelledby="today-priority" className="mt-6 overflow-hidden rounded-lg border border-orange-200 bg-white">
        <header className="flex flex-col justify-between gap-3 border-b border-orange-100 bg-orange-50 px-4 py-4 sm:flex-row sm:items-center sm:px-5">
          <div>
            <div className="flex items-center gap-2">
              <AlertTriangle className="size-4 text-orange-700" aria-hidden="true" />
              <h2 id="today-priority" className="text-base font-semibold">Ưu tiên hôm nay</h2>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {priorityAssets[0]?.id ?? "Chưa có thiết bị"} có risk score cao nhất trong batch hiện tại.
            </p>
          </div>
          <Badge className="bg-orange-100 text-orange-800 ring-1 ring-orange-200 hover:bg-orange-100">
            {priorityAssets.length} thiết bị đầu danh sách
          </Badge>
        </header>

        <div className="grid gap-3 p-4 md:hidden">
          {priorityAssets.map((asset, index) => (
            <article key={asset.id} className="rounded-lg border p-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold text-orange-700">Ưu tiên {index + 1}</p>
                  <p className="mt-1 font-mono text-sm font-semibold">{asset.id}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{asset.name}</p>
                </div>
                <div className="text-right">
                  <p className="text-lg font-semibold tabular-nums">{asset.riskScore?.toFixed(2) ?? "--"}</p>
                  {asset.riskLevel && <RiskBadge level={asset.riskLevel} />}
                </div>
              </div>
              <p className="mt-3 text-sm leading-5">{asset.contributingFactors}</p>
              <div className="mt-3 flex gap-2">
                <Button asChild variant="outline" className="flex-1"><Link href={`/assets/${asset.id}`}>Xem thiết bị</Link></Button>
                <Button asChild className="flex-1"><Link href={`/tickets?asset=${asset.id}&action=create`}><TicketPlus aria-hidden="true" />Tạo ticket</Link></Button>
              </div>
            </article>
          ))}
        </div>

        <div className="hidden overflow-x-auto md:block">
          <Table>
            <TableHeader><TableRow><TableHead>Ưu tiên</TableHead><TableHead>Thiết bị</TableHead><TableHead>Tình trạng</TableHead><TableHead className="w-[38%]">Lý do cần chú ý</TableHead><TableHead className="w-48 text-right">Hành động</TableHead></TableRow></TableHeader>
            <TableBody>
              {priorityAssets.map((asset, index) => (
                <TableRow key={asset.id}>
                  <TableCell className="font-semibold tabular-nums">#{index + 1}</TableCell>
                  <TableCell><p className="font-mono text-xs font-medium text-primary">{asset.id}</p><p className="mt-1 max-w-52 truncate text-xs text-muted-foreground">{asset.name}</p></TableCell>
                  <TableCell><div className="flex flex-wrap gap-1.5">{asset.riskLevel && <RiskBadge level={asset.riskLevel} />}{asset.maintenanceStatus && <MaintenanceBadge status={asset.maintenanceStatus} />}</div><p className="mt-1.5 text-xs text-muted-foreground">Risk {asset.riskScore?.toFixed(2) ?? "chưa có dữ liệu"}</p></TableCell>
                  <TableCell className="max-w-md text-sm text-muted-foreground"><p className="line-clamp-2">{asset.contributingFactors}</p></TableCell>
                  <TableCell><div className="flex justify-end gap-2"><Button asChild variant="outline" size="sm"><Link href={`/assets/${asset.id}`}>Xem thiết bị</Link></Button><Button asChild size="sm"><Link href={`/tickets?asset=${asset.id}&action=create`}>Tạo ticket</Link></Button></div></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>

      <section aria-label="Phân bố vận hành" className="mt-6">
        <div className="mb-3"><h2 className="text-base font-semibold">Điều kiện vận hành</h2><p className="mt-1 text-sm text-muted-foreground">Phân bố từ batch analytics và dữ liệu nghiệp vụ hiện tại.</p></div>
        <OverviewCharts riskDistribution={riskDistribution} ticketDistribution={ticketDistribution} preventiveDistribution={preventiveDistribution} />
      </section>

      <section className="mt-6">
        <DataTableShell title="Hoạt động ticket gần đây" description="Ba ticket mới nhất cần điều phối hoặc theo dõi" actions={<Button asChild variant="ghost" size="sm"><Link href="/tickets">Mở workspace<ArrowRight aria-hidden="true" /></Link></Button>}>
          <div className="overflow-x-auto">
            <Table><TableHeader><TableRow><TableHead>Ticket</TableHead><TableHead>Vấn đề</TableHead><TableHead>Trạng thái</TableHead><TableHead>Phụ trách</TableHead><TableHead>Thời gian</TableHead></TableRow></TableHeader>
              <TableBody>{latestTickets.map((ticket) => <TableRow key={ticket.id}><TableCell><p className="font-mono text-xs font-medium text-primary">{ticket.id}</p><p className="mt-1 font-mono text-xs text-muted-foreground">{ticket.assetId}</p></TableCell><TableCell className="max-w-md font-medium">{ticket.summary}</TableCell><TableCell><TicketStatusBadge status={ticket.status} /></TableCell><TableCell>{ticket.technician}</TableCell><TableCell><div className="flex items-center gap-2"><PriorityBadge priority={ticket.priority} /><span className="text-xs text-muted-foreground">{ticket.waitingTime}</span></div></TableCell></TableRow>)}</TableBody>
            </Table>
          </div>
        </DataTableShell>
      </section>
    </>
  );
}

function SecondaryStat({ label, value, icon: Icon }: { label: string; value: string; icon: typeof Clock3 }) {
  return <div className="px-4 py-3 md:px-5"><p className="flex items-center gap-1.5 text-xs text-muted-foreground"><Icon className="size-3.5" aria-hidden="true" />{label}</p><p className="mt-1 text-sm font-semibold tabular-nums">{value}</p></div>;
}

function buildDistribution<T extends string>(order: readonly T[], colors: string[], values: T[]): DistributionDatum[] {
  return order.map((name, index) => ({ name, value: values.filter((value) => value === name).length, color: colors[index] }));
}
