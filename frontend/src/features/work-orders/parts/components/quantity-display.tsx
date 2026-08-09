"use client";

import {
  Boxes,
  CheckCircle2,
  PackageCheck,
  ShieldCheck,
} from "lucide-react";

import type { WorkOrderPartsSummary } from "@/lib/api/inventory-schemas";

export function PartsKpis({ summary }: { summary: WorkOrderPartsSummary }) {
  const metrics = [
    {
      label: "Kế hoạch",
      value: summary.total_planned_quantity,
      icon: Boxes,
    },
    {
      label: "Đã giữ",
      value: summary.total_reserved_quantity,
      icon: ShieldCheck,
    },
    {
      label: "Đã xuất",
      value: summary.total_issued_quantity,
      icon: PackageCheck,
    },
    {
      label: "Đã sử dụng",
      value: summary.net_consumed_quantity,
      icon: CheckCircle2,
    },
  ];
  return (
    <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {metrics.map(({ label, value, icon: Icon }) => (
        <div key={label} className="rounded-md border p-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-muted-foreground">{label}</p>
            <Icon className="size-4 text-primary" aria-hidden="true" />
          </div>
          <p className="mt-1 text-xl font-semibold">
            {new Intl.NumberFormat("vi-VN", {
              maximumFractionDigits: 3,
            }).format(value)}
          </p>
        </div>
      ))}
    </div>
  );
}

export function SummaryFact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-sm font-semibold tabular-nums">{value}</dd>
    </div>
  );
}
