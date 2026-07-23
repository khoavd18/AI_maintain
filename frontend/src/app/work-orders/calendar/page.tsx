import { PageHeader } from "@/components/page-header";
import { WorkOrderCalendar } from "@/components/work-order-calendar";

export default function WorkOrderCalendarPage() {
  return (
    <>
      <PageHeader
        title="Lịch bảo trì"
        description="Xem occurrence sắp tới, work order đã phát hành và công việc quá hạn trong một date range có giới hạn."
        breadcrumbs={[{ label: "Work order", href: "/work-orders" }, { label: "Lịch" }]}
      />
      <WorkOrderCalendar />
    </>
  );
}
