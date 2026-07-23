import { MaintenancePlanDetail } from "@/components/maintenance-plan-detail";
import { PageHeader } from "@/components/page-header";

export default async function MaintenancePlanPage({ params }: { params: Promise<{ planId: string }> }) {
  const { planId } = await params;
  return (
    <>
      <PageHeader
        title="Chi tiết kế hoạch"
        description="Theo dõi cấu hình, occurrence và work order đã phát hành mà không viết lại lịch sử."
        breadcrumbs={[{ label: "Kế hoạch bảo trì", href: "/maintenance/plans" }, { label: "Chi tiết" }]}
      />
      <MaintenancePlanDetail planId={planId} />
    </>
  );
}
