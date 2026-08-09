import { PageHeader } from "@/components/page-header";
import { SlaAdministration } from "@/features/sla/administration";

export default function SlaAdministrationPage() {
  return (
    <>
      <PageHeader
        title="Thiết lập SLA"
        description="Cấu hình business calendar và policy có hiệu lực; ticket đã tạo tiếp tục dùng snapshot lịch sử."
        breadcrumbs={[
          { label: "Sự cố", href: "/tickets" },
          { label: "Thiết lập SLA" },
        ]}
      />
      <SlaAdministration />
    </>
  );
}
