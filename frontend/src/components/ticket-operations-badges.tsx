import { StatusBadge } from "@/components/status-badges";
import type {
  TicketPriorityCode,
  TicketStatusCode,
} from "@/lib/api/ticketing-schemas";
import {
  priorityStatusCatalog,
  resolveStatusPresentation,
  slaStatusCatalog,
  ticketStatusCatalog,
} from "@/lib/status-terminology";

export function TicketOperationsStatusBadge({
  status,
  label,
}: {
  status: TicketStatusCode;
  label: string;
}) {
  return <StatusBadge presentation={resolveStatusPresentation(ticketStatusCatalog, status, label)} />;
}

export function TicketOperationsPriorityBadge({
  priority,
  label,
}: {
  priority: TicketPriorityCode;
  label: string;
}) {
  return <StatusBadge presentation={resolveStatusPresentation(priorityStatusCatalog, priority, label)} />;
}

export function SlaStatusBadge({
  status,
  label,
}: {
  status: string;
  label: string;
}) {
  return <StatusBadge presentation={resolveStatusPresentation(slaStatusCatalog, status, label)} />;
}
