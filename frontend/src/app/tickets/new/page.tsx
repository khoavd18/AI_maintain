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
        title="Báo sự cố"
        description="Ghi nhận thiết bị, mô tả vấn đề và mức độ cần ưu tiên xử lý."
        breadcrumbs={[
          { label: "Phiếu sự cố", href: "/tickets" },
          { label: "Tiếp nhận" },
        ]}
      />
      <TicketIntakeForm initialAssetId={asset} />
    </>
  );
}
