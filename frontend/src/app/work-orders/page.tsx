import { PageHeader } from "@/components/page-header";
import { WorkOrderWorkspace } from "@/components/work-order-workspace";

export default function WorkOrdersPage() {
  return (
    <>
      <PageHeader
        title="Lệnh công việc"
        description="Theo dõi việc được giao, thời hạn và bước cần thực hiện tiếp theo."
        breadcrumbs={[{ label: "Tổng quan", href: "/" }, { label: "Lệnh công việc" }]}
      />
      <WorkOrderWorkspace />
    </>
  );
}
