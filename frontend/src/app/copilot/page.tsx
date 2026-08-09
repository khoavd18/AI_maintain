import { CopilotWorkspace } from "@/components/copilot-workspace";
import { PageHeader } from "@/components/page-header";

export default async function CopilotPage({
  searchParams,
}: {
  searchParams: Promise<{ asset?: string | string[]; ticket?: string | string[] }>;
}) {
  const params = await searchParams;
  const assetId = Array.isArray(params.asset) ? params.asset[0] : params.asset;
  const ticketId = Array.isArray(params.ticket) ? params.ticket[0] : params.ticket;
  return (
    <>
      <PageHeader
        title="Trợ lý bảo trì"
        description="Đặt câu hỏi theo ngữ cảnh thiết bị và ticket, sau đó đối chiếu hướng dẫn với SOP/checklist được truy xuất."
        breadcrumbs={[{ label: "Tổng quan", href: "/" }, { label: "Trợ lý bảo trì" }]}
      />
      <CopilotWorkspace initialAssetId={assetId} initialTicketId={ticketId} />
    </>
  );
}
