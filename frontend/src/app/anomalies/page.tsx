import { AnomalyWorkspace } from "@/components/anomaly-workspace";
import { PageHeader } from "@/components/page-header";

export default function AnomaliesPage() {
  return (
    <>
      <PageHeader
        title="Bất thường"
        description="Theo dõi tín hiệu được phát hiện từ rule và Isolation Forest trong các batch gần đây."
        breadcrumbs={[{ label: "Tổng quan", href: "/" }, { label: "Bất thường" }]}
      />
      <AnomalyWorkspace />
    </>
  );
}
