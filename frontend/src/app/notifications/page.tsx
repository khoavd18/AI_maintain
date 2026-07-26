import { NotificationWorkspace } from "@/components/notification-workspace";
import { PageHeader } from "@/components/page-header";

export default function NotificationsPage() {
  return (
    <>
      <PageHeader
        title="Thông báo vận hành"
        description="Theo dõi các sự kiện cần chú ý từ ticket, work order, SLA và tồn kho."
        breadcrumbs={[
          { label: "Trung tâm vận hành", href: "/" },
          { label: "Thông báo" },
        ]}
      />
      <NotificationWorkspace />
    </>
  );
}
