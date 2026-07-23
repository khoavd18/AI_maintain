import { MaintenancePlanCreateForm } from "@/components/maintenance-plan-workspace";
import { PageHeader } from "@/components/page-header";

export default function NewMaintenancePlanPage() {
  return (
    <>
      <PageHeader
        title="Tạo preventive plan"
        description="Cấu hình lịch định kỳ, checklist và assignee mặc định cho một thiết bị active."
        breadcrumbs={[{ label: "Kế hoạch bảo trì", href: "/maintenance/plans" }, { label: "Tạo mới" }]}
      />
      <MaintenancePlanCreateForm />
    </>
  );
}
