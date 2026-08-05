import { PageHeader } from "@/components/page-header";
import { WorkOrderDetail } from "@/components/work-order-detail";

export default async function WorkOrderPage({
  params,
}: {
  params: Promise<{ workOrderId: string }>;
}) {
  const { workOrderId } = await params;
  return (
    <>
      <PageHeader
        title="Chi tiết lệnh công việc"
        description="Thực hiện danh sách kiểm tra, quản lý phụ tùng, gửi hoàn thành và xác nhận độc lập."
        breadcrumbs={[
          { label: "Lệnh công việc", href: "/work-orders" },
          { label: "Chi tiết" },
        ]}
      />
      <WorkOrderDetail workOrderId={workOrderId} />
    </>
  );
}
