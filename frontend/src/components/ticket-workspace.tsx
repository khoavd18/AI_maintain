"use client";

import Link from "next/link";
import { ArrowUpRight, Filter, Search, UserRound } from "lucide-react";
import { useMemo, useState } from "react";

import { PriorityBadge, TicketStatusBadge } from "@/components/status-badges";
import { TicketCard } from "@/components/ticket-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { EmptyState } from "@/components/ui-states";
import { tickets } from "@/lib/mock-data";
import type { Ticket, TicketStatus } from "@/lib/types";

const columns: { status: TicketStatus; label: string; accent: string }[] = [
  { status: "new", label: "Mới tạo", accent: "bg-blue-500" },
  { status: "in_progress", label: "Đang xử lý", accent: "bg-amber-500" },
  { status: "resolved", label: "Đã xử lý", accent: "bg-green-600" },
];

export function TicketWorkspace() {
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null);
  const [search, setSearch] = useState("");
  const [priority, setPriority] = useState("all");

  const filteredTickets = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase("vi");
    return tickets.filter((ticket) => {
      const matchesSearch =
        !normalizedSearch ||
        [ticket.id, ticket.assetId, ticket.summary, ticket.technician].some((value) =>
          value.toLocaleLowerCase("vi").includes(normalizedSearch),
        );
      return matchesSearch && (priority === "all" || ticket.priority === priority);
    });
  }, [priority, search]);

  return (
    <>
      <section aria-label="Bộ lọc ticket" className="mb-4 flex flex-col gap-3 rounded-lg border bg-white p-4 sm:flex-row sm:items-end">
        <div className="w-full space-y-1.5 sm:max-w-sm">
          <Label htmlFor="ticket-search">Tìm ticket</Label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input
              id="ticket-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Ticket ID, asset ID hoặc kỹ thuật viên"
              className="pl-8"
            />
          </div>
        </div>
        <div className="w-full space-y-1.5 sm:w-52">
          <Label htmlFor="ticket-priority">Mức ưu tiên</Label>
          <Select value={priority} onValueChange={setPriority}>
            <SelectTrigger id="ticket-priority" className="w-full">
              <Filter aria-hidden="true" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tất cả mức ưu tiên</SelectItem>
              <SelectItem value="Khẩn cấp">Khẩn cấp</SelectItem>
              <SelectItem value="Cao">Cao</SelectItem>
              <SelectItem value="Trung bình">Trung bình</SelectItem>
              <SelectItem value="Thấp">Thấp</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <p className="pb-1 text-xs text-muted-foreground sm:ml-auto">
          {filteredTickets.length} ticket trong workspace mock
        </p>
      </section>

      <div className="grid items-start gap-4 lg:grid-cols-3">
        {columns.map((column) => {
          const columnTickets = filteredTickets.filter((ticket) => ticket.status === column.status);
          return (
            <section key={column.status} aria-labelledby={`column-${column.status}`} className="rounded-lg bg-neutral-100/80 p-3 ring-1 ring-neutral-200">
              <header className="mb-3 flex items-center justify-between gap-2 px-1">
                <div className="flex items-center gap-2">
                  <span className={`size-2 rounded-full ${column.accent}`} aria-hidden="true" />
                  <h2 id={`column-${column.status}`} className="text-sm font-semibold">{column.label}</h2>
                </div>
                <span className="flex size-6 items-center justify-center rounded-full bg-white text-xs font-semibold ring-1 ring-neutral-200">
                  {columnTickets.length}
                </span>
              </header>
              <div className="space-y-3">
                {columnTickets.length > 0 ? (
                  columnTickets.map((ticket) => (
                    <TicketCard key={ticket.id} ticket={ticket} onSelect={setSelectedTicket} />
                  ))
                ) : (
                  <div className="rounded-lg border border-dashed bg-white">
                    <EmptyState title="Không có ticket" description="Không có kết quả phù hợp trong nhóm này." />
                  </div>
                )}
              </div>
            </section>
          );
        })}
      </div>

      <Sheet open={selectedTicket !== null} onOpenChange={(open) => !open && setSelectedTicket(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-lg">
          {selectedTicket && (
            <>
              <SheetHeader className="border-b text-left">
                <div className="flex flex-wrap items-center gap-2 pr-8">
                  <SheetTitle className="font-mono text-primary">{selectedTicket.id}</SheetTitle>
                  <TicketStatusBadge status={selectedTicket.status} />
                  <PriorityBadge priority={selectedTicket.priority} />
                </div>
                <SheetDescription>{selectedTicket.summary}</SheetDescription>
              </SheetHeader>
              <div className="space-y-5 px-4 pb-6">
                <DetailSection title="Ngữ cảnh thiết bị">
                  <DetailRow label="Asset ID" value={selectedTicket.assetId} mono />
                  <DetailRow label="Nhóm lỗi" value={selectedTicket.failureCategory} />
                  <DetailRow label="Kỹ thuật viên" value={selectedTicket.technician} icon={<UserRound className="size-3.5" aria-hidden="true" />} />
                </DetailSection>

                <DetailSection title="Mô tả vấn đề">
                  <p className="text-sm leading-6 text-muted-foreground">{selectedTicket.description}</p>
                </DetailSection>

                <DetailSection title="Thời gian">
                  <DetailRow label="Tạo lúc" value={selectedTicket.createdAt} />
                  <DetailRow label="Cập nhật" value={selectedTicket.updatedAt} />
                </DetailSection>

                <Button asChild className="w-full justify-between">
                  <Link href={`/assets/${selectedTicket.assetId}`}>
                    Mở thiết bị liên quan
                    <ArrowUpRight aria-hidden="true" />
                  </Link>
                </Button>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}

function DetailSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">{title}</h3>
      <div className="space-y-2 rounded-lg border p-3">{children}</div>
    </section>
  );
}

function DetailRow({ label, value, mono = false, icon }: { label: string; value: string; mono?: boolean; icon?: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={`flex items-center gap-1.5 text-right font-medium ${mono ? "font-mono" : ""}`}>
        {icon}{value}
      </span>
    </div>
  );
}
