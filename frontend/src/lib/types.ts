export type RiskLevel = "Thấp" | "Trung bình" | "Cao" | "Nghiêm trọng";

export type MaintenanceStatus = "Chưa đến hạn" | "Sắp đến hạn" | "Quá hạn";

export type TicketStatus = "new" | "in_progress" | "resolved";

export type TicketPriority = "Thấp" | "Trung bình" | "Cao" | "Khẩn cấp";

export interface Asset {
  id: string;
  name: string;
  type: string;
  location: string;
  criticality: string;
  status: string;
  riskScore: number;
  riskLevel: RiskLevel;
  maintenanceStatus: MaintenanceStatus;
  lastMaintenance: string;
  nextMaintenance: string;
  overdueDays: number;
  unresolvedTickets: number;
  latestAnomaly: string;
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
  updatedAt: string;
}

export interface AnomalyRecord {
  id: string;
  date: string;
  assetId: string;
  assetType: string;
  anomalyType: string;
  score: number;
  reason: string;
}

export interface RecurringIssue {
  category: string;
  assetType: string;
  occurrences: number;
  affectedAssets: number;
  latestDate: string;
}

export interface MaintenanceEvent {
  id: string;
  date: string;
  result: string;
  actions: string;
  technician: string;
  followUp: boolean;
}

export interface RiskContribution {
  factor: string;
  value: number;
  explanation: string;
}

export interface SourceDocument {
  title: string;
  section: string;
  relevance: number;
  excerpt: string;
}
