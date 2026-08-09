"use client";

import Link from "next/link";
import { useMemo } from "react";

import { StockStateBadge } from "@/components/inventory-badges";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/ui-states";
import type {
  InventoryBalance,
  InventoryMovement,
} from "@/lib/api/inventory-schemas";
import { formatTimestamp } from "@/lib/formatters";
import { formatQuantity } from "@/lib/inventory";

import { SectionHeading } from "./inventory-controls";

const movementTypeLabels: Record<string, string> = {
  opening_balance: "Số dư ban đầu",
  receipt: "Nhập kho",
  issue: "Xuất kho",
  return: "Trả kho",
  transfer_out: "Điều chuyển đi",
  transfer_in: "Điều chuyển đến",
  adjustment_increase: "Điều chỉnh tăng",
  adjustment_decrease: "Điều chỉnh giảm",
  damaged_scrapped: "Hư hỏng hoặc loại bỏ",
};

export function QuantityCell({
  value,
  symbol,
  strong = false,
}: {
  value: number;
  symbol: string;
  strong?: boolean;
}) {
  return (
    <TableCell className={`text-right tabular-nums ${strong ? "font-semibold" : ""}`}>
      {formatQuantity(value, symbol)}
    </TableCell>
  );
}

export function QuantityTile({
  label,
  value,
  symbol,
}: {
  label: string;
  value: number;
  symbol: string;
}) {
  return (
    <div className="rounded-md bg-neutral-50 p-2">
      <p className="text-muted-foreground">{label}</p>
      <p className="mt-1 font-semibold tabular-nums">
        {formatQuantity(value, symbol)}
      </p>
    </div>
  );
}

export function BalanceTable({ rows }: { rows: InventoryBalance[] }) {
  if (!rows.length) {
    return (
      <EmptyState
        title="Chưa có dữ liệu tồn kho"
        description="Chưa có dữ liệu phù hợp với bộ lọc hiện tại."
      />
    );
  }
  return (
    <>
      <div className="grid gap-3 p-3 md:hidden">
        {rows.map((row) => (
          <article key={row.id} className="rounded-lg border p-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <Link
                  href={`/inventory/parts/${row.part_id}`}
                  className="font-mono text-xs font-semibold text-primary"
                >
                  {row.part_number}
                </Link>
                <p className="mt-1 text-sm font-medium">{row.part_name_vi}</p>
              </div>
              <StockStateBadge
                state={row.stock_state}
                label={row.stock_state_display}
              />
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              {row.stock_location_code} · {row.stock_location_name}
            </p>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
              <QuantityTile
                label="Tồn thực tế"
                value={row.on_hand_quantity}
                symbol={row.unit_symbol}
              />
              <QuantityTile
                label="Đã đặt trước"
                value={row.reserved_quantity}
                symbol={row.unit_symbol}
              />
              <QuantityTile
                label="Khả dụng"
                value={row.available_quantity}
                symbol={row.unit_symbol}
              />
            </div>
          </article>
        ))}
      </div>
      <div className="hidden overflow-x-auto md:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Vật tư</TableHead>
              <TableHead>Vị trí kho</TableHead>
              <TableHead className="text-right">Tồn thực tế</TableHead>
              <TableHead className="text-right">Đã đặt trước</TableHead>
              <TableHead className="text-right">Khả dụng</TableHead>
              <TableHead>Trạng thái</TableHead>
              <TableHead className="text-right">Gợi ý bổ sung</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id}>
                <TableCell>
                  <Link
                    href={`/inventory/parts/${row.part_id}`}
                    className="font-mono text-xs font-semibold text-primary hover:underline"
                  >
                    {row.part_number}
                  </Link>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {row.part_name_vi}
                  </p>
                </TableCell>
                <TableCell>
                  <p className="text-sm font-medium">{row.stock_location_code}</p>
                  <p className="text-xs text-muted-foreground">
                    {row.stock_location_name}
                  </p>
                </TableCell>
                <QuantityCell
                  value={row.on_hand_quantity}
                  symbol={row.unit_symbol}
                />
                <QuantityCell
                  value={row.reserved_quantity}
                  symbol={row.unit_symbol}
                />
                <QuantityCell
                  value={row.available_quantity}
                  symbol={row.unit_symbol}
                  strong
                />
                <TableCell>
                  <StockStateBadge
                    state={row.stock_state}
                    label={row.stock_state_display}
                  />
                </TableCell>
                <QuantityCell
                  value={row.suggested_reorder_quantity}
                  symbol={row.unit_symbol}
                />
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </>
  );
}

