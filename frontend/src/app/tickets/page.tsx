import { PageHeader } from "@/components/page-header";
import { TicketWorkspace } from "@/components/ticket-workspace";

export default async function TicketsPage({
  searchParams,
}: {
  searchParams: Promise<{ asset?: string; action?: string; ticket?: string }>;
}) {
  const { asset, action, ticket } = await searchParams;
  const initialCreateAssetId = action === "create" ? asset : undefined;

  return (
    <>
      <PageHeader
        title="Phiếu sự cố"
        description="Theo dõi vấn đề từ lúc ghi nhận đến khi kỹ thuật viên hoàn tất xử lý."
        breadcrumbs={[{ label: "Tổng quan", href: "/" }, { label: "Phiếu sự cố" }]}
      />
      <TicketWorkspace initialCreateAssetId={initialCreateAssetId} initialTicketId={ticket} />
    </>
  );
}
