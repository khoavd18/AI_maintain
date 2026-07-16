import { PageHeader } from "@/components/page-header";
import { TicketWorkspace } from "@/components/ticket-workspace";

export default function TicketsPage() {
  return (
    <>
      <PageHeader
        title="Ticket"
        description="Theo dõi vấn đề từ lúc ghi nhận đến khi kỹ thuật viên hoàn tất xử lý."
        breadcrumbs={[{ label: "Tổng quan", href: "/" }, { label: "Ticket" }]}
      />
      <TicketWorkspace />
    </>
  );
}