export function MovementTable({ rows }: { rows: InventoryMovement[] }) {
  if (!rows.length) {
    return (
      <EmptyState
        title="Chưa có biến động kho"
        description="Không có biến động kho phù hợp với bộ lọc."
      />
    );
  }
  return (
    <>
      <div className="grid gap-3 p-3 md:hidden">
        {rows.map((row) => (
          <article key={row.id} className="rounded-lg border p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="font-mono text-xs font-semibold text-primary">
                  {row.movement_number}
                </p>
                <p className="mt-1 font-mono text-xs">{row.part_number}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {row.part_name_vi}
                </p>
              </div>
              <Badge variant="outline">{row.movement_type_display}</Badge>
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-3 border-y py-3 text-xs">
              <div>
                <dt className="text-muted-foreground">Vị trí kho</dt>
                <dd className="mt-1 font-medium">{row.stock_location_code}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Số lượng</dt>
                <dd className="mt-1 font-semibold tabular-nums">
                  {formatQuantity(row.quantity, row.unit_symbol)}
                </dd>
              </div>
            </dl>
            <div className="mt-3 flex items-end justify-between gap-3 text-xs">
              <div className="min-w-0">
                <p className="truncate">{row.business_reference}</p>
                {row.work_order_number && (
                  <Link
                    href={`/work-orders/${row.work_order_id}`}
                    className="mt-1 block font-mono text-primary hover:underline"
                  >
                    {row.work_order_number}
                  </Link>
                )}
              </div>
              <time className="shrink-0 text-right text-muted-foreground">
                {formatTimestamp(row.occurred_at)}
              </time>
            </div>
          </article>
        ))}
      </div>
      <div className="hidden overflow-x-auto md:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Mã giao dịch</TableHead>
              <TableHead>Vật tư</TableHead>
              <TableHead>Kho</TableHead>
              <TableHead>Loại</TableHead>
              <TableHead className="text-right">Số lượng</TableHead>
              <TableHead>Tham chiếu</TableHead>
              <TableHead>Thời điểm</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="font-mono text-xs font-semibold">
                  {row.movement_number}
                </TableCell>
                <TableCell>
                  <p className="font-mono text-xs">{row.part_number}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {row.part_name_vi}
                  </p>
                </TableCell>
                <TableCell className="text-xs">
                  {row.stock_location_code}
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{row.movement_type_display}</Badge>
                </TableCell>
                <QuantityCell
                  value={row.quantity}
                  symbol={row.unit_symbol}
                  strong
                />
                <TableCell>
                  <p className="max-w-48 truncate text-xs">
                    {row.business_reference}
                  </p>
                  {row.work_order_number && (
                    <Link
                      href={`/work-orders/${row.work_order_id}`}
                      className="mt-1 block font-mono text-xs text-primary hover:underline"
                    >
                      {row.work_order_number}
                    </Link>
                  )}
                </TableCell>
                <TableCell className="whitespace-nowrap text-xs">
                  {formatTimestamp(row.occurred_at)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </>
  );
}

export function MovementBars({ counts }: { counts: Record<string, number> }) {
  const entries = useMemo(
    () => Object.entries(counts).sort((left, right) => right[1] - left[1]),
    [counts],
  );
  const maximum = Math.max(1, ...entries.map(([, count]) => count));
  if (!entries.length) {
    return (
      <EmptyState
        title="Chưa có biến động kho"
        description="Biểu đồ sẽ xuất hiện sau giao dịch kho đầu tiên."
      />
    );
  }
  return (
    <div className="space-y-3 p-4">
      {entries.map(([type, count]) => (
        <div key={type}>
          <div className="mb-1 flex items-center justify-between gap-3 text-xs">
            <span>{movementTypeLabels[type] ?? type.replaceAll("_", " ")}</span>
            <span className="font-semibold tabular-nums">{count}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-neutral-100">
            <div
              className="h-full rounded-full bg-primary"
              style={{ width: `${Math.max(4, (count / maximum) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ReferenceList({
  title,
  items,
}: {
  title: string;
  items: Array<{
    code: string;
    name: string;
    detail: string;
    active: boolean;
  }>;
}) {
  return (
    <section className="rounded-lg border bg-white">
      <SectionHeading title={title} description={`${items.length} bản ghi`} />
      <div className="divide-y">
        {items.map((item) => (
          <div key={item.code} className="flex items-start justify-between gap-3 p-3">
            <div className="min-w-0">
              <p className="font-mono text-xs font-semibold">{item.code}</p>
              <p className="mt-1 text-sm font-medium">{item.name}</p>
              <p className="mt-1 truncate text-xs text-muted-foreground">
                {item.detail}
              </p>
            </div>
            <Badge variant={item.active ? "default" : "outline"}>
              {item.active ? "Active" : "Inactive"}
            </Badge>
          </div>
        ))}
      </div>
    </section>
  );
}
