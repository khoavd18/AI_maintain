"use client";

import {
  Bot,
  Wrench,
} from "lucide-react";
import Link from "next/link";

import { useAuth } from "@/components/auth-provider";
import {
  SlaStatusBadge,
  TicketOperationsPriorityBadge,
  TicketOperationsStatusBadge,
} from "@/components/ticket-operations-badges";
import { Button } from "@/components/ui/button";
import type { TicketDetail } from "@/lib/api/ticketing-schemas";
import { permissions } from "@/lib/auth";
import { formatTimestamp } from "@/lib/formatters";

export function TicketSummary({ ticket }: { ticket: TicketDetail }) {
  const auth = useAuth();
  return (
    <section className="rounded-lg border bg-white p-4 sm:p-5">
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs font-semibold text-primary">
              {ticket.ticket_id}
            </span>
            <TicketOperationsStatusBadge status={ticket.status} label={ticket.status_display} />
            <TicketOperationsPriorityBadge priority={ticket.priority} label={ticket.priority_display} />
          </div>
          <h2 className="mt-3 text-lg font-semibold">{ticket.issue_description}</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {ticket.asset_id} · {ticket.category_name ?? "Chưa phân loại"} ·{" "}
            {ticket.failure_category_display}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href={`/assets/${ticket.asset_id}`}>
              <Wrench aria-hidden="true" />
              Hồ sơ thiết bị
            </Link>
          </Button>
          {auth.can(permissions.copilotUse) && (
            <Button asChild variant="outline" size="sm">
              <Link
                href={`/copilot?asset=${encodeURIComponent(ticket.asset_id)}&ticket=${encodeURIComponent(ticket.ticket_id)}`}
              >
                <Bot aria-hidden="true" />
                Hỏi trợ lý bảo trì
              </Link>
            </Button>
          )}
        </div>
      </div>
    </section>
  );
}

export function TicketFacts({ ticket }: { ticket: TicketDetail }) {
  return (
    <section className="rounded-lg border bg-white p-4 sm:p-5">
      <h2 className="text-sm font-semibold">Thông tin chính</h2>
      <dl className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Fact label="Người phụ trách" value={ticket.assigned_user_name ?? "Chưa phân công"} />
        <Fact label="Nhóm xử lý" value={ticket.support_group_name ?? "Chưa phân nhóm"} />
        <Fact label="Mức ảnh hưởng" value={ticket.impact_display} />
        <Fact label="Độ khẩn cấp" value={ticket.urgency_display} />
        <Fact label="Tiếp nhận lúc" value={formatTimestamp(ticket.created_at)} />
      </dl>

      <div className="mt-5 border-t pt-5">
        <SlaFacts ticket={ticket} />
      </div>

      {ticket.waiting_reason && (
        <div className="mt-4 rounded-lg border border-orange-200 bg-orange-50 p-3 text-sm text-orange-950">
          <strong>Lý do chờ:</strong> {ticket.waiting_reason}
        </div>
      )}
      {ticket.manager_note && (
        <div className="mt-4 rounded-lg border bg-muted/30 p-3 text-sm">
          <strong>Ghi chú quản lý:</strong> {ticket.manager_note}
        </div>
      )}

      <details className="group mt-5 border-t pt-4">
        <summary className="w-fit cursor-pointer rounded-md text-sm font-medium text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          Thông tin bổ sung
        </summary>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Fact label="Phân loại cụ thể" value={ticket.subcategory_name ?? "Chưa chọn"} />
          <Fact label="Nguồn tiếp nhận" value={ticket.intake_source_name ?? "Chưa ghi"} />
          <Fact label="Phản hồi lần đầu" value={formatTimestamp(ticket.first_response_at)} />
          <Fact label="Số lần mở lại" value={`${ticket.reopen_count} lần`} />
        </dl>
        <div className="mt-5 border-t pt-5">
          <ReporterFacts ticket={ticket} />
        </div>
      </details>
    </section>
  );
}

function ReporterFacts({ ticket }: { ticket: TicketDetail }) {
  return (
    <section aria-labelledby="reporter-heading">
      <div className="flex items-center gap-2">
        <h3 id="reporter-heading" className="text-sm font-semibold">
          Người báo sự cố
        </h3>
        {ticket.reporter_redacted && (
          <span className="rounded bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600">
            Đã ẩn theo quyền
          </span>
        )}
      </div>
      <dl className="mt-3 space-y-3">
        <Fact label="Họ tên" value={ticket.reporter_name ?? "Không hiển thị"} />
        <Fact label="Email" value={ticket.reporter_email ?? "Không hiển thị"} />
        <Fact label="Điện thoại" value={ticket.reporter_phone ?? "Không hiển thị"} />
      </dl>
    </section>
  );
}

function SlaFacts({ ticket }: { ticket: TicketDetail }) {
  if (!ticket.sla) {
    return (
      <section aria-labelledby="sla-heading">
        <h3 id="sla-heading" className="text-sm font-semibold">Thời hạn xử lý</h3>
        <p className="mt-3 text-sm text-muted-foreground">
          Phiếu này chưa có thời hạn xử lý được áp dụng.
        </p>
      </section>
    );
  }
  return (
    <section aria-labelledby="sla-heading">
      <div className="flex items-center justify-between gap-2">
        <h3 id="sla-heading" className="text-sm font-semibold">Thời hạn phản hồi và xử lý</h3>
        <span className="text-xs text-muted-foreground">Chu kỳ {ticket.sla.occurrence_number}</span>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <SlaClock label="Phản hồi lần đầu" clock={ticket.sla.first_response} target={ticket.sla.first_response_target_minutes} />
        <SlaClock label="Hoàn tất xử lý" clock={ticket.sla.resolution} target={ticket.sla.resolution_target_minutes} />
      </div>
      <p className="mt-3 text-xs leading-5 text-muted-foreground">
        {ticket.sla.pause_on_waiting
          ? "Thời gian được tạm dừng khi phiếu ở trạng thái Chờ."
          : "Thời gian vẫn tiếp tục tính khi phiếu ở trạng thái Chờ."}
      </p>
    </section>
  );
}

function SlaClock({
  label,
  clock,
  target,
}: {
  label: string;
  clock: TicketDetail["sla"] extends infer T
    ? T extends { first_response: infer C }
      ? C
      : never
    : never;
  target: number;
}) {
  return (
    <div className="rounded-lg border p-3">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <div className="mt-2">
        <SlaStatusBadge status={clock.status} label={clock.status_display} />
      </div>
      <p className="mt-2 text-xs">{formatBusinessMinutes(clock.remaining_business_minutes)}</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Hạn {formatTimestamp(clock.due_at)} · mục tiêu {target} phút
      </p>
    </div>
  );
}

export function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-sm font-medium">{value}</dd>
    </div>
  );
}

export function formatBusinessMinutes(minutes: number | null) {
  if (minutes === null) return "Đã dừng tính thời gian";
  if (minutes <= 0) return "Đã đến hoặc quá hạn";
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return hours
    ? `Còn ${hours} giờ${remainder ? ` ${remainder} phút` : ""} làm việc`
    : `Còn ${remainder} phút làm việc`;
}
