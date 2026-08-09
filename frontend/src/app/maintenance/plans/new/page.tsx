import { MaintenancePlanCreateForm } from "@/components/maintenance-plan-workspace";
import { PageHeader } from "@/components/page-header";

export default function NewMaintenancePlanPage() {
  return (
    <>
      <PageHeader
        title="Tạo kế hoạch bảo trì"
        description="Chọn thiết bị, chu kỳ, người phụ trách và danh sách kiểm tra."
        breadcrumbs={[{ label: "Kế hoạch bảo trì", href: "/maintenance/plans" }, { label: "Tạo mới" }]}
      />
      <MaintenancePlanCreateForm />
    </>
  );
}
