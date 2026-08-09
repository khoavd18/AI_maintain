import type { LucideIcon } from "lucide-react";
import { CircleAlert, CircleCheck, TriangleAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { AnomalySeverity, MaintenanceStatus, RiskLevel, TicketPriority, TicketStatus } from "@/lib/types";
import {
  anomalySeverityStatusCatalog,
  assetLifecycleStatusCatalog,
  assetOperationalStatusCatalog,
  checklistTemplateStatusCatalog,
  legacyPriorityStatusCatalog,
  legacyTicketStatusCatalog,
  maintenanceDueStatusCatalog,
  maintenancePlanStatusCatalog,
  priorityStatusCatalog,
  resolveStatusPresentation,
  riskStatusCatalog,
  type StatusPresentation,
  type StatusTone,
  workOrderStatusCatalog,
} from "@/lib/status-terminology";
import { cn } from "@/lib/utils";

type LifecycleStatus = "planned" | "active" | "inactive" | "retired" | "archived";
type OperationalStatus = "running" | "warning" | "fault" | "under_maintenance" | "out_of_service";

const toneClasses: Record<StatusTone, string> = {
  neutral: "border-neutral-200 bg-neutral-50 text-neutral-700 ring-neutral-200",
  info: "border-blue-200 bg-blue-50 text-blue-700 ring-blue-200",
  success: "border-green-200 bg-green-50 text-green-700 ring-green-200",
  warning: "border-amber-200 bg-amber-50 text-amber-800 ring-amber-200",
  danger: "border-red-200 bg-red-50 text-red-700 ring-red-200",
};

const toneIcons: Partial<Record<StatusTone, LucideIcon>> = {
  success: CircleCheck,
  warning: TriangleAlert,
  danger: CircleAlert,
};

export function StatusBadge({ presentation }: { presentation: StatusPresentation }) {
  const Icon = toneIcons[presentation.tone];
  return (
    <Badge
      variant="outline"
      className={cn("gap-1 ring-1 hover:bg-inherit", toneClasses[presentation.tone])}
      title={presentation.description}
    >
      {Icon && <Icon className="size-3" aria-hidden="true" />}
      {presentation.label}
      <span className="sr-only">. {presentation.description}</span>
    </Badge>
  );
}

export function RiskBadge({ level }: { level: RiskLevel }) {
  return <StatusBadge presentation={resolveStatusPresentation(riskStatusCatalog, level, level)} />;
}

export function MaintenanceBadge({ status }: { status: MaintenanceStatus }) {
  return <StatusBadge presentation={resolveStatusPresentation(maintenanceDueStatusCatalog, status, status)} />;
}

export function TicketStatusBadge({ status }: { status: TicketStatus }) {
  return <StatusBadge presentation={resolveStatusPresentation(legacyTicketStatusCatalog, status)} />;
}

export function PriorityBadge({ priority }: { priority: TicketPriority }) {
  return <StatusBadge presentation={resolveStatusPresentation(legacyPriorityStatusCatalog, priority, priority)} />;
}

export function AnomalySeverityBadge({ severity }: { severity: AnomalySeverity }) {
  return <StatusBadge presentation={resolveStatusPresentation(anomalySeverityStatusCatalog, severity, severity)} />;
}

export function LifecycleBadge({
  status,
  label,
}: {
  status: LifecycleStatus;
  label: string;
}) {
  return <StatusBadge presentation={resolveStatusPresentation(assetLifecycleStatusCatalog, status, label)} />;
}

export function OperationalBadge({
  status,
  label,
}: {
  status: OperationalStatus;
  label: string;
}) {
  return <StatusBadge presentation={resolveStatusPresentation(assetOperationalStatusCatalog, status, label)} />;
}

export function PlanStatusBadge({ status, label }: { status: string; label: string }) {
  return <StatusBadge presentation={resolveStatusPresentation(maintenancePlanStatusCatalog, status, label)} />;
}

export function ChecklistTemplateStatusBadge({ status, label }: { status: string; label: string }) {
  return <StatusBadge presentation={resolveStatusPresentation(checklistTemplateStatusCatalog, status, label)} />;
}

export function WorkOrderStatusBadge({ status, label }: { status: string; label: string }) {
  return <StatusBadge presentation={resolveStatusPresentation(workOrderStatusCatalog, status, label)} />;
}

export function CodePriorityBadge({ priority, label }: { priority: string; label: string }) {
  return <StatusBadge presentation={resolveStatusPresentation(priorityStatusCatalog, priority, label)} />;
}
