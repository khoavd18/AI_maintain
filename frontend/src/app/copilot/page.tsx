import { CopilotWorkspace } from "@/components/copilot-workspace";
import { PageHeader } from "@/components/page-header";

export default function CopilotPage() {
  return (
    <>
      <PageHeader
        title="Trợ lý bảo trì"
        description="Minh họa cách kỹ thuật viên đặt câu hỏi theo ngữ cảnh thiết bị và xem hướng dẫn có nguồn."
        breadcrumbs={[{ label: "Tổng quan", href: "/" }, { label: "Trợ lý bảo trì" }]}
      />
      <CopilotWorkspace />
    </>
  );
}
