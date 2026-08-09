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
        title="Sự cố"
        description="Ưu tiên sự cố cần xử lý, theo dõi người phụ trách và thời hạn."
        breadcrumbs={[{ label: "Tổng quan", href: "/" }, { label: "Sự cố" }]}
      />
      <TicketInbox />
    </>
  );
}
