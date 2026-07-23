import { PageHeader } from "@/components/page-header";
import { WorkOrderWorkspace } from "@/components/work-order-workspace";

export default function WorkOrdersPage() {
  return (
    <>
      <PageHeader
        title="Phiếu công việc"
        description="Phân công, thực thi, ghi checklist, hoàn tất và xác minh công việc bảo trì."
        breadcrumbs={[{ label: "Tổng quan", href: "/" }, { label: "Phiếu công việc" }]}
      />
      <WorkOrderWorkspace />
    </>
  );
}
