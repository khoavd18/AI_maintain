import { z } from "zod";

export const riskLevelSchema = z.enum(["Thấp", "Trung bình", "Cao", "Khẩn cấp"]);
export const riskLevelCodeSchema = z.enum(["low", "medium", "high", "critical"]);
export const maintenanceStatusCodeSchema = z.enum(["not_due", "due_soon", "overdue"]);
export const maintenanceStatusDisplaySchema = z.enum([
  "Chưa đến hạn",
  "Sắp đến hạn",
  "Quá hạn",
]);
export const ticketStatusSchema = z.enum(["Mới tạo", "Đang xử lý", "Đã xử lý"]);
export const ticketPrioritySchema = z.enum(["Thấp", "Trung bình", "Cao", "Khẩn cấp"]);
export const assetCriticalitySchema = z.enum(["Trung bình", "Cao", "Rất quan trọng"]);
export const assetStatusSchema = z.enum(["Bình thường", "Cảnh báo"]);

const scoreSchema = z.number().min(0).max(100);
const nonNegativeIntegerSchema = z.number().int().nonnegative();
const requiredStringSchema = z.string().min(1);

export const healthResponseSchema = z.object({
  status: z.enum(["ok", "degraded"]),
  raw_data_available: z.boolean().nullable().optional(),
  analytics_available: z.boolean().nullable().optional(),
});

export const summaryResponseSchema = z.object({
  total_assets: nonNegativeIntegerSchema,
  total_records: nonNegativeIntegerSchema,
  high_risk_count: nonNegativeIntegerSchema,
  urgent_risk_count: nonNegativeIntegerSchema,
  anomaly_count: nonNegativeIntegerSchema,
  latest_date: z.string().nullable(),
  average_risk_score: scoreSchema,
});

export const assetRecordSchema = z.object({
  asset_id: requiredStringSchema,
  asset_name: requiredStringSchema,
  asset_type: requiredStringSchema,
  location: requiredStringSchema,
  criticality: assetCriticalitySchema,
  status: assetStatusSchema,
  installation_date: requiredStringSchema,
  last_maintenance_date: requiredStringSchema,
  maintenance_interval_days: z.number().int().positive(),
  next_maintenance_date: requiredStringSchema,
});

export const assetOverviewRecordSchema = assetRecordSchema.extend({
  risk_score: scoreSchema.nullable().optional(),
  risk_level_code: riskLevelCodeSchema.nullable().optional(),
  risk_level: riskLevelSchema.nullable().optional(),
  contributing_factors: z.string().nullable().optional(),
  recommended_action: z.string().nullable().optional(),
  maintenance_status: maintenanceStatusCodeSchema.nullable().optional(),
  maintenance_status_display: maintenanceStatusDisplaySchema.nullable().optional(),
  days_until_due: nonNegativeIntegerSchema.nullable().optional(),
  days_overdue: nonNegativeIntegerSchema.nullable().optional(),
  unresolved_ticket_count: nonNegativeIntegerSchema.nullable().optional(),
});

export const riskRecordSchema = z.object({
  asset_id: requiredStringSchema,
  date: requiredStringSchema,
  asset_name: requiredStringSchema,
  asset_type: requiredStringSchema,
  location: requiredStringSchema,
  anomaly_score: scoreSchema,
  maintenance_overdue_score: scoreSchema,
  recent_ticket_score: scoreSchema,
  criticality_score: scoreSchema,
  runtime_score: scoreSchema,
  final_risk_score: scoreSchema,
  risk_level: riskLevelSchema,
  main_reasons: requiredStringSchema,
  recommended_action: requiredStringSchema,
  feature_date: z.string().optional(),
  unresolved_ticket_score: scoreSchema.optional(),
  recurring_issue_score: scoreSchema.optional(),
  follow_up_score: scoreSchema.optional(),
  risk_score: scoreSchema.optional(),
  risk_level_code: riskLevelCodeSchema.optional(),
  contributing_factors: z.string().optional(),
});

export const anomalyRecordSchema = z.object({
  asset_id: requiredStringSchema,
  date: requiredStringSchema,
  asset_type: requiredStringSchema,
  location: requiredStringSchema,
  energy_kwh: z.number(),
  temperature: z.number(),
  vibration: z.number(),
  runtime_hours: z.number(),
  pressure: z.number(),
  energy_delta_percent: z.number(),
  vibration_delta: z.number(),
  runtime_delta_percent: z.number(),
  rule_based_score: scoreSchema,
  isolation_forest_score: scoreSchema,
  anomaly_score: scoreSchema,
  is_anomaly: z.boolean(),
  anomaly_type: requiredStringSchema,
  anomaly_reasons: requiredStringSchema,
  feature_date: z.string().optional(),
  anomalous_metrics: z.string().optional(),
  contributing_signals: z.string().optional(),
});

