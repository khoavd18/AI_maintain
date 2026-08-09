import { MaintenancePlanDetail } from "@/components/maintenance-plan-detail";
import { PageHeader } from "@/components/page-header";

export default async function MaintenancePlanPage({ params }: { params: Promise<{ planId: string }> }) {
  const { planId } = await params;
  return (
    <>
      <PageHeader
        title="Chi tiết kế hoạch"
        description="Xem lịch sắp tới, lệnh công việc đã tạo và điều chỉnh các kỳ chưa phát hành."
        breadcrumbs={[{ label: "Kế hoạch bảo trì", href: "/maintenance/plans" }, { label: "Chi tiết" }]}
      />
      <MaintenancePlanDetail planId={planId} />
    </>
  );
}
