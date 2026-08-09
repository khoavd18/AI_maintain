import { PageHeader } from "@/components/page-header";
import { UserManagement } from "@/components/user-management";

export default function UsersPage() {
  return <><PageHeader title="Người dùng & quyền" description="Tạo và quản lý tài khoản local cho internal pilot. Mật khẩu và token không được hiển thị." breadcrumbs={[{ label: "Tổng quan", href: "/" }, { label: "Người dùng & quyền" }]} /><UserManagement /></>;
}
