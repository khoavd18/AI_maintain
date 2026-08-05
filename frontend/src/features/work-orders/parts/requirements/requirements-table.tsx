"use client";

import { InventoryStatusBadge } from "@/components/inventory-badges";
import { EmptyState } from "@/components/ui-states";
import { formatQuantity } from "@/lib/inventory";
import type { Requirement } from "@/lib/api/inventory-schemas";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export function RequirementsTable({
  requirements,
}: {
  requirements: Requirement[];
}) {
  if (!requirements.length) {
    return (
      <EmptyState
        title="Chưa có nhu cầu vật tư"
        description="Kỹ sư phụ trách có thể thêm nhu cầu phụ tùng cho công việc."
      />
    );
  }
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Vật tư</TableHead>
            <TableHead>Kho nguồn</TableHead>
            <TableHead>Trạng thái</TableHead>
            <TableHead className="text-right">Kế hoạch</TableHead>
            <TableHead className="text-right">Đã giữ</TableHead>
            <TableHead className="text-right">Đã xuất</TableHead>
            <TableHead className="text-right">Thiếu</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {requirements.map((item) => (
            <TableRow key={item.id}>
              <TableCell>
                <p className="font-medium">{item.part_name_vi}</p>
                <p className="font-mono text-xs text-muted-foreground">
                  {item.part_number}
                </p>
              </TableCell>
              <TableCell>{item.source_stock_location_name}</TableCell>
              <TableCell>
                <InventoryStatusBadge
                  status={item.status}
                  label={item.status_display}
                />
              </TableCell>
              <TableCell className="text-right">
                {formatQuantity(item.planned_quantity, item.unit_symbol)}
              </TableCell>
              <TableCell className="text-right">
                {formatQuantity(item.reserved_quantity, item.unit_symbol)}
              </TableCell>
              <TableCell className="text-right">
                {formatQuantity(item.issued_quantity, item.unit_symbol)}
              </TableCell>
              <TableCell className="text-right font-medium text-red-700">
                {formatQuantity(item.shortage_quantity, item.unit_symbol)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
