"use client";

import Link from "next/link";
import { Bell, Check, Mail, X } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  useNotificationActionMutation,
  useNotificationsQuery,
  useUnreadNotificationCountQuery,
} from "@/hooks/use-operations";
import type { NotificationRecord } from "@/lib/api/operations-schemas";
import { permissions, type Permission } from "@/lib/auth";
import { formatTimestamp } from "@/lib/formatters";
import { cn } from "@/lib/utils";

export function NotificationCenter() {
  const auth = useAuth();
  const enabled = auth.can(permissions.notificationsRead);
  const count = useUnreadNotificationCountQuery(enabled);
  const notifications = useNotificationsQuery(
    { page: 1, page_size: 8 },
    enabled,
  );
  const action = useNotificationActionMutation();
  if (!enabled) return null;

  const unreadCount = count.data?.unread_count ?? 0;
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative"
          aria-label={`Thông báo${unreadCount ? `, ${unreadCount} chưa đọc` : ""}`}
          title="Thông báo"
        >
          <Bell aria-hidden="true" />
          {unreadCount > 0 && (
            <span className="absolute right-0.5 top-0.5 flex min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold leading-4 text-white">
              {unreadCount > 99 ? "99+" : unreadCount}
            </span>
          )}
        </Button>
      </SheetTrigger>
      <SheetContent className="w-full p-0 sm:max-w-md">
        <SheetHeader className="border-b px-5 py-4 text-left">
          <div className="flex items-center justify-between gap-3 pr-8">
            <div>
              <SheetTitle>Thông báo</SheetTitle>
              <SheetDescription>
                {unreadCount} thông báo chưa đọc
              </SheetDescription>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link href="/notifications">Xem tất cả</Link>
            </Button>
          </div>
        </SheetHeader>
        <ScrollArea className="h-[calc(100vh-92px)]">
          {notifications.isPending && (
            <p className="px-5 py-8 text-center text-sm text-muted-foreground">
              Đang tải thông báo...
            </p>
          )}
          {notifications.isError && (
            <div role="alert" className="m-4 rounded-md bg-red-50 p-3 text-sm text-red-800">
              Không thể tải thông báo.
            </div>
          )}
          {notifications.data?.items.length === 0 && (
            <p className="px-5 py-8 text-center text-sm text-muted-foreground">
              Chưa có thông báo.
            </p>
          )}
          <div className="divide-y">
            {notifications.data?.items.map((notification) => (
              <NotificationRow
                key={notification.id}
                notification={notification}
                pending={action.isPending}
                onAction={(actionName) =>
                  action.mutate({
                    notificationId: notification.id,
                    action: actionName,
                    expectedVersion: notification.version,
                  })
                }
              />
            ))}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}

function NotificationRow({
  notification,
  pending,
  onAction,
}: {
  notification: NotificationRecord;
  pending: boolean;
  onAction: (action: "read" | "unread" | "dismiss") => void;
}) {
  const auth = useAuth();
  const href = notificationHref(notification, auth.can);
  return (
    <article
      className={cn(
        "px-5 py-4",
        !notification.read_at && "bg-blue-50/60",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold">{notification.title}</p>
            <SeverityBadge severity={notification.severity} />
          </div>
          <p className="mt-1 text-sm leading-5 text-muted-foreground">
            {notification.body}
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            {formatTimestamp(notification.created_at)}
          </p>
        </div>
        {!notification.read_at && (
          <span className="mt-1 size-2 shrink-0 rounded-full bg-blue-600" aria-label="Chưa đọc" />
        )}
      </div>
      <div className="mt-3 flex items-center gap-1">
        {href && (
          <Button asChild variant="link" size="sm" className="h-8 px-0 pr-2">
            <Link href={href}>Mở chi tiết</Link>
          </Button>
        )}
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          disabled={pending}
          title={notification.read_at ? "Đánh dấu chưa đọc" : "Đánh dấu đã đọc"}
          aria-label={notification.read_at ? "Đánh dấu chưa đọc" : "Đánh dấu đã đọc"}
          onClick={() => onAction(notification.read_at ? "unread" : "read")}
        >
          {notification.read_at ? <Mail aria-hidden="true" /> : <Check aria-hidden="true" />}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          disabled={pending}
          title="Ẩn thông báo"
          aria-label="Ẩn thông báo"
          onClick={() => onAction("dismiss")}
        >
          <X aria-hidden="true" />
        </Button>
      </div>
    </article>
  );
}

export function SeverityBadge({
  severity,
}: {
  severity: NotificationRecord["severity"];
}) {
  const label = {
    info: "Thông tin",
    warning: "Cảnh báo",
    critical: "Nghiêm trọng",
  }[severity];
  return (
    <Badge
      variant="outline"
      className={cn(
        "text-[11px]",
        severity === "info" && "border-blue-200 bg-blue-50 text-blue-700",
        severity === "warning" && "border-amber-200 bg-amber-50 text-amber-800",
        severity === "critical" && "border-red-200 bg-red-50 text-red-700",
      )}
    >
      {label}
    </Badge>
  );
}

export function notificationHref(
  notification: NotificationRecord,
  can?: (permission: Permission) => boolean,
): string | null {
  const id = notification.related_entity_id;
  if (!id) return null;
  const route = {
    ticket: { prefix: "/tickets/", permission: permissions.ticketsRead },
    work_order: { prefix: "/work-orders/", permission: permissions.workOrdersRead },
    part: { prefix: "/inventory/parts/", permission: permissions.inventoryRead },
    maintenance_plan: {
      prefix: "/maintenance/plans/",
      permission: permissions.maintenancePlansRead,
    },
    job_execution: {
      prefix: "/admin/jobs?execution_id=",
      permission: permissions.jobOperationsRead,
    },
    inventory_issue: {
      prefix: "/inventory/movements?issue_id=",
      permission: permissions.inventoryRead,
    },
  }[notification.related_entity_type ?? ""];
  if (!route || (can && !can(route.permission))) return null;
  return `${route.prefix}${encodeURIComponent(id)}`;
}
