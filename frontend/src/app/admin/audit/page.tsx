import { AuditLogWorkspace } from "@/components/audit-log-workspace";
import { PageHeader } from "@/components/page-header";

export default function AuditPage() {
  return <><PageHeader title="Nhật ký hệ thống" description="Theo dõi sự kiện xác thực, quản trị và workflow dưới dạng append-only." breadcrumbs={[{ label: "Tổng quan", href: "/" }, { label: "Nhật ký hệ thống" }]} /><AuditLogWorkspace /></>;
}
