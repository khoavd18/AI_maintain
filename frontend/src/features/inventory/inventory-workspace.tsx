"use client";

import { InventorySectionNav } from "@/components/inventory-section-nav";
import { PageHeader } from "@/components/page-header";

import { BalanceWorkspace } from "./sections/balance";
import { InventoryOverview } from "./sections/overview";
import { MovementWorkspace } from "./sections/movements";
import { ReservationWorkspace } from "./sections/reservations";
import { InventorySettings } from "./sections/settings";

export type InventoryWorkspaceView =
  | "overview"
  | "stock"
  | "low-stock"
  | "movements"
  | "reservations"
  | "settings";

const titles: Record<
  InventoryWorkspaceView,
  { title: string; description: string }
> = {
  overview: {
    title: "Kho phụ tùng",
    description: "Theo dõi số lượng khả dụng, phụ tùng sắp hết và nhu cầu cho công việc.",
  },
  stock: {
    title: "Tồn kho",
    description: "Xem số lượng thực tế, đã đặt trước và còn có thể sử dụng tại từng kho.",
  },
  "low-stock": {
    title: "Phụ tùng sắp hết",
    description: "Ưu tiên các mã đã xuống dưới mức tồn tối thiểu hoặc đã hết hàng.",
  },
  movements: {
    title: "Lịch sử kho",
    description: "Tra cứu các lần nhập, xuất, trả, điều chuyển và điều chỉnh.",
  },
  reservations: {
    title: "Đặt trước phụ tùng",
    description: "Theo dõi phụ tùng đã dành cho lệnh công việc và xử lý yêu cầu còn mở.",
  },
  settings: {
    title: "Thiết lập kho",
    description: "Quản lý phân loại, đơn vị tính và các vị trí lưu kho.",
  },
};

export function InventoryWorkspace({
  view,
}: {
  view: InventoryWorkspaceView;
}) {
  const heading = titles[view];
  return (
    <div>
      <PageHeader
        title={heading.title}
        description={heading.description}
        breadcrumbs={[
          { label: "Tổng quan", href: "/" },
          { label: "Kho phụ tùng" },
        ]}
      />
      <InventorySectionNav />
      {view === "overview" && <InventoryOverview />}
      {view === "stock" && <BalanceWorkspace lowStockOnly={false} />}
      {view === "low-stock" && <BalanceWorkspace lowStockOnly />}
      {view === "movements" && <MovementWorkspace />}
      {view === "reservations" && <ReservationWorkspace />}
      {view === "settings" && <InventorySettings />}
    </div>
  );
}
