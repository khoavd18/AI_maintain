import { ChecklistTemplateWorkspace } from "@/components/checklist-template-workspace";
import { PageHeader } from "@/components/page-header";

export default function ChecklistTemplatesPage() {
  return (
    <>
      <PageHeader
        title="Checklist template"
        description="Thiết kế và version hóa các bước bảo trì; work order luôn giữ snapshot lịch sử."
        breadcrumbs={[{ label: "Tổng quan", href: "/" }, { label: "Checklist" }]}
      />
      <ChecklistTemplateWorkspace />
    </>
  );
}