export const preventiveRecordSchema = z.object({
  asset_id: requiredStringSchema,
  as_of_date: requiredStringSchema,
  last_maintenance_date: requiredStringSchema,
  next_maintenance_date: requiredStringSchema,
  days_until_due: nonNegativeIntegerSchema,
  days_overdue: nonNegativeIntegerSchema,
  maintenance_status: maintenanceStatusCodeSchema,
  maintenance_status_display: maintenanceStatusDisplaySchema,
  asset_name: z.string().optional(),
  asset_type: z.string().optional(),
  location: z.string().optional(),
  criticality: assetCriticalitySchema.optional(),
});

export const recurringIssueRecordSchema = z.object({
  asset_id: requiredStringSchema,
  failure_category: requiredStringSchema,
  occurrence_count: z.number().int().positive(),
  first_occurrence: requiredStringSchema,
  last_occurrence: requiredStringSchema,
  resolved_count: nonNegativeIntegerSchema,
  unresolved_count: nonNegativeIntegerSchema,
  recurrence_flag: z.boolean(),
  recurrence_threshold: z.number().int().min(2),
});

export const maintenanceKpiResponseSchema = z.object({
  as_of_date: requiredStringSchema,
  total_tickets: nonNegativeIntegerSchema,
  open_tickets: nonNegativeIntegerSchema,
  resolved_tickets: nonNegativeIntegerSchema,
  ticket_resolution_rate_percent: z.number().min(0).max(100),
  average_resolution_time_hours: z.number().nonnegative(),
  median_resolution_time_hours: z.number().nonnegative(),
  overdue_asset_count: nonNegativeIntegerSchema,
  due_soon_asset_count: nonNegativeIntegerSchema,
  recurring_issue_count: nonNegativeIntegerSchema,
  follow_up_required_maintenance_count: nonNegativeIntegerSchema,
  high_critical_risk_asset_count: nonNegativeIntegerSchema,
});

export const ticketRecordSchema = z.object({
  ticket_id: requiredStringSchema,
  asset_id: requiredStringSchema,
  issue_description: requiredStringSchema,
  priority: ticketPrioritySchema,
  status: ticketStatusSchema,
  failure_category: requiredStringSchema,
  created_at: requiredStringSchema,
  resolved_at: z.string().nullable(),
  technician_id: requiredStringSchema,
  manager_note: z.string().nullable().optional(),
  note: z.string().nullable().optional(),
});

export const maintenanceLogRecordSchema = z.object({
  log_id: requiredStringSchema,
  ticket_id: z.string().nullable(),
  asset_id: requiredStringSchema,
  maintenance_date: requiredStringSchema,
  maintenance_type: requiredStringSchema,
  technician_id: requiredStringSchema,
  inspection_result: requiredStringSchema,
  actions_taken: requiredStringSchema,
  parts_replaced: z.string().nullable(),
  technician_note: requiredStringSchema,
  maintenance_result: requiredStringSchema,
  follow_up_required: z.boolean(),
  next_maintenance_date: requiredStringSchema,
});

export const assetDetailsResponseSchema = z.object({
  asset_profile: assetRecordSchema,
  latest_risk: riskRecordSchema.nullable(),
  risk_contributing_factors: z.string().nullable(),
  recommended_action: z.string().nullable(),
  preventive_maintenance: preventiveRecordSchema.nullable(),
  risk_history: z.array(riskRecordSchema),
  recent_anomalies: z.array(anomalyRecordSchema),
  recent_tickets: z.array(ticketRecordSchema),
  recent_maintenance_logs: z.array(maintenanceLogRecordSchema),
  recurring_issues: z.array(recurringIssueRecordSchema),
});

export const assetsResponseSchema = z.array(assetOverviewRecordSchema);
export const risksResponseSchema = z.array(riskRecordSchema);
export const anomaliesResponseSchema = z.array(anomalyRecordSchema);
export const preventiveResponseSchema = z.array(preventiveRecordSchema);
export const recurringIssuesResponseSchema = z.array(recurringIssueRecordSchema);
export const ticketsResponseSchema = z.array(ticketRecordSchema);
export const maintenanceLogsResponseSchema = z.array(maintenanceLogRecordSchema);

export type HealthResponse = z.infer<typeof healthResponseSchema>;
export type SummaryResponse = z.infer<typeof summaryResponseSchema>;
export type AssetRecord = z.infer<typeof assetRecordSchema>;
export type AssetOverviewRecord = z.infer<typeof assetOverviewRecordSchema>;
export type RiskRecord = z.infer<typeof riskRecordSchema>;
export type AnomalyRecord = z.infer<typeof anomalyRecordSchema>;
export type PreventiveRecord = z.infer<typeof preventiveRecordSchema>;
export type RecurringIssueRecord = z.infer<typeof recurringIssueRecordSchema>;
export type MaintenanceKpiResponse = z.infer<typeof maintenanceKpiResponseSchema>;
export type TicketRecord = z.infer<typeof ticketRecordSchema>;
export type MaintenanceLogRecord = z.infer<typeof maintenanceLogRecordSchema>;
export type AssetDetailsResponse = z.infer<typeof assetDetailsResponseSchema>;
