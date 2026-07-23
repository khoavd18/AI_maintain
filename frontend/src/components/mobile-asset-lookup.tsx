"use client";

import { Bot, CalendarClock, ExternalLink, Loader2, MapPin, TicketPlus, Wrench } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { LifecycleBadge, OperationalBadge } from "@/components/status-badges";
import { TicketCreateSheet } from "@/components/ticket-create-sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState, RetryButton } from "@/components/ui-states";
import { useAssetDetailsQuery, useQrLookupQuery, useTicketsQuery } from "@/hooks/use-api-queries";
import { adaptAssetDetails, adaptAssetProfile } from "@/lib/adapters";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { AssetProfile } from "@/lib/api/schemas";
import { permissions } from "@/lib/auth";
import { formatDate, formatTimestamp } from "@/lib/formatters";

export function MobileAssetLookup({ lookupToken }: { lookupToken: string }) {
  const lookup = useQrLookupQuery(lookupToken);

  if (lookup.isPending) {
    return <div className="flex min-h-[50vh] items-center justify-center text-sm text-muted-foreground"><Loader2 className="mr-2 size-5 animate-spin" aria-hidden="true" />Đang nhận diện asset</div>;
  }
  if (lookup.isError) {
    return <ErrorState title="Không nhận diện được QR" description={getApiErrorMessage(lookup.error)} action={<RetryButton onClick={() => void lookup.refetch()} />} />;
  }
  return <MobileAssetLookupContent profile={lookup.data} />;
}

function MobileAssetLookupContent({ profile }: { profile: AssetProfile }) {
  const auth = useAuth();
  const details = useAssetDetailsQuery(profile.asset_id, 20);
  const tickets = useTicketsQuery({ asset_id: profile.asset_id, limit: 50 });
  const [ticketOpen, setTicketOpen] = useState(false);
  const asset = details.data ? adaptAssetDetails(details.data) : adaptAssetProfile(profile);
  const openTickets = (tickets.data ?? []).filter((ticket) => ticket.status !== "Đã xử lý");
  const canCreateTicket = auth.can(permissions.ticketsCreate) && !["retired", "archived"].includes(profile.lifecycle_status);

  return <div className="mx-auto w-full max-w-2xl space-y-4 overflow-x-hidden pb-8">
    <header className="border-b pb-4">
      <p className="font-mono text-xs font-semibold uppercase text-primary">{profile.asset_id}</p>
      <h1 className="mt-1 break-words text-2xl font-semibold">{profile.asset_name}</h1>
      <p className="mt-2 flex items-start gap-2 text-sm text-muted-foreground"><MapPin className="mt-0.5 size-4 shrink-0" aria-hidden="true" />{profile.location_breadcrumb}</p>
      <div className="mt-3 flex flex-wrap gap-2"><Badge variant="outline">{profile.asset_type}</Badge><LifecycleBadge status={profile.lifecycle_status} label={profile.lifecycle_status_display} /><OperationalBadge status={profile.operational_status} label={profile.operational_status_display} /></div>
    </header>

    <section className="grid grid-cols-2 gap-3" aria-label="Thông tin nhanh">
      <QuickFact icon={<Wrench aria-hidden="true" />} label="Mức quan trọng" value={profile.criticality} />
      <QuickFact icon={<CalendarClock aria-hidden="true" />} label="Bảo trì kế tiếp" value={formatDate(profile.next_maintenance_date)} />
      <QuickFact label="Ticket đang mở" value={tickets.isPending ? "..." : String(openTickets.length)} />
      <QuickFact label="Bảo hành" value={profile.warranty_end_date ? formatDate(profile.warranty_end_date) : "Chưa cập nhật"} />
    </section>

    <div className="grid gap-2 sm:grid-cols-3">
      <Button asChild><Link href={`/assets/${profile.asset_id}`}><ExternalLink aria-hidden="true" />Mở hồ sơ đầy đủ</Link></Button>
      {canCreateTicket && <Button type="button" variant="outline" onClick={() => setTicketOpen(true)}><TicketPlus aria-hidden="true" />Tạo ticket</Button>}
      {auth.can(permissions.copilotUse) && <Button asChild variant="outline"><Link href={`/copilot?asset=${profile.asset_id}`}><Bot aria-hidden="true" />Mở Copilot</Link></Button>}
    </div>

    <section className="rounded-lg border bg-white" aria-labelledby="open-ticket-heading">
      <div className="border-b p-3"><h2 id="open-ticket-heading" className="text-sm font-semibold">Ticket đang mở</h2></div>
      {tickets.isError ? <p role="alert" className="p-3 text-sm text-red-700">{getApiErrorMessage(tickets.error)}</p> : tickets.isPending ? <p className="p-3 text-sm text-muted-foreground">Đang tải ticket...</p> : openTickets.length === 0 ? <p className="p-3 text-sm text-muted-foreground">Không có ticket đang mở.</p> : <ul className="divide-y">{openTickets.slice(0, 5).map((ticket) => <li key={ticket.ticket_id} className="p-3"><div className="flex flex-wrap items-center justify-between gap-2"><Link href={`/tickets?ticket=${ticket.ticket_id}`} className="font-mono text-xs font-semibold text-primary hover:underline">{ticket.ticket_id}</Link><Badge variant="outline">{ticket.status}</Badge></div><p className="mt-2 break-words text-sm leading-5">{ticket.issue_description}</p><p className="mt-2 text-xs text-muted-foreground">{ticket.priority} · {formatTimestamp(ticket.created_at)}</p></li>)}</ul>}
    </section>

    <p className="text-xs leading-5 text-muted-foreground">QR hỗ trợ nhận diện và truy cập nhanh. Trạng thái và lịch sử vẫn phải được xác minh trước khi thực hiện bảo trì.</p>

    {canCreateTicket && <TicketCreateSheet asset={asset} latestAnomaly={details.data?.recent_anomalies[0]?.anomaly_reasons} open={ticketOpen} onOpenChange={setTicketOpen} />}
  </div>;
}

function QuickFact({ icon, label, value }: { icon?: React.ReactNode; label: string; value: string }) {
  return <div className="min-w-0 rounded-lg border bg-white p-3"><p className="flex items-center gap-1.5 text-xs text-muted-foreground">{icon && <span className="[&>svg]:size-3.5">{icon}</span>}{label}</p><p className="mt-1 break-words text-sm font-semibold">{value}</p></div>;
}
