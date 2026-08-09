"use client";

import { Pencil, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { SlaPolicy } from "@/lib/api/ticketing-schemas";
import { formatDate } from "@/lib/formatters";

export function PolicyList({
  policies,
  canManage,
  onNew,
  onEdit,
}: {
  policies: SlaPolicy[];
  canManage: boolean;
  onNew: () => void;
  onEdit: (policy: SlaPolicy) => void;
}) {
  return (
    <section className="overflow-hidden rounded-lg border bg-white">
      <header className="flex items-center justify-between gap-3 border-b p-4">
        <div>
          <h2 className="text-sm font-semibold">Policy đang cấu hình</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Ticket giữ snapshot; chỉnh policy không viết lại lịch sử.
          </p>
        </div>
        {canManage && (
          <Button type="button" variant="outline" size="sm" onClick={onNew}>
            <Plus aria-hidden="true" />
            Policy mới
          </Button>
        )}
      </header>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Policy</TableHead>
              <TableHead>Calendar</TableHead>
              <TableHead>Hiệu lực</TableHead>
              <TableHead>Due soon</TableHead>
              <TableHead>Trạng thái</TableHead>
              {canManage && <TableHead />}
            </TableRow>
          </TableHeader>
          <TableBody>
            {policies.map((policy) => (
              <TableRow key={policy.id}>
                <TableCell>
                  <p className="font-mono text-xs font-semibold text-primary">{policy.code}</p>
                  <p className="mt-1 text-sm">{policy.name}</p>
                </TableCell>
                <TableCell>{policy.calendar_code}</TableCell>
                <TableCell className="text-xs">
                  {formatDate(policy.effective_from)}
                  {policy.effective_to ? ` – ${formatDate(policy.effective_to)}` : " – không giới hạn"}
                </TableCell>
                <TableCell>{policy.due_soon_percent}%</TableCell>
                <TableCell>
                  <span className={`rounded px-2 py-1 text-xs ${policy.is_active ? "bg-green-50 text-green-700" : "bg-neutral-100 text-neutral-600"}`}>
                    {policy.is_active ? "Đang dùng" : "Ngừng dùng"}
                  </span>
                </TableCell>
                {canManage && (
                  <TableCell className="text-right">
                    <Button type="button" variant="ghost" size="sm" onClick={() => onEdit(policy)}>
                      <Pencil aria-hidden="true" />
                      Sửa
                    </Button>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}
