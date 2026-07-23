import { Badge } from "@/components/ui/badge";
import type { AnomalySeverity, MaintenanceStatus, RiskLevel, TicketPriority, TicketStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

type LifecycleStatus = "planned" | "active" | "inactive" | "retired" | "archived";
type OperationalStatus = "running" | "warning" | "fault" | "under_maintenance" | "out_of_service";

const riskClasses: Record<RiskLevel, string> = {
  Thấp: "bg-green-50 text-green-700 ring-green-200",
  "Trung bình": "bg-amber-50 text-amber-700 ring-amber-200",
  Cao: "bg-orange-50 text-orange-700 ring-orange-200",
  "Khẩn cấp": "bg-red-50 text-red-700 ring-red-200",
};

const maintenanceClasses: Record<MaintenanceStatus, string> = {
  "Chưa đến hạn": "bg-green-50 text-green-700 ring-green-200",
  "Sắp đến hạn": "bg-amber-50 text-amber-700 ring-amber-200",
  "Quá hạn": "bg-red-50 text-red-700 ring-red-200",
};

const ticketLabels: Record<TicketStatus, string> = {
  new: "Mới tạo",
  in_progress: "Đang xử lý",
  resolved: "Đã xử lý",
};

const ticketClasses: Record<TicketStatus, string> = {
  new: "bg-blue-50 text-blue-700 ring-blue-200",
  in_progress: "bg-amber-50 text-amber-700 ring-amber-200",
  resolved: "bg-green-50 text-green-700 ring-green-200",
};

const priorityClasses: Record<TicketPriority, string> = {
  Thấp: "bg-neutral-100 text-neutral-700 ring-neutral-200",
  "Trung bình": "bg-blue-50 text-blue-700 ring-blue-200",
  Cao: "bg-orange-50 text-orange-700 ring-orange-200",
  "Khẩn cấp": "bg-red-50 text-red-700 ring-red-200",
};

const anomalySeverityClasses: Record<AnomalySeverity, string> = {
  "Theo dõi": "bg-blue-50 text-blue-700 ring-blue-200",
  "Cảnh báo": "bg-amber-50 text-amber-700 ring-amber-200",
  "Ưu tiên": "bg-orange-50 text-orange-700 ring-orange-200",
};

const lifecycleClasses: Record<LifecycleStatus, string> = {
  planned: "bg-blue-50 text-blue-700 ring-blue-200",
  active: "bg-green-50 text-green-700 ring-green-200",
  inactive: "bg-neutral-100 text-neutral-700 ring-neutral-200",
  retired: "bg-amber-50 text-amber-800 ring-amber-200",
  archived: "bg-neutral-200 text-neutral-800 ring-neutral-300",
};

const operationalClasses: Record<OperationalStatus, string> = {
  running: "bg-green-50 text-green-700 ring-green-200",
  warning: "bg-amber-50 text-amber-800 ring-amber-200",
  fault: "bg-red-50 text-red-700 ring-red-200",
  under_maintenance: "bg-blue-50 text-blue-700 ring-blue-200",
  out_of_service: "bg-neutral-100 text-neutral-700 ring-neutral-200",
};

const planClasses: Record<string, string> = {
  active: "bg-green-50 text-green-700 ring-green-200",
  paused: "bg-amber-50 text-amber-800 ring-amber-200",
  archived: "bg-neutral-200 text-neutral-800 ring-neutral-300",
};

const workOrderClasses: Record<string, string> = {
  planned: "bg-neutral-100 text-neutral-700 ring-neutral-200",
  assigned: "bg-blue-50 text-blue-700 ring-blue-200",
  in_progress: "bg-amber-50 text-amber-800 ring-amber-200",
  on_hold: "bg-orange-50 text-orange-800 ring-orange-200",
  completed: "bg-cyan-50 text-cyan-800 ring-cyan-200",
  verified: "bg-green-50 text-green-700 ring-green-200",
  cancelled: "bg-neutral-200 text-neutral-700 ring-neutral-300",
};

const codePriorityClasses: Record<string, string> = {
  low: "bg-neutral-100 text-neutral-700 ring-neutral-200",
  medium: "bg-blue-50 text-blue-700 ring-blue-200",
  high: "bg-orange-50 text-orange-700 ring-orange-200",
  critical: "bg-red-50 text-red-700 ring-red-200",
};

function SemanticBadge({ label, className }: { label: string; className: string }) {
  return <Badge className={cn("ring-1 hover:bg-inherit", className)}>{label}</Badge>;
}

export function RiskBadge({ level }: { level: RiskLevel }) {
  return <SemanticBadge label={level} className={riskClasses[level]} />;
}

export function MaintenanceBadge({ status }: { status: MaintenanceStatus }) {
  return <SemanticBadge label={status} className={maintenanceClasses[status]} />;
}

export function TicketStatusBadge({ status }: { status: TicketStatus }) {
  return <SemanticBadge label={ticketLabels[status]} className={ticketClasses[status]} />;
}

export function PriorityBadge({ priority }: { priority: TicketPriority }) {
  return <SemanticBadge label={priority} className={priorityClasses[priority]} />;
}

export function AnomalySeverityBadge({ severity }: { severity: AnomalySeverity }) {
  return <SemanticBadge label={severity} className={anomalySeverityClasses[severity]} />;
}

export function LifecycleBadge({
  status,
  label,
}: {
  status: LifecycleStatus;
  label: string;
}) {
  return <SemanticBadge label={label} className={lifecycleClasses[status]} />;
}

export function OperationalBadge({
  status,
  label,
}: {
  status: OperationalStatus;
  label: string;
}) {
  return <SemanticBadge label={label} className={operationalClasses[status]} />;
}

export function PlanStatusBadge({ status, label }: { status: string; label: string }) {
  return <SemanticBadge label={label} className={planClasses[status] ?? planClasses.archived} />;
}

export function WorkOrderStatusBadge({ status, label }: { status: string; label: string }) {
  return <SemanticBadge label={label} className={workOrderClasses[status] ?? workOrderClasses.planned} />;
}

export function CodePriorityBadge({ priority, label }: { priority: string; label: string }) {
  return <SemanticBadge label={label} className={codePriorityClasses[priority] ?? codePriorityClasses.low} />;
}
