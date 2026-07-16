"use client";

import Link from "next/link";
import { ArrowRight, LockKeyhole } from "lucide-react";

import { PriorityBadge, RiskBadge, TicketStatusBadge } from "@/components/status-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { Asset, Ticket } from "@/lib/types";

export function TicketDetailSheet({
  ticket,
  asset,
  onClose,
}: {
  ticket: Ticket | null;
  asset?: Asset;
  onClose: () => void;
}) {
  return (
    <Sheet open={Boolean(ticket)} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        {ticket && (
          <>
            <SheetHeader className="text-left">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="font-mono">{ticket.id}</Badge>
                <PriorityBadge priority={ticket.priority} />
                <TicketStatusBadge status={ticket.status} />
              </div>
              <SheetTitle>{ticket.summary}</SheetTitle>
              <SheetDescription>{ticket.assetId} · {ticket.failureCategory}</SheetDescription>
            </SheetHeader>

            <div className="space-y-5 px-4 pb-6">
              <section className="rounded-lg border bg-muted/30 p-3">
                <h3 className="text-sm font-semibold">Thông tin ticket</h3>
                <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                  <Fact label="Kỹ thuật viên" value={ticket.technician} />
                  <Fact label="Thời gian chờ / xử lý" value={ticket.waitingTime} />
                  <Fact label="Tạo lúc" value={ticket.createdAt} />
                  <Fact label="Cập nhật" value={ticket.updatedAt} />
                </dl>
                <p className="mt-4 text-sm leading-6 text-muted-foreground">{ticket.description}</p>
              </section>

              {asset && (
                <section className="rounded-lg border p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div><h3 className="text-sm font-semibold">Thiết bị liên quan</h3><p className="mt-1 text-xs text-muted-foreground">{asset.name} · {asset.location}</p></div>
                    {asset.riskLevel ? <RiskBadge level={asset.riskLevel} /> : <span className="text-xs text-muted-foreground">Chưa có risk</span>}
                  </div>
                  <p className="mt-3 text-sm text-muted-foreground">Risk {asset.riskScore == null ? "chưa có dữ liệu" : asset.riskScore.toFixed(2)} · {asset.maintenanceStatus ?? "chưa có lịch bảo trì"}</p>
                  <Button asChild variant="outline" className="mt-3 w-full justify-between"><Link href={`/assets/${asset.id}`}>Mở hồ sơ thiết bị<ArrowRight aria-hidden="true" /></Link></Button>
                </section>
              )}

              <Separator />
              <section aria-labelledby="pending-actions">
                <h3 id="pending-actions" className="flex items-center gap-2 text-sm font-semibold"><LockKeyhole className="size-4" aria-hidden="true" />Thao tác chưa kết nối</h3>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">Phân công, chuyển trạng thái, ghi kết quả bảo trì và đóng ticket sẽ được nối API trong frontend milestone tiếp theo.</p>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  <Button disabled variant="outline">Phân công kỹ thuật viên</Button>
                  <Button disabled variant="outline">Chuyển trạng thái</Button>
                  <Button disabled variant="outline">Ghi kết quả bảo trì</Button>
                  <Button disabled>Đóng ticket</Button>
                </div>
              </section>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 font-medium">{value}</dd></div>;
}
