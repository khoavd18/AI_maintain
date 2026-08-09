"use client";

import Link from "next/link";
import {
  AlertTriangle,
  Boxes,
  ClipboardList,
  PackageCheck,
} from "lucide-react";

import { KpiCard } from "@/components/kpi-card";
import { Button } from "@/components/ui/button";
import {
  ErrorState,
  LoadingSkeleton,
  RetryButton,
} from "@/components/ui-states";
import {
  useInventoryMetricsQuery,
  useInventoryMovementsQuery,
  useLowStockQuery,
} from "@/hooks/use-inventory";
import { getApiErrorMessage } from "@/lib/api/errors";

import {
  BalanceTable,
  MovementBars,
  MovementTable,
} from "../components/inventory-common";
import { SectionHeading } from "../components/inventory-controls";

export function InventoryOverview() {
  const metrics = useInventoryMetricsQuery();
  const lowStock = useLowStockQuery({ page: 1, page_size: 6 });
  const movements = useInventoryMovementsQuery({ page: 1, page_size: 8 });
  const error = metrics.error ?? lowStock.error ?? movements.error;
  if (metrics.isPending || lowStock.isPending || movements.isPending) {
    return <LoadingSkeleton />;
  }
  if (error || !metrics.data) {
    return (
      <ErrorState
        title="Chưa tải được tổng quan kho"
        description={getApiErrorMessage(error)}
        action={
          <RetryButton
            onClick={() =>
              void Promise.all([
                metrics.refetch(),
                lowStock.refetch(),
                movements.refetch(),
              ])
            }
          />
        }
      />
    );
  }
  const data = metrics.data;
  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Mã phụ tùng đang dùng"
          value={String(data.total_active_parts)}
          detail="Trong danh mục hiện tại"
          icon={Boxes}
          tone="blue"
        />
        <KpiCard
          label="Đã đặt trước"
          value={data.total_reserved_units.toLocaleString("vi-VN")}
          detail="Dành cho lệnh công việc"
          icon={PackageCheck}
          tone="amber"
        />
        <KpiCard
          label="Sắp hết hoặc hết"
          value={String(data.low_stock_parts + data.out_of_stock_parts)}
          detail={`${data.out_of_stock_parts} mã hết hàng`}
          icon={AlertTriangle}
          tone="red"
        />
        <KpiCard
          label="Công việc chờ phụ tùng"
          value={String(data.work_orders_waiting_for_parts)}
          detail={`${data.open_shortages} nhu cầu còn thiếu`}
          icon={ClipboardList}
          tone="orange"
        />
      </div>

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(300px,0.65fr)]">
        <section className="rounded-lg border bg-white">
          <SectionHeading
            title="Cần chú ý"
            description="Các mã cần kiểm tra hoặc bổ sung trước."
            action={
              <Button asChild variant="outline" size="sm">
                <Link href="/inventory/low-stock">Mở hàng đợi</Link>
              </Button>
            }
          />
          <BalanceTable rows={lowStock.data?.items ?? []} />
        </section>
        <section className="rounded-lg border bg-white">
          <SectionHeading
            title="Loại biến động"
            description="Số lần nhập, xuất, trả và điều chuyển."
          />
          <MovementBars counts={data.movements_by_type} />
        </section>
      </div>

      <section className="rounded-lg border bg-white">
        <SectionHeading
          title="Biến động gần đây"
          description="Các thay đổi số lượng mới nhất trong kho."
          action={
            <Button asChild variant="outline" size="sm">
              <Link href="/inventory/movements">Xem toàn bộ</Link>
            </Button>
          }
        />
        <MovementTable rows={movements.data?.items ?? []} />
      </section>
      <p className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs text-blue-900">
        Số lượng khả dụng bằng tồn thực tế trừ số đã đặt trước.
      </p>
    </div>
  );
}
