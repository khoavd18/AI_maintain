"use client";

import { useMemo } from "react";

import type { TicketDetail } from "@/lib/api/ticketing-schemas";
import { formatTimestamp } from "@/lib/formatters";

function slaEventLabel(eventType: string) {
  return ({
    policy_applied: "Áp dụng thời hạn xử lý",
    clock_started: "Bắt đầu tính thời gian",
    paused: "Tạm dừng tính thời gian",
    resumed: "Tiếp tục tính thời gian",
    first_response_recorded: "Ghi nhận phản hồi lần đầu",
    target_met: "Hoàn thành trong thời hạn",
    breached: "Đã quá thời hạn",
    resolved: "Dừng thời gian xử lý",
    reopened: "Bắt đầu chu kỳ xử lý mới",
    stopped: "Dừng tính thời gian",
  }[eventType] ?? "Cập nhật thời hạn xử lý");
}

function slaClockLabel(clockType: string) {
  return clockType === "first_response"
    ? "Phản hồi lần đầu"
    : clockType === "resolution"
      ? "Hoàn tất xử lý"
      : "Thời hạn xử lý";
}

function escalationRuleLabel(ruleCode: string) {
  return ({
    first_response_due_soon: "Sắp đến hạn phản hồi",
    first_response_breached: "Quá hạn phản hồi",
    resolution_due_soon: "Sắp đến hạn xử lý",
    resolution_breached: "Quá hạn xử lý",
    critical_priority: "Sự cố khẩn cấp cần điều phối",
    repeated_reopen: "Phiếu được mở lại nhiều lần",
  }[ruleCode] ?? "Cảnh báo cần điều phối");
}

export function TicketTimeline({ ticket }: { ticket: TicketDetail }) {
  const items = useMemo(
    () =>
      [
        ...ticket.comments.map((item) => ({
          id: `comment-${item.id}`,
          at: item.created_at,
          title: item.visibility === "internal" ? "Ghi chú nội bộ" : "Cập nhật requester",
          detail: `${item.author_name}: ${item.body}`,
          tone: "comment",
        })),
        ...ticket.sla_events.map((item) => ({
          id: `sla-${item.id}`,
          at: item.occurred_at,
          title: slaEventLabel(item.event_type),
          detail: item.clock_type ? `${slaClockLabel(item.clock_type)} · Chu kỳ ${item.occurrence_number}` : `Chu kỳ ${item.occurrence_number}`,
          tone: "sla",
        })),
        ...ticket.escalations.map((item) => ({
          id: `escalation-${item.id}`,
          at: item.detected_at,
          title: escalationRuleLabel(item.rule_code),
          detail: item.clock_type ? slaClockLabel(item.clock_type) : "Cảnh báo ở cấp phiếu",
          tone: "escalation",
        })),
      ].sort((left, right) => right.at.localeCompare(left.at)),
    [ticket.comments, ticket.escalations, ticket.sla_events],
  );

  return (
    <section className="rounded-lg border bg-white">
      <header className="border-b p-4"><h2 className="text-sm font-semibold">Lịch sử cập nhật</h2></header>
      {items.length ? (
        <ol className="divide-y">
          {items.map((item) => (
            <li key={item.id} className="flex gap-3 p-4">
              <span
                className={`mt-1 size-2 shrink-0 rounded-full ${item.tone === "escalation" ? "bg-red-600" : item.tone === "sla" ? "bg-blue-600" : "bg-green-600"}`}
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap justify-between gap-2">
                  <p className="text-sm font-semibold">{item.title}</p>
                  <time className="text-xs text-muted-foreground">{formatTimestamp(item.at)}</time>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">{item.detail}</p>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="p-6 text-sm text-muted-foreground">Chưa có cập nhật nào.</p>
      )}
    </section>
  );
}
