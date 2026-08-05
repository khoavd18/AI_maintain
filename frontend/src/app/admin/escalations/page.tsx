import { EscalationDashboard } from "@/components/escalation-dashboard";
import { PageHeader } from "@/components/page-header";

export default function EscalationsPage() {
  return (
    <>
      <PageHeader
        title="Cảnh báo SLA"
        description="Đánh giá deterministic và idempotent các ticket critical, due soon, breached hoặc reopened nhiều lần."
        breadcrumbs={[
          { label: "Sự cố", href: "/tickets" },
          { label: "Cảnh báo SLA" },
        ]}
      />
      <EscalationDashboard />
    </>
  );
}
