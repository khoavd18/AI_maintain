import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const stockTones: Record<string, string> = {
  healthy: "bg-green-50 text-green-700 ring-green-200",
  low_stock: "bg-amber-50 text-amber-800 ring-amber-200",
  at_reorder_point: "bg-orange-50 text-orange-800 ring-orange-200",
  out_of_stock: "bg-red-50 text-red-700 ring-red-200",
  overstock: "bg-blue-50 text-blue-700 ring-blue-200",
};

const statusTones: Record<string, string> = {
  active: "bg-green-50 text-green-700 ring-green-200",
  partially_issued: "bg-amber-50 text-amber-800 ring-amber-200",
  fulfilled: "bg-green-50 text-green-700 ring-green-200",
  reserved: "bg-blue-50 text-blue-700 ring-blue-200",
  partially_reserved: "bg-amber-50 text-amber-800 ring-amber-200",
  planned: "bg-neutral-100 text-neutral-700 ring-neutral-200",
  issued: "bg-blue-50 text-blue-700 ring-blue-200",
  partially_consumed: "bg-amber-50 text-amber-800 ring-amber-200",
  released: "bg-neutral-100 text-neutral-700 ring-neutral-200",
  expired: "bg-red-50 text-red-700 ring-red-200",
  replaced: "bg-neutral-100 text-neutral-700 ring-neutral-200",
  inactive: "bg-neutral-100 text-neutral-700 ring-neutral-200",
  archived: "bg-neutral-100 text-neutral-600 ring-neutral-200",
};

export function StockStateBadge({
  state,
  label,
}: {
  state: string;
  label: string;
}) {
  return (
    <Badge className={cn("ring-1", stockTones[state] ?? statusTones.planned)}>
      {label}
    </Badge>
  );
}

export function InventoryStatusBadge({
  status,
  label,
}: {
  status: string;
  label: string;
}) {
  return (
    <Badge className={cn("ring-1", statusTones[status] ?? statusTones.planned)}>
      {label}
    </Badge>
  );
}
