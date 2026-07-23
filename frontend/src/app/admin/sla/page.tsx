import { PageHeader } from "@/components/page-header";
import { SlaAdministration } from "@/components/sla-administration";

export default function SlaAdministrationPage() {
  return (
    <>
      <PageHeader
        title="Quản trị SLA"
        description="Cấu hình business calendar và policy có hiệu lực; ticket đã tạo tiếp tục dùng snapshot lịch sử."
        breadcrumbs={[
          { label: "Phiếu sự cố", href: "/tickets" },
          { label: "SLA" },
        ]}
      />
      <SlaAdministration />
    </>
  );
}
