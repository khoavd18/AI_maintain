import { PageHeader } from "@/components/page-header";
import { WorkOrderDetail } from "@/components/work-order-detail";

export default async function WorkOrderPage({ params }: { params: Promise<{ workOrderId: string }> }) {
  const { workOrderId } = await params;
  return (
    <>
      <PageHeader
        title="Chi tiết work order"
        description="Workflow có version, checklist snapshot, MaintenanceLog và bước xác minh độc lập."
        breadcrumbs={[{ label: "Work order", href: "/work-orders" }, { label: "Chi tiết" }]}
      />
      <WorkOrderDetail workOrderId={workOrderId} />
    </>
  );
}
