import { JobOperationsWorkspace } from "@/components/job-operations-workspace";
import { PageHeader } from "@/components/page-header";

export default function JobOperationsPage() {
  return (
    <>
      <PageHeader
        title="Tác vụ hệ thống"
        description="Theo dõi worker, execution, retry và transactional outbox cho các job được hỗ trợ."
        breadcrumbs={[
          { label: "Tổng quan", href: "/" },
          { label: "Quản trị" },
          { label: "Tác vụ hệ thống" },
        ]}
      />
      <JobOperationsWorkspace />
    </>
  );
}
