import { PageHeader } from "@/components/page-header";
import { TicketIntakeForm } from "@/components/ticket-intake-form";

export default async function NewTicketPage({
  searchParams,
}: {
  searchParams: Promise<{ asset?: string }>;
}) {
  const { asset } = await searchParams;
  return (
    <>
      <PageHeader
        title="Tiếp nhận ticket"
        description="Ghi nhận sự cố, phân loại impact và urgency, sau đó áp dụng priority cùng SLA policy từ backend."
        breadcrumbs={[
          { label: "Phiếu sự cố", href: "/tickets" },
          { label: "Tiếp nhận" },
        ]}
      />
      <TicketIntakeForm initialAssetId={asset} />
    </>
  );
}
