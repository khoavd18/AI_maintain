"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  ChevronRight,
  ClipboardList,
  PackageOpen,
  TicketCheck,
  TicketPlus,
  Wrench,
} from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { DataTableShell } from "@/components/data-table-shell";
import { KpiCard } from "@/components/kpi-card";
import {
  OverviewStatusCard,
  type OverviewStatusSegment,
} from "@/components/overview-status-card";
import { PageHeader } from "@/components/page-header";
import {
  MaintenanceBadge,
  PriorityBadge,
  RiskBadge,
  TicketStatusBadge,
} from "@/components/status-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  EmptyState,
  ErrorState,
  LoadingSkeleton,
  RetryButton,
} from "@/components/ui-states";
import {
  useAssetsQuery,
  useMaintenanceKpisQuery,
  useTicketsQuery,
  useWorkOrderMetricsQuery,
} from "@/hooks/use-api-queries";
import { useInventoryMetricsQuery } from "@/hooks/use-inventory";
import { adaptAsset, adaptTicket } from "@/lib/adapters";
import { getApiErrorMessage } from "@/lib/api/errors";
import { permissions } from "@/lib/auth";
import { formatDate } from "@/lib/formatters";
import { todayIso } from "@/lib/maintenance";

export default function OverviewPage() {
  const auth = useAuth();
  const assetsQuery = useAssetsQuery();
  const ticketsQuery = useTicketsQuery({ limit: 3 });
  const kpisQuery = useMaintenanceKpisQuery();
  const canReadWorkOrders = auth.can(permissions.workOrdersRead);
  const canReadInventory = auth.can(permissions.inventoryRead);
  const workOrderMetrics = useWorkOrderMetricsQuery(todayIso(), canReadWorkOrders);
  const inventoryMetrics = useInventoryMetricsQuery(canReadInventory);
  const requiredQueries = [assetsQuery, ticketsQuery, kpisQuery];

  if (requiredQueries.some((query) => query.isPending)) {
    return <LoadingSkeleton />;
  }

  const failedQuery = requiredQueries.find((query) => query.isError);
  if (failedQuery) {
    return (
      <ErrorState
        title="Chưa tải được tổng quan"
        description={getApiErrorMessage(failedQuery.error)}
        action={
          <RetryButton
            onClick={() =>
              void Promise.all(requiredQueries.map((query) => query.refetch()))
            }
          />
        }
      />
    );
  }

  if (!assetsQuery.data || !ticketsQuery.data || !kpisQuery.data) {
    return <LoadingSkeleton />;
  }

  const assets = assetsQuery.data.map(adaptAsset);
  const tickets = ticketsQuery.data.map(adaptTicket);
  const kpis = kpisQuery.data;
  const priorityAssets = assets
    .filter((asset) => asset.riskScore !== null)
    .sort((left, right) => (right.riskScore ?? -1) - (left.riskScore ?? -1))
    .slice(0, 5);
  const latestTickets = tickets.slice(0, 3);
  const ticketSegments = buildTicketSegments(
    kpis.total_tickets,
    kpis.open_tickets,
    kpis.resolved_tickets,
  );
  const riskSegments = buildRiskSegments(
    assets.length,
    kpis.high_critical_risk_asset_count,
  );

  return (
    <>
      <PageHeader
        title="Tổng quan bảo trì"
        description={`Xin chào ${auth.user?.display_name ?? "bạn"}. Đây là các hạng mục cần xem xét trong ca làm việc hiện tại.`}
        breadcrumbs={[{ label: "Tổng quan" }]}
        actions={
          auth.can(permissions.ticketsCreate) ? (
            <Button asChild>
              <Link href="/tickets/new">
                <TicketPlus aria-hidden="true" />
                Báo sự cố
              </Link>
            </Button>
          ) : (
            <Button asChild variant="outline">
              <Link href="/assets">
                Xem thiết bị
                <ArrowRight aria-hidden="true" />
              </Link>
            </Button>
          )
        }
      />

      <section
        aria-labelledby="attention-summary-title"
        className="rounded-xl border bg-white p-4 shadow-[0_4px_20px_rgba(15,23,42,0.04)] sm:p-5"
      >
        <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 id="attention-summary-title" className="text-sm font-semibold text-slate-900">
              Cần chú ý
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Dữ liệu phân tích được cập nhật đến {formatDate(kpis.as_of_date)}.
            </p>
          </div>
          <Badge variant="outline" className="bg-blue-50 text-blue-700">
            Hỗ trợ sắp xếp ưu tiên
          </Badge>
        </div>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <KpiCard
            href="/tickets"
            label="Sự cố cần xử lý"
            value={String(kpis.open_tickets)}
            detail="Mở danh sách sự cố"
            icon={TicketCheck}
            tone="amber"
          />
          <KpiCard
            href="/assets"
            label="Thiết bị quá hạn bảo trì"
            value={String(kpis.overdue_asset_count)}
            detail="Kiểm tra lịch bảo trì"
            icon={CalendarClock}
            tone="orange"
          />
          {canReadWorkOrders && workOrderMetrics.data ? (
            <KpiCard
              href="/work-orders"
              label="Lệnh công việc quá hạn"
              value={String(workOrderMetrics.data.overdue_count)}
              detail="Mở danh sách công việc"
              icon={ClipboardList}
              tone="red"
            />
          ) : canReadWorkOrders ? (
            <KpiCard
              href="/work-orders"
              label="Lệnh công việc"
              value="—"
              detail="Mở danh sách công việc"
              icon={ClipboardList}
              tone="blue"
            />
          ) : (
            <KpiCard
              href="/assets"
              label="Thiết bị ưu tiên cao"
              value={String(kpis.high_critical_risk_asset_count)}
              detail="Mức Cao hoặc Khẩn cấp"
              icon={AlertTriangle}
              tone="red"
            />
          )}
          {canReadInventory && inventoryMetrics.data ? (
            <KpiCard
              href="/inventory/low-stock"
              label="Phụ tùng sắp hết hoặc hết"
              value={String(
                inventoryMetrics.data.low_stock_parts +
                  inventoryMetrics.data.out_of_stock_parts,
              )}
              detail="Mở danh sách cần kiểm tra"
              icon={PackageOpen}
              tone="orange"
            />
          ) : canReadInventory ? (
            <KpiCard
              href="/inventory/low-stock"
              label="Tình trạng phụ tùng"
              value="—"
              detail="Mở danh sách cần kiểm tra"
              icon={PackageOpen}
              tone="blue"
            />
          ) : (
            <KpiCard
              href="/assets"
              label="Thiết bị đang theo dõi"
              value={String(assets.length)}
              detail="Mở danh mục thiết bị"
              icon={Wrench}
              tone="blue"
            />
          )}
        </div>
      </section>

      <div className="mt-5 grid items-start gap-5 xl:grid-cols-[minmax(0,1.65fr)_minmax(300px,0.62fr)]">
        <div className="min-w-0 space-y-5">
          <PriorityAssetQueue
            assets={priorityAssets}
            canCreateTicket={auth.can(permissions.ticketsCreate)}
          />

          <DataTableShell
            title="Sự cố mới tạo"
            description="Ba phiếu gần nhất cần điều phối hoặc theo dõi"
            actions={
              <Button asChild variant="ghost" size="sm">
                <Link href="/tickets">
                  Xem tất cả
                  <ArrowRight aria-hidden="true" />
                </Link>
              </Button>
            }
          >
            {latestTickets.length ? (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Phiếu</TableHead>
                      <TableHead>Vấn đề</TableHead>
                      <TableHead>Trạng thái</TableHead>
                      <TableHead>Phụ trách</TableHead>
                      <TableHead>Ưu tiên</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {latestTickets.map((ticket) => (
                      <TableRow key={ticket.id}>
                        <TableCell>
                          <Link
                            href={`/tickets/${ticket.id}`}
                            className="font-mono text-xs font-medium text-primary hover:underline"
                          >
                            {ticket.id}
                          </Link>
                          <p className="mt-1 font-mono text-xs text-muted-foreground">
                            {ticket.assetId}
                          </p>
                        </TableCell>
                        <TableCell className="max-w-md font-medium">{ticket.summary}</TableCell>
                        <TableCell><TicketStatusBadge status={ticket.status} /></TableCell>
                        <TableCell>{ticket.technician}</TableCell>
                        <TableCell><PriorityBadge priority={ticket.priority} /></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ) : (
              <EmptyState
                title="Chưa có sự cố"
                description="Các phiếu sự cố mới sẽ xuất hiện tại đây."
              />
            )}
          </DataTableShell>
        </div>

        <aside aria-label="Tình trạng vận hành" className="space-y-4 xl:sticky xl:top-20">
          {canReadWorkOrders && workOrderMetrics.data && (
            <OverviewStatusCard
              title="Tình trạng lệnh công việc"
              description="Phân bố theo trạng thái thực hiện hiện tại."
              href="/work-orders"
              segments={buildWorkOrderSegments(workOrderMetrics.data.by_status)}
            />
          )}

          <OverviewStatusCard
            title="Tình trạng sự cố"
            description="Phiếu đang mở vẫn cần con người điều phối và quyết định xử lý."
            href="/tickets"
            segments={ticketSegments}
          />

          {canReadInventory && inventoryMetrics.data ? (
            <OverviewStatusCard
              title="Tình trạng phụ tùng"
              description="Tổng hợp trạng thái khả dụng từ số dư và ngưỡng kho."
              href="/inventory/low-stock"
              segments={buildInventorySegments(
                inventoryMetrics.data.total_active_parts,
                inventoryMetrics.data.low_stock_parts,
                inventoryMetrics.data.out_of_stock_parts,
              )}
            />
          ) : (
            <OverviewStatusCard
              title="Mức ưu tiên thiết bị"
              description="Chỉ số dùng để sắp xếp kiểm tra, không phải xác suất hỏng."
              href="/assets"
              segments={riskSegments}
            />
          )}

          <section className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-950">
            <div className="flex items-start gap-3">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-blue-100 text-blue-700">
                <Wrench className="size-4" aria-hidden="true" />
              </span>
              <div>
                <h2 className="font-semibold">Quyết định vẫn thuộc về con người</h2>
                <p className="mt-1 text-xs leading-5 text-blue-900/75">
                  Kiểm tra hiện trường, điều kiện an toàn và khả năng thực hiện trước khi hành động.
                </p>
              </div>
            </div>
          </section>
        </aside>
      </div>
    </>
  );
}

interface PriorityAsset {
  id: string;
  name: string;
  riskScore: number | null;
  riskLevel: "Thấp" | "Trung bình" | "Cao" | "Khẩn cấp" | null;
  maintenanceStatus: "Chưa đến hạn" | "Sắp đến hạn" | "Quá hạn" | null;
  contributingFactors: string;
}

function PriorityAssetQueue({
  assets,
  canCreateTicket,
}: {
  assets: PriorityAsset[];
  canCreateTicket: boolean;
}) {
  return (
    <section
      aria-labelledby="priority-assets-title"
      className="overflow-hidden rounded-xl border bg-white shadow-[0_4px_20px_rgba(15,23,42,0.04)]"
    >
      <header className="flex flex-col justify-between gap-3 border-b bg-slate-50/80 px-4 py-4 sm:flex-row sm:items-center sm:px-5">
        <div>
          <div className="flex items-center gap-2">
            <AlertTriangle className="size-4 text-orange-600" aria-hidden="true" />
            <h2 id="priority-assets-title" className="text-sm font-semibold text-slate-900">
              Thiết bị có chỉ số ưu tiên cao nhất
            </h2>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Sắp xếp theo chỉ số ưu tiên của đợt phân tích hiện tại.
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href="/assets">
            Tất cả thiết bị
            <ArrowRight aria-hidden="true" />
          </Link>
        </Button>
      </header>

      {assets.length ? (
        <div className="divide-y">
          {assets.map((asset, index) => (
            <article
              key={asset.id}
              className="grid gap-3 px-4 py-4 transition-colors hover:bg-slate-50/70 sm:px-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(190px,0.8fr)_minmax(130px,0.45fr)_auto] lg:items-center"
            >
              <div className="flex min-w-0 items-center gap-3">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border bg-slate-50 text-slate-500">
                  <Wrench className="size-4" aria-hidden="true" />
                </span>
                <div className="min-w-0">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-orange-600">
                    Ưu tiên {index + 1}
                  </p>
                  <Link
                    href={`/assets/${asset.id}`}
                    className="mt-0.5 block truncate font-mono text-xs font-semibold text-primary hover:underline"
                  >
                    {asset.id}
                  </Link>
                  <p className="mt-0.5 truncate text-xs text-muted-foreground">{asset.name}</p>
                </div>
              </div>

              <p className="line-clamp-2 text-xs leading-5 text-muted-foreground">
                {asset.contributingFactors}
              </p>

              <div className="flex items-center justify-between gap-3 lg:block lg:text-right">
                <p className="text-lg font-semibold tabular-nums text-slate-900">
                  {asset.riskScore?.toFixed(2) ?? "—"}
                </p>
                <div className="flex flex-wrap items-center gap-1.5 lg:mt-1 lg:justify-end">
                  {asset.riskLevel && <RiskBadge level={asset.riskLevel} />}
                  {asset.maintenanceStatus && (
                    <MaintenanceBadge status={asset.maintenanceStatus} />
                  )}
                </div>
              </div>

              {canCreateTicket ? (
                <Button asChild size="sm">
                  <Link href={`/tickets?asset=${asset.id}&action=create`}>Báo sự cố</Link>
                </Button>
              ) : (
                <Button asChild variant="outline" size="sm">
                  <Link href={`/assets/${asset.id}`}>
                    Xem thiết bị
                    <ChevronRight aria-hidden="true" />
                  </Link>
                </Button>
              )}
            </article>
          ))}
        </div>
      ) : (
        <EmptyState
          title="Chưa có thiết bị được xếp hạng"
          description="Kết quả sẽ xuất hiện sau khi hoàn tất đợt phân tích dữ liệu."
        />
      )}
    </section>
  );
}

function buildWorkOrderSegments(byStatus: Record<string, number>): OverviewStatusSegment[] {
  return [
    {
      label: "Chờ thực hiện",
      value: (byStatus.planned ?? 0) + (byStatus.assigned ?? 0),
      color: "#60a5fa",
    },
    {
      label: "Đang thực hiện",
      value: (byStatus.in_progress ?? 0) + (byStatus.on_hold ?? 0),
      color: "#fb923c",
    },
    { label: "Chờ xác nhận", value: byStatus.completed ?? 0, color: "#facc15" },
    { label: "Đã xác nhận", value: byStatus.verified ?? 0, color: "#22c55e" },
    { label: "Đã hủy", value: byStatus.cancelled ?? 0, color: "#94a3b8" },
  ];
}

function buildTicketSegments(
  total: number,
  open: number,
  resolved: number,
): OverviewStatusSegment[] {
  return [
    { label: "Cần xử lý", value: open, color: "#fb923c" },
    { label: "Đã xử lý", value: resolved, color: "#22c55e" },
    {
      label: "Trạng thái khác",
      value: Math.max(total - open - resolved, 0),
      color: "#60a5fa",
    },
  ];
}

function buildInventorySegments(
  total: number,
  lowStock: number,
  outOfStock: number,
): OverviewStatusSegment[] {
  return [
    {
      label: "Còn hàng",
      value: Math.max(total - lowStock - outOfStock, 0),
      color: "#22c55e",
    },
    { label: "Sắp hết", value: lowStock, color: "#f59e0b" },
    { label: "Hết hàng", value: outOfStock, color: "#ef4444" },
  ];
}

function buildRiskSegments(total: number, highPriority: number): OverviewStatusSegment[] {
  return [
    { label: "Cao hoặc Khẩn cấp", value: highPriority, color: "#ef4444" },
    {
      label: "Mức khác hoặc chưa có",
      value: Math.max(total - highPriority, 0),
      color: "#60a5fa",
    },
  ];
}
