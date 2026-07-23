import { MaintenancePlanWorkspace } from "@/components/maintenance-plan-workspace";
import { PageHeader } from "@/components/page-header";

export default function MaintenancePlansPage() {
  return (
    <>
      <PageHeader
        title="Kế hoạch bảo trì"
        description="Quản lý preventive plan, xem kỳ đến hạn và phát hành work order theo lịch xác định."
        breadcrumbs={[{ label: "Tổng quan", href: "/" }, { label: "Kế hoạch bảo trì" }]}
      />
      <MaintenancePlanWorkspace />
    </>
  );
}
