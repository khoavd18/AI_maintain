import { StatusBadge } from "@/components/status-badges";
import {
  inventoryLifecycleStatusCatalog,
  inventoryStatusCatalog,
  resolveStatusPresentation,
  stockStateStatusCatalog,
} from "@/lib/status-terminology";

export function StockStateBadge({
  state,
  label,
}: {
  state: string;
  label: string;
}) {
  return <StatusBadge presentation={resolveStatusPresentation(stockStateStatusCatalog, state, label)} />;
}

export function InventoryStatusBadge({
  status,
  label,
  context = "operation",
}: {
  status: string;
  label: string;
  context?: "lifecycle" | "operation";
}) {
  const catalog =
    context === "lifecycle"
      ? inventoryLifecycleStatusCatalog
      : inventoryStatusCatalog;
  return <StatusBadge presentation={resolveStatusPresentation(catalog, status, label)} />;
}
