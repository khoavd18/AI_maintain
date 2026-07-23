import { Badge } from "@/components/ui/badge";
import type {
  TicketPriorityCode,
  TicketStatusCode,
} from "@/lib/api/ticketing-schemas";
import { cn } from "@/lib/utils";

const statusClasses: Record<TicketStatusCode, string> = {
  open: "bg-blue-50 text-blue-700 ring-blue-200",
  assigned: "bg-cyan-50 text-cyan-800 ring-cyan-200",
  in_progress: "bg-amber-50 text-amber-800 ring-amber-200",
  waiting: "bg-orange-50 text-orange-800 ring-orange-200",
  resolved: "bg-green-50 text-green-700 ring-green-200",
  closed: "bg-neutral-200 text-neutral-700 ring-neutral-300",
  cancelled: "bg-neutral-100 text-neutral-600 ring-neutral-200",
  reopened: "bg-red-50 text-red-700 ring-red-200",
};

const priorityClasses: Record<TicketPriorityCode, string> = {
  low: "bg-neutral-100 text-neutral-700 ring-neutral-200",
  medium: "bg-blue-50 text-blue-700 ring-blue-200",
  high: "bg-orange-50 text-orange-700 ring-orange-200",
  critical: "bg-red-50 text-red-700 ring-red-200",
};

const slaClasses: Record<string, string> = {
  not_started: "bg-neutral-100 text-neutral-700 ring-neutral-200",
  active: "bg-blue-50 text-blue-700 ring-blue-200",
  paused: "bg-orange-50 text-orange-800 ring-orange-200",
  met: "bg-green-50 text-green-700 ring-green-200",
  due_soon: "bg-amber-50 text-amber-800 ring-amber-200",
  breached: "bg-red-50 text-red-700 ring-red-200",
  stopped: "bg-neutral-200 text-neutral-700 ring-neutral-300",
};

function SemanticBadge({
  label,
  className,
}: {
  label: string;
  className: string;
}) {
  return (
    <Badge className={cn("ring-1 hover:bg-inherit", className)}>
      {label}
    </Badge>
  );
}

export function TicketOperationsStatusBadge({
  status,
  label,
}: {
  status: TicketStatusCode;
  label: string;
}) {
  return <SemanticBadge label={label} className={statusClasses[status]} />;
}

export function TicketOperationsPriorityBadge({
  priority,
  label,
}: {
  priority: TicketPriorityCode;
  label: string;
}) {
  return <SemanticBadge label={label} className={priorityClasses[priority]} />;
}

export function SlaStatusBadge({
  status,
  label,
}: {
  status: string;
  label: string;
}) {
  return (
    <SemanticBadge
      label={label}
      className={slaClasses[status] ?? slaClasses.not_started}
    />
  );
}
