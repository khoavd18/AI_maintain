"use client";

import { CheckCheck, ChevronDown, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { SeverityBadge, notificationHref, presentNotificationText } from "@/components/notification-center";
import { useAuth } from "@/components/auth-provider";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  useNotificationActionMutation,
  useNotificationsQuery,
  useReadAllNotificationsMutation,
} from "@/hooks/use-operations";
import type { NotificationSeverity } from "@/lib/api/operations-schemas";
import { getApiErrorMessage } from "@/lib/api/errors";
import { formatTimestamp } from "@/lib/formatters";
import { cn } from "@/lib/utils";

export function NotificationWorkspace() {
  const auth = useAuth();
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [severity, setSeverity] = useState<NotificationSeverity | "all">("all");
  const notifications = useNotificationsQuery({
    unread_only: unreadOnly,
    severity: severity === "all" ? undefined : severity,
    page: 1,
    page_size: 50,
  });
  const action = useNotificationActionMutation();
  const readAll = useReadAllNotificationsMutation();

  return (
    <div className="space-y-4">
      <div className="flex flex-col justify-between gap-3 rounded-lg border bg-white p-4 sm:flex-row sm:items-center">
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant={unreadOnly ? "default" : "outline"}
            size="sm"
            onClick={() => setUnreadOnly((value) => !value)}
          >
            Chưa đọc
          </Button>
          <div className="flex items-center gap-2 text-sm">
            <Label htmlFor="notification-severity" className="text-muted-foreground">
              Mức độ
            </Label>
            <Select
              value={severity}
              onValueChange={(value) =>
                setSeverity(value as NotificationSeverity | "all")
              }
            >
              <SelectTrigger id="notification-severity" className="h-9 w-36 bg-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tất cả</SelectItem>
                <SelectItem value="info">Thông tin</SelectItem>
                <SelectItem value="warning">Cảnh báo</SelectItem>
                <SelectItem value="critical">Nghiêm trọng</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void notifications.refetch()}
          >
            <RefreshCw aria-hidden="true" />
            Làm mới
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={readAll.isPending}
            onClick={() => readAll.mutate()}
          >
            <CheckCheck aria-hidden="true" />
            Đánh dấu tất cả đã đọc
          </Button>
        </div>
      </div>

      {(action.error || readAll.error) && (
        <div role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-800">
          {getApiErrorMessage(action.error ?? readAll.error)}
        </div>
      )}
      {notifications.isPending && (
        <Card><CardContent className="py-12 text-center text-sm text-muted-foreground">Đang tải thông báo...</CardContent></Card>
      )}
      {notifications.isError && (
        <Card><CardContent className="py-12 text-center text-sm text-red-700">Không thể tải thông báo.</CardContent></Card>
      )}
      {notifications.data?.items.length === 0 && (
        <Card><CardContent className="py-12 text-center text-sm text-muted-foreground">Không có thông báo phù hợp bộ lọc.</CardContent></Card>
      )}
      <div className="divide-y rounded-lg border bg-white">
        {notifications.data?.items.map((notification) => {
          const href = notificationHref(notification, auth.can);
          return (
            <article
              key={notification.id}
              className={notification.read_at ? "p-4" : "bg-blue-50/50 p-4"}
            >
              <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-sm font-semibold">{presentNotificationText(notification.title)}</h2>
                    <SeverityBadge severity={notification.severity} />
                    {!notification.read_at && (
                      <span className="text-xs font-medium text-blue-700">Chưa đọc</span>
                    )}
                  </div>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    {presentNotificationText(notification.body)}
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {formatTimestamp(notification.created_at)}
                  </p>
                </div>
                <div className="flex w-full shrink-0 flex-col gap-2 sm:w-auto sm:items-end">
                  {href && (
                    <Button asChild size="sm" className="w-full sm:w-auto">
                      <Link href={href}>Mở chi tiết</Link>
                    </Button>
                  )}
                  <details className="group w-full sm:w-auto">
                    <summary
                      className={cn(
                        buttonVariants({ variant: "outline", size: "sm" }),
                        "w-full cursor-pointer list-none [&::-webkit-details-marker]:hidden",
                      )}
                    >
                      Thao tác khác
                      <ChevronDown className="transition-transform group-open:rotate-180" aria-hidden="true" />
                    </summary>
                    <div className="mt-2 grid min-w-52 gap-1 rounded-lg border bg-white p-1.5 shadow-sm">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="w-full justify-start"
                        disabled={action.isPending}
                        onClick={() =>
                          action.mutate({
                            notificationId: notification.id,
                            action: notification.read_at ? "unread" : "read",
                            expectedVersion: notification.version,
                          })
                        }
                      >
                        {notification.read_at ? "Đánh dấu chưa đọc" : "Đánh dấu đã đọc"}
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="w-full justify-start text-muted-foreground"
                        disabled={action.isPending}
                        onClick={() =>
                          action.mutate({
                            notificationId: notification.id,
                            action: "dismiss",
                            expectedVersion: notification.version,
                          })
                        }
                      >
                        Ẩn thông báo
                      </Button>
                    </div>
                  </details>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
