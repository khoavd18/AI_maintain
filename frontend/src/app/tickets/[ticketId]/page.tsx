import { PageHeader } from "@/components/page-header";
import { TicketOperationsDetail } from "@/components/ticket-operations-detail";

export default async function TicketDetailPage({
  params,
}: {
  params: Promise<{ ticketId: string }>;
}) {
  const { ticketId } = await params;
  return (
    <>
      <PageHeader
        title="Chi tiết ticket"
        description="Lifecycle, SLA, communication và corrective work order được theo dõi độc lập, có audit."
        breadcrumbs={[
          { label: "Phiếu sự cố", href: "/tickets" },
          { label: ticketId },
        ]}
      />
      <TicketOperationsDetail ticketId={ticketId} />
    </>
  );
}
