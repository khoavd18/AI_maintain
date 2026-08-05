import { PageHeader } from "@/components/page-header";
import { TicketOperationsDetail } from "@/features/tickets/detail/ticket-detail";

export default async function TicketDetailPage({
  params,
}: {
  params: Promise<{ ticketId: string }>;
}) {
  const { ticketId } = await params;
  return (
    <>
      <PageHeader
        title="Chi tiết sự cố"
        description="Xem tình trạng, người phụ trách, thời hạn và hành động tiếp theo."
        breadcrumbs={[
          { label: "Phiếu sự cố", href: "/tickets" },
          { label: ticketId },
        ]}
      />
      <TicketOperationsDetail ticketId={ticketId} />
    </>
  );
}
