import type {
  AnomalyRecord as ApiAnomalyRecord,
  AssetDetailsResponse,
  AssetOverviewRecord,
  MaintenanceLogRecord,
  RecurringIssueRecord,
  RiskRecord,
  TicketRecord,
} from "@/lib/api/schemas";
import {
  formatDate,
  formatElapsedTime,
  formatMaintenanceLabel,
  formatMetricList,
  formatRiskLabel,
  formatTimestamp,
  missingValue,
} from "@/lib/formatters";
import type {
  AnomalyRecord,
  AnomalySeverity,
  Asset,
  MaintenanceEvent,
  RecurringIssue,
  RiskContribution,
  Ticket,
  TicketStatus,
} from "@/lib/types";

const ticketStatusCodes: Record<TicketRecord["status"], TicketStatus> = {
  "Mới tạo": "new",
  "Đang xử lý": "in_progress",
  "Đã xử lý": "resolved",
};

export function adaptAsset(record: AssetOverviewRecord): Asset {
  return {
    id: record.asset_id,
    name: record.asset_name,
    type: record.asset_type,
    location: record.location,
    criticality: record.criticality,
    status: record.status,
    riskScore: record.risk_score ?? null,
    riskLevel: formatRiskLabel(record.risk_level),
    maintenanceStatus: formatMaintenanceLabel(record.maintenance_status_display),
    lastMaintenance: formatDate(record.last_maintenance_date),
    nextMaintenance: formatDate(record.next_maintenance_date),
    overdueDays: record.days_overdue ?? 0,
    unresolvedTickets: record.unresolved_ticket_count ?? 0,
    contributingFactors: record.contributing_factors ?? missingValue,
    recommendedAction: record.recommended_action ?? missingValue,
  };
}

export function adaptAssetDetails(details: AssetDetailsResponse): Asset {
  const profile = details.asset_profile;
  const preventive = details.preventive_maintenance;
  return {
    id: profile.asset_id,
    name: profile.asset_name,
    type: profile.asset_type,
    location: profile.location,
    criticality: profile.criticality,
    status: profile.status,
    riskScore: details.latest_risk?.final_risk_score ?? null,
    riskLevel: formatRiskLabel(details.latest_risk?.risk_level),
    maintenanceStatus: formatMaintenanceLabel(preventive?.maintenance_status_display),
    lastMaintenance: formatDate(profile.last_maintenance_date),
    nextMaintenance: formatDate(profile.next_maintenance_date),
    overdueDays: preventive?.days_overdue ?? 0,
    unresolvedTickets: details.recent_tickets.filter((ticket) => ticket.status !== "Đã xử lý").length,
    contributingFactors: details.risk_contributing_factors ?? missingValue,
    recommendedAction: details.recommended_action ?? missingValue,
  };
}

export function adaptTicket(record: TicketRecord): Ticket {
  return {
    id: record.ticket_id,
    assetId: record.asset_id,
    summary: record.issue_description,
    description: record.issue_description,
    failureCategory: record.failure_category,
    priority: record.priority,
    status: ticketStatusCodes[record.status],
    technician: record.technician_id,
    createdAt: formatTimestamp(record.created_at),
    updatedAt: formatTimestamp(record.resolved_at ?? record.created_at),
    waitingTime: formatElapsedTime(record.created_at, record.resolved_at),
  };
}

export function adaptAnomaly(record: ApiAnomalyRecord): AnomalyRecord {
  return {
    id: `${record.asset_id}-${record.date}`,
    date: formatDate(record.date),
    assetId: record.asset_id,
    assetType: record.asset_type,
    anomalyType: record.anomaly_type,
    metric: formatMetricList(record.anomalous_metrics),
    change: buildObservedChange(record),
    severity: anomalySeverity(record.anomaly_score),
    score: record.anomaly_score,
    reason: record.anomaly_reasons,
    relatedAction: "Mở hồ sơ thiết bị để đối chiếu risk, ticket và lịch bảo trì.",
  };
}

export function adaptRecurringIssue(record: RecurringIssueRecord): RecurringIssue {
  return {
    assetId: record.asset_id,
    category: record.failure_category,
    occurrences: record.occurrence_count,
    latestDate: formatTimestamp(record.last_occurrence),
    unresolvedCount: record.unresolved_count,
    recurrenceFlag: record.recurrence_flag,
  };
}

export function adaptMaintenanceLog(record: MaintenanceLogRecord): MaintenanceEvent {
  return {
    id: record.log_id,
    date: formatDate(record.maintenance_date),
    result: record.maintenance_result,
    actions: record.actions_taken,
    technician: record.technician_id,
    followUp: record.follow_up_required,
    nextMaintenance: formatDate(record.next_maintenance_date),
  };
}

export function adaptRiskHistory(records: RiskRecord[]) {
  return records.map((record) => ({
    date: formatDate(record.date),
    score: record.final_risk_score,
  }));
}

export function adaptRiskContributions(record: RiskRecord | null): RiskContribution[] {
  if (!record) return [];
  const components = [
    ["Bất thường", record.anomaly_score, 0.2, "Tín hiệu từ rule và Isolation Forest."],
    ["Bảo trì quá hạn", record.maintenance_overdue_score, 0.25, "Mức quá hạn bảo trì phòng ngừa."],
    ["Ticket chưa xử lý", record.unresolved_ticket_score ?? 0, 0.2, "Số ticket còn mở tại ngày đánh giá."],
    ["Ticket gần đây", record.recent_ticket_score, 0.1, "Tần suất và mức ưu tiên ticket gần đây."],
    ["Lỗi lặp lại", record.recurring_issue_score ?? 0, 0.075, "Nhóm lỗi đạt ngưỡng lặp lại."],
    ["Mức độ quan trọng", record.criticality_score, 0.1, "Mức độ quan trọng của thiết bị."],
    ["Cần theo dõi", record.follow_up_score ?? 0, 0.05, "Log bảo trì còn yêu cầu theo dõi."],
    ["Runtime", record.runtime_score, 0.025, "Độ lệch runtime so với mức nền."],
  ] as const;
  return components.map(([factor, score, weight, explanation]) => ({
    factor,
    value: Number((score * weight).toFixed(2)),
    explanation,
  }));
}

function anomalySeverity(score: number): AnomalySeverity {
  if (score >= 85) return "Ưu tiên";
  if (score >= 65) return "Cảnh báo";
  return "Theo dõi";
}

function buildObservedChange(record: ApiAnomalyRecord): string {
  const changes: string[] = [];
  if (Math.abs(record.energy_delta_percent) >= 10) {
    changes.push(`điện năng ${formatSignedPercent(record.energy_delta_percent)}`);
  }
  if (Math.abs(record.runtime_delta_percent) >= 10) {
    changes.push(`runtime ${formatSignedPercent(record.runtime_delta_percent)}`);
  }
  if (Math.abs(record.vibration_delta) >= 0.05) {
    changes.push(`độ rung ${record.vibration_delta >= 0 ? "tăng" : "giảm"} ${Math.abs(record.vibration_delta).toFixed(2)}`);
  }
  return changes.length ? changes.join("; ") : record.anomaly_type;
}

function formatSignedPercent(value: number): string {
  return `${value >= 0 ? "tăng" : "giảm"} ${Math.abs(value).toFixed(1)}%`;
}
