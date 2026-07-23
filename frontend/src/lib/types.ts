export type RiskLevel = "Thấp" | "Trung bình" | "Cao" | "Khẩn cấp";

export type MaintenanceStatus = "Chưa đến hạn" | "Sắp đến hạn" | "Quá hạn";

export type TicketStatus = "new" | "in_progress" | "resolved";

export type TicketPriority = "Thấp" | "Trung bình" | "Cao" | "Khẩn cấp";

export type AnomalySeverity = "Theo dõi" | "Cảnh báo" | "Ưu tiên";

export interface Asset {
  id: string;
  name: string;
  type: string;
  location: string;
  criticality: string;
  status: string;
  riskScore: number | null;
  riskLevel: RiskLevel | null;
  maintenanceStatus: MaintenanceStatus | null;
  lastMaintenance: string;
  lastMaintenanceDateIso?: string;
  nextMaintenance: string;
  nextMaintenanceDateIso?: string;
  maintenanceIntervalDays?: number;
  overdueDays: number;
  unresolvedTickets: number;
  contributingFactors: string;
  recommendedAction: string;
}

export interface Ticket {
  id: string;
  assetId: string;
  summary: string;
  description: string;
  failureCategory: string;
  priority: TicketPriority;
  status: TicketStatus;
  technician: string;
  createdAt: string;
  createdAtIso?: string;
  resolvedAtIso?: string | null;
  updatedAt: string;
  waitingTime: string;
  managerNote?: string | null;
  note?: string | null;
}

export interface AnomalyRecord {
  id: string;
  date: string;
  assetId: string;
  assetType: string;
  anomalyType: string;
  metric: string;
  change: string;
  severity: AnomalySeverity;
  score: number;
  reason: string;
  relatedAction: string;
}

export interface RecurringIssue {
  assetId: string;
  category: string;
  occurrences: number;
  latestDate: string;
  unresolvedCount: number;
  recurrenceFlag: boolean;
}

export interface MaintenanceEvent {
  id: string;
  ticketId?: string | null;
  date: string;
  result: string;
  actions: string;
  technician: string;
  followUp: boolean;
  nextMaintenance: string;
}

export interface RiskContribution {
  factor: string;
  value: number;
  explanation: string;
}
