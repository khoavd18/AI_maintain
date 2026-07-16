import { Badge } from "@/components/ui/badge";
import type { AnomalySeverity, MaintenanceStatus, RiskLevel, TicketPriority, TicketStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

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
