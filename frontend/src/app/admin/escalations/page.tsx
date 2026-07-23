import { EscalationDashboard } from "@/components/escalation-dashboard";
import { PageHeader } from "@/components/page-header";

export default function EscalationsPage() {
  return (
    <>
      <PageHeader
        title="Escalation"
        description="Đánh giá deterministic và idempotent các ticket critical, due soon, breached hoặc reopened nhiều lần."
        breadcrumbs={[
          { label: "Phiếu sự cố", href: "/tickets" },
          { label: "Escalation" },
        ]}
      />
      <EscalationDashboard />
    </>
  );
}
