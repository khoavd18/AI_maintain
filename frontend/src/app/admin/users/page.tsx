import { PageHeader } from "@/components/page-header";
import { UserManagement } from "@/components/user-management";

export default function UsersPage() {
  return <><PageHeader title="Quản lý người dùng" description="Tạo và quản lý tài khoản local cho internal pilot. Mật khẩu và token không được hiển thị." breadcrumbs={[{ label: "Tổng quan", href: "/" }, { label: "Người dùng" }]} /><UserManagement /></>;
}
