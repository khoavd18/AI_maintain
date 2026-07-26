import { JobOperationsWorkspace } from "@/components/job-operations-workspace";
import { PageHeader } from "@/components/page-header";

export default function JobOperationsPage() {
  return (
    <>
      <PageHeader
        title="Background jobs"
        description="Theo dõi worker, execution, retry và transactional outbox cho các job được hỗ trợ."
        breadcrumbs={[
          { label: "Trung tâm vận hành", href: "/" },
          { label: "Quản trị" },
          { label: "Background jobs" },
        ]}
      />
      <JobOperationsWorkspace />
    </>
  );
}
