import { redirect } from "next/navigation";

import { PageHeader } from "@/components/page-header";
import { TicketInbox } from "@/components/ticket-inbox";

export default async function TicketsPage({
  searchParams,
}: {
  searchParams: Promise<{ asset?: string; action?: string; ticket?: string }>;
}) {
  const { asset, action, ticket } = await searchParams;
  if (ticket) redirect(`/tickets/${encodeURIComponent(ticket)}`);
  if (action === "create") {
    redirect(asset ? `/tickets/new?asset=${encodeURIComponent(asset)}` : "/tickets/new");
  }

  return (
    <>
      <PageHeader
        title="Phiếu sự cố"
        description="Inbox vận hành theo queue, priority và SLA; mọi chuyển trạng thái đi qua action nghiệp vụ rõ ràng."
        breadcrumbs={[{ label: "Tổng quan", href: "/" }, { label: "Phiếu sự cố" }]}
      />
      <TicketInbox />
    </>
  );
}
