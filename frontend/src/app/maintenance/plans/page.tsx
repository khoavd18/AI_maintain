import { MaintenancePlanWorkspace } from "@/components/maintenance-plan-workspace";
import { PageHeader } from "@/components/page-header";

export default function MaintenancePlansPage() {
  return (
    <>
      <PageHeader
        title="Bảo trì định kỳ"
        description="Theo dõi lịch bảo trì, kỳ sắp đến hạn và lệnh công việc đã phát hành."
        breadcrumbs={[{ label: "Tổng quan", href: "/" }, { label: "Bảo trì định kỳ" }]}
      />
      <MaintenancePlanWorkspace />
    </>
  );
}
