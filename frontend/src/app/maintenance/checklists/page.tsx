import { ChecklistTemplateWorkspace } from "@/components/checklist-template-workspace";
import { PageHeader } from "@/components/page-header";

export default function ChecklistTemplatesPage() {
  return (
    <>
      <PageHeader
        title="Mẫu kiểm tra"
        description="Quản lý các bước kiểm tra dùng khi thực hiện lệnh công việc."
        breadcrumbs={[{ label: "Tổng quan", href: "/" }, { label: "Mẫu kiểm tra" }]}
      />
      <ChecklistTemplateWorkspace />
    </>
  );
}
