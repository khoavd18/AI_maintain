import { Clock3, Hourglass, UserRound } from "lucide-react";

import { PriorityBadge } from "@/components/status-badges";
import { Card, CardContent } from "@/components/ui/card";
import type { Ticket } from "@/lib/types";
import { cn } from "@/lib/utils";

interface TicketCardProps {
  ticket: Ticket;
  onSelect?: (ticket: Ticket) => void;
  compact?: boolean;
}

export function TicketCard({ ticket, onSelect, compact = false }: TicketCardProps) {
  const content = (
    <Card
      size="sm"
      className={cn(
        "text-left transition-colors",
        onSelect && "hover:bg-muted/40 hover:ring-primary/30",
      )}
    >
      <CardContent className="space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="font-mono text-xs font-medium text-primary">{ticket.id}</p>
            <p className="mt-1 font-mono text-xs text-muted-foreground">{ticket.assetId}</p>
          </div>
          <PriorityBadge priority={ticket.priority} />
        </div>
        <p className={cn("font-medium leading-5", compact ? "line-clamp-1" : "line-clamp-2")}>
          {ticket.summary}
        </p>
        <div className="space-y-1.5 text-xs text-muted-foreground">
          <p className="flex items-center gap-2">
            <UserRound className="size-3.5" aria-hidden="true" />
            <span className="truncate">Phụ trách: {ticket.technician}</span>
          </p>
          <p className="flex items-center gap-2">
            <Hourglass className="size-3.5" aria-hidden="true" />
            <span>{ticket.status === "resolved" ? "Thời gian xử lý" : "Đang chờ"}: {ticket.waitingTime}</span>
          </p>
          {!compact && (
            <p className="flex items-center gap-2">
              <Clock3 className="size-3.5" aria-hidden="true" />
              <span>Tạo lúc {ticket.createdAt}</span>
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );

  if (!onSelect) {
    return content;
  }

  return (
    <button
      type="button"
      onClick={() => onSelect(ticket)}
      className="block w-full rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      aria-label={`Xem chi tiết ticket ${ticket.id}`}
    >
      {content}
    </button>
  );
}
