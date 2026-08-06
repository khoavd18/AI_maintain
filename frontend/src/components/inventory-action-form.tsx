"use client";

import { InventorySectionNav } from "@/components/inventory-section-nav";
import { PageHeader } from "@/components/page-header";
import { ErrorState, LoadingSkeleton } from "@/components/ui-states";
import { useInventoryLocationsQuery, useInventoryPartsQuery } from "@/hooks/use-inventory";
import { getApiErrorMessage } from "@/lib/api/errors";
import { AdjustmentForm } from "@/components/inventory/actions/adjustment-form";
import { ReceivingForm } from "@/components/inventory/actions/receiving-form";
import { TransferForm } from "@/components/inventory/actions/transfer-form";

export type InventoryActionView = "receiving" | "transfer" | "adjustment";

const copy: Record<
  InventoryActionView,
  { title: string; description: string }
> = {
  receiving: {
    title: "Nhập kho",
    description: "Ghi nhận phụ tùng nhập vào kho hoặc số lượng đầu kỳ.",
  },
  transfer: {
    title: "Điều chuyển kho",
    description: "Chuyển phụ tùng giữa hai vị trí kho trong một thao tác.",
  },
  adjustment: {
    title: "Điều chỉnh tồn",
    description: "Ghi nhận chênh lệch kiểm kê, hư hỏng hoặc loại bỏ có lý do.",
  },
};
export function InventoryActionForm({ view }: { view: InventoryActionView }) {
  const heading = copy[view];
  const parts = useInventoryPartsQuery({
    lifecycle_status: "active",
    page: 1,
    page_size: 200,
  });
  const locations = useInventoryLocationsQuery();
  if (parts.isPending || locations.isPending) return <LoadingSkeleton />;
  const error = parts.error ?? locations.error;
  if (error || !parts.data) {
    return (
      <ErrorState
        title="Chưa tải được dữ liệu biểu mẫu"
        description={getApiErrorMessage(error)}
      />
    );
  }
  return (
    <div>
      <PageHeader
        title={heading.title}
        description={heading.description}
        breadcrumbs={[
          { label: "Kho phụ tùng", href: "/inventory" },
          { label: heading.title },
        ]}
      />
      <InventorySectionNav />
      {view === "receiving" && (
        <ReceivingForm parts={parts.data.items} locations={locations.data ?? []} />
      )}
      {view === "transfer" && (
        <TransferForm parts={parts.data.items} locations={locations.data ?? []} />
      )}
      {view === "adjustment" && (
        <AdjustmentForm
          parts={parts.data.items}
          locations={locations.data ?? []}
        />
      )}
    </div>
  );
}
