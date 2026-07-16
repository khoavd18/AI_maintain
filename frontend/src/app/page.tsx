import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CircleCheckBig,
  Gauge,
  Repeat2,
  TicketCheck,
  Wrench,
} from "lucide-react";

import { DataTableShell } from "@/components/data-table-shell";
import { OverviewCharts } from "@/components/dashboard-charts";
import { KpiCard } from "@/components/kpi-card";
import { PageHeader } from "@/components/page-header";
import { MaintenanceBadge, RiskBadge } from "@/components/status-badges";
import { TicketCard } from "@/components/ticket-card";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { assets, overviewKpis, tickets } from "@/lib/mock-data";

const kpiIcons = [Wrench, AlertTriangle, TicketCheck, CircleCheckBig, CalendarClock, Repeat2, Activity, Gauge];

export default function OverviewPage() {
  const topRiskAssets = [...assets].sort((a, b) => b.riskScore - a.riskScore).slice(0, 5);
  const latestTickets = tickets.slice(0, 4);

  return (
    <>
      <PageHeader
        title="Tổng quan bảo trì"
        description="Ưu tiên thiết bị cần kiểm tra từ risk score, ticket và lịch bảo trì trong batch dữ liệu mới nhất."
        breadcrumbs={[{ label: "Tổng quan" }]}
        actions={
          <Button asChild variant="outline">
            <Link href="/assets">
              Xem thiết bị
              <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
        }
      />

      <section aria-label="Chỉ số chính" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {overviewKpis.map((kpi, index) => (
          <KpiCard key={kpi.label} {...kpi} icon={kpiIcons[index]} />
        ))}
      </section>

      <section aria-label="Biểu đồ vận hành" className="mt-6">
        <OverviewCharts />
      </section>

      <section className="mt-6 grid items-start gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(320px,0.8fr)]">
        <DataTableShell
          title="Thiết bị rủi ro cao nhất"
          description="Sắp xếp theo final risk score mới nhất"
          actions={
            <Button asChild variant="ghost" size="sm">
              <Link href="/assets">
                Xem tất cả
                <ArrowRight aria-hidden="true" />
              </Link>
            </Button>
          }
        >
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Thiết bị</TableHead>
                  <TableHead>Vị trí</TableHead>
                  <TableHead>Risk</TableHead>
                  <TableHead>Bảo trì</TableHead>
                  <TableHead className="text-right">Điểm</TableHead>
                  <TableHead><span className="sr-only">Thao tác</span></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {topRiskAssets.map((asset) => (
                  <TableRow key={asset.id}>
                    <TableCell>
                      <p className="font-mono text-xs font-medium text-primary">{asset.id}</p>
                      <p className="mt-1 max-w-52 truncate text-xs text-muted-foreground">{asset.name}</p>
                    </TableCell>
                    <TableCell className="max-w-44 truncate text-muted-foreground">{asset.location}</TableCell>
                    <TableCell><RiskBadge level={asset.riskLevel} /></TableCell>
                    <TableCell><MaintenanceBadge status={asset.maintenanceStatus} /></TableCell>
                    <TableCell className="text-right font-semibold tabular-nums">{asset.riskScore.toFixed(2)}</TableCell>
                    <TableCell className="text-right">
                      <Button asChild variant="ghost" size="icon-sm">
                        <Link href={`/assets/${asset.id}`} aria-label={`Xem ${asset.id}`}>
                          <ArrowRight aria-hidden="true" />
                        </Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </DataTableShell>

        <DataTableShell
          title="Ticket mới nhất"
          description="Các vấn đề cần điều phối gần đây"
          actions={
            <Button asChild variant="ghost" size="sm">
              <Link href="/tickets">Mở workspace</Link>
            </Button>
          }
        >
          <div className="space-y-3 p-4">
            {latestTickets.map((ticket) => (
              <TicketCard key={ticket.id} ticket={ticket} compact />
            ))}
          </div>
        </DataTableShell>
      </section>
    </>
  );
}
