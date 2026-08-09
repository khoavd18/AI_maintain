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
export const ticketFailureCategorySchema = z.enum([
  "Lỗi làm lạnh",
  "Lỗi rung động",
  "Lỗi điện",
  "Lỗi áp suất",
  "Lỗi thời gian vận hành",
  "Lỗi cảm biến",
  "Cảnh báo giả",
  "Không có lỗi",
]);
export const maintenanceResultSchema = z.enum([
  "Đã xử lý",
  "Đã xử lý một phần",
  "Cần theo dõi",
  "Cần hỗ trợ chuyên môn",
]);
export const assetCriticalitySchema = z.enum(["Thấp", "Trung bình", "Cao", "Rất quan trọng"]);
export const assetStatusSchema = z.enum(["Bình thường", "Cảnh báo", "Sự cố"]);
export const assetTypeCodeSchema = z.enum(["hvac", "pump", "generator"]);
export const assetCategoryCodeSchema = z.enum([
  "climate_control",
  "water_system",
  "power_system",
  "other",
]);
export const criticalityCodeSchema = z.enum(["low", "medium", "high", "critical"]);
export const lifecycleStatusCodeSchema = z.enum([
  "planned",
  "active",
  "inactive",
  "retired",
  "archived",
]);
export const operationalStatusCodeSchema = z.enum([
  "running",
  "warning",
  "fault",
  "under_maintenance",
  "out_of_service",
]);
export const ownershipTypeCodeSchema = z.enum(["owned", "leased", "managed"]);
export const locationTypeCodeSchema = z.enum(["building", "floor", "room", "area", "plant"]);
export const attachmentCategoryCodeSchema = z.enum([
  "asset_photo",
  "technical_manual",
  "warranty_document",
  "commissioning_record",
  "inspection_document",
  "other",
]);

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

export const assetProfileSchema = assetRecordSchema.extend({
  asset_type_code: assetTypeCodeSchema,
  asset_category: assetCategoryCodeSchema,
  asset_category_display: requiredStringSchema,
  manufacturer: z.string().nullable(),
  model: z.string().nullable(),
  serial_number: z.string().nullable(),
  production_year: z.number().int().nullable(),
  location_id: z.string().uuid().nullable(),
  location_breadcrumb: requiredStringSchema,
  criticality_code: criticalityCodeSchema,
  lifecycle_status: lifecycleStatusCodeSchema,
  lifecycle_status_display: requiredStringSchema,
  lifecycle_status_before_archive: z.string().nullable(),
  operational_status: operationalStatusCodeSchema,
  operational_status_display: requiredStringSchema,
  operational_status_before_archive: z.string().nullable(),
  installed_at: requiredStringSchema,
  commissioned_at: z.string().nullable(),
  retired_at: z.string().nullable(),
  archived_at: z.string().nullable(),
  archive_reason: z.string().nullable(),
  ownership_type: ownershipTypeCodeSchema,
  ownership_type_display: requiredStringSchema,
  description: z.string().nullable(),
  warranty_start_date: z.string().nullable(),
  warranty_end_date: z.string().nullable(),
  warranty_provider: z.string().nullable(),
  warranty_reference: z.string().nullable(),
  created_at: requiredStringSchema,
  updated_at: requiredStringSchema,
  created_by_user_id: z.string().uuid().nullable(),
  updated_by_user_id: z.string().uuid().nullable(),
  version: z.number().int().positive(),
  qr_lookup_token: z.string().uuid(),
});

export const assetCatalogPageSchema = z.object({
  items: z.array(assetProfileSchema),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  total_pages: z.number().int().nonnegative(),
});

export const assetOptionSchema = z.object({
  code: requiredStringSchema,
  display_name: requiredStringSchema,
});

export const assetOptionsSchema = z.object({
  asset_types: z.array(assetOptionSchema),
  asset_categories: z.array(assetOptionSchema),
  criticalities: z.array(assetOptionSchema),
  lifecycle_statuses: z.array(assetOptionSchema),
  operational_statuses: z.array(assetOptionSchema),
  ownership_types: z.array(assetOptionSchema),
  location_types: z.array(assetOptionSchema),
  attachment_categories: z.array(assetOptionSchema),
});

export const locationRecordSchema = z.object({
  id: z.string().uuid(),
  code: requiredStringSchema,
  name: requiredStringSchema,
  location_type: locationTypeCodeSchema,
  location_type_display: requiredStringSchema,
  parent_id: z.string().uuid().nullable(),
  breadcrumb: requiredStringSchema,
  description: z.string().nullable(),
  is_active: z.boolean(),
  asset_count: z.number().int().nonnegative(),
  created_at: requiredStringSchema,
  updated_at: requiredStringSchema,
  version: z.number().int().positive(),
});

export const locationsResponseSchema = z.array(locationRecordSchema);

export const assetCreateRequestSchema = z
  .object({
    asset_id: z.string().trim().min(2).max(50).regex(/^[A-Za-z0-9_-]+$/),
    asset_name: z.string().trim().min(2).max(200),
    asset_type: assetTypeCodeSchema,
    asset_category: assetCategoryCodeSchema,
    manufacturer: z.string().trim().max(200).nullable().optional(),
    model: z.string().trim().max(200).nullable().optional(),
    serial_number: z.string().trim().max(150).nullable().optional(),
    production_year: z.number().int().min(1900).max(2200).nullable().optional(),
    location_id: z.string().uuid(),
    criticality: criticalityCodeSchema,
    lifecycle_status: z.enum(["planned", "active", "inactive"]),
    operational_status: operationalStatusCodeSchema,
    installed_at: z.string().datetime({ offset: true }),
    commissioned_at: z.string().datetime({ offset: true }).nullable().optional(),
    ownership_type: ownershipTypeCodeSchema,
    description: z.string().trim().max(4000).nullable().optional(),
    warranty_start_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable().optional(),
    warranty_end_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable().optional(),
    warranty_provider: z.string().trim().max(200).nullable().optional(),
    warranty_reference: z.string().trim().max(200).nullable().optional(),
    maintenance_interval_days: z.number().int().positive().max(3650),
    last_maintenance_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    next_maintenance_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  })
  .superRefine((request, context) => {
    if (request.commissioned_at && request.commissioned_at < request.installed_at) {
      context.addIssue({
        code: "custom",
        path: ["commissioned_at"],
        message: "Ngày nghiệm thu không được sớm hơn ngày lắp đặt.",
      });
    }
    if (
      request.warranty_start_date &&
      request.warranty_end_date &&
      request.warranty_end_date < request.warranty_start_date
    ) {
      context.addIssue({
        code: "custom",
        path: ["warranty_end_date"],
        message: "Ngày kết thúc bảo hành không được sớm hơn ngày bắt đầu.",
      });
    }
    if (request.next_maintenance_date < request.last_maintenance_date) {
      context.addIssue({
        code: "custom",
        path: ["next_maintenance_date"],
        message: "Ngày bảo trì kế tiếp không được sớm hơn lần gần nhất.",
      });
    }
  });

export const assetUpdateRequestSchema = z
  .object({
    expected_version: z.number().int().positive(),
    asset_name: z.string().trim().min(2).max(200).optional(),
    asset_type: assetTypeCodeSchema.optional(),
    asset_category: assetCategoryCodeSchema.optional(),
    manufacturer: z.string().trim().max(200).nullable().optional(),
    model: z.string().trim().max(200).nullable().optional(),
    serial_number: z.string().trim().max(150).nullable().optional(),
    production_year: z.number().int().min(1900).max(2200).nullable().optional(),
    location_id: z.string().uuid().optional(),
    criticality: criticalityCodeSchema.optional(),
    installed_at: z.string().datetime({ offset: true }).optional(),
    commissioned_at: z.string().datetime({ offset: true }).nullable().optional(),
    ownership_type: ownershipTypeCodeSchema.optional(),
    description: z.string().trim().max(4000).nullable().optional(),
    warranty_start_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable().optional(),
    warranty_end_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable().optional(),
    warranty_provider: z.string().trim().max(200).nullable().optional(),
    warranty_reference: z.string().trim().max(200).nullable().optional(),
    maintenance_interval_days: z.number().int().positive().max(3650).optional(),
    last_maintenance_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
    next_maintenance_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  })
  .refine((request) => Object.keys(request).some((key) => key !== "expected_version"), {
    message: "Cần cung cấp ít nhất một field để cập nhật.",
  });

export const operationalStatusRequestSchema = z.object({
  operational_status: operationalStatusCodeSchema,
  expected_version: z.number().int().positive(),
});

export const lifecycleTransitionRequestSchema = z.object({
  lifecycle_status: z.enum(["planned", "active", "inactive", "retired"]),
  expected_version: z.number().int().positive(),
});

export const assetArchiveRequestSchema = z.object({
  archive_reason: z.string().trim().min(5).max(1000),
  expected_version: z.number().int().positive(),
});

export const assetRestoreRequestSchema = z.object({
  expected_version: z.number().int().positive(),
  lifecycle_status: z.enum(["planned", "active", "inactive"]).nullable().optional(),
});

export const assetAttachmentSchema = z.object({
  id: z.string().uuid(),
  asset_id: requiredStringSchema,
  category: attachmentCategoryCodeSchema,
  category_display: requiredStringSchema,
  original_filename: requiredStringSchema,
  media_type: z.enum(["application/pdf", "image/png", "image/jpeg"]),
  size_bytes: z.number().int().positive(),
  checksum: z.string().length(64),
  uploaded_by_user_id: z.string().uuid(),
  created_at: requiredStringSchema,
  deleted_at: z.string().nullable(),
  deleted_by_user_id: z.string().uuid().nullable(),
  storage_cleanup_pending: z.boolean().nullable().optional(),
});

export const assetAttachmentsSchema = z.array(assetAttachmentSchema);

export const assetQrSchema = z.object({
  asset_id: requiredStringSchema,
  lookup_token: z.string().uuid(),
  lookup_url: z.string().url(),
  svg_base64: requiredStringSchema,
  label_text: requiredStringSchema,
});

export const assetHistoryEventSchema = z.object({
  id: requiredStringSchema,
  occurred_at: requiredStringSchema,
  action: requiredStringSchema,
  event_type: requiredStringSchema,
  summary: requiredStringSchema,
  actor_user_id: z.string().uuid().nullable(),
  actor_display_name: z.string().nullable(),
  resource_type: requiredStringSchema,
  resource_id: z.string().nullable(),
  changed_fields: z.array(z.string()),
});

export const assetHistoryPageSchema = z.object({
  items: z.array(assetHistoryEventSchema),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  total_pages: z.number().int().nonnegative(),
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
  failure_category: ticketFailureCategorySchema,
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

const dateOnlySchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Ngày phải có định dạng YYYY-MM-DD.");
const zonedDateTimeSchema = z.string().refine(
  (value) =>
    !Number.isNaN(new Date(value).getTime()) && /(Z|[+-]\d{2}:\d{2})$/.test(value),
  "Timestamp phải có timezone.",
);

export const ticketCreateRequestSchema = z.object({
  asset_id: z.string().trim().min(1, "Asset ID là bắt buộc.").max(50),
  issue_description: z.string().trim().min(5, "Mô tả cần ít nhất 5 ký tự.").max(1000),
  priority: ticketPrioritySchema,
  failure_category: ticketFailureCategorySchema,
  technician_id: z.string().trim().min(1, "Mã kỹ thuật viên là bắt buộc.").max(50),
  manager_note: z.string().trim().max(1000).nullable().optional(),
});

export const ticketUpdateRequestSchema = z
  .object({
    status: ticketStatusSchema.optional(),
    priority: ticketPrioritySchema.optional(),
    technician_id: z.string().trim().min(1).max(50).optional(),
    note: z.string().trim().max(1000).nullable().optional(),
    resolved_at: zonedDateTimeSchema.nullable().optional(),
  })
  .refine((request) => Object.values(request).some((value) => value !== undefined), {
    message: "Cần cung cấp ít nhất một trường để cập nhật.",
  });

export const maintenanceLogCreateRequestSchema = z
  .object({
    ticket_id: z.string().trim().min(1).max(50),
    asset_id: z.string().trim().min(1).max(50),
    maintenance_date: dateOnlySchema,
    inspection_result: z.string().trim().min(3, "Kết quả kiểm tra cần ít nhất 3 ký tự.").max(2000),
    actions_taken: z.string().trim().min(3, "Hành động cần ít nhất 3 ký tự.").max(2000),
    parts_replaced: z.string().trim().max(1000).nullable().optional(),
    technician_note: z.string().trim().min(1, "Ghi chú kỹ thuật viên là bắt buộc.").max(2000),
    maintenance_result: maintenanceResultSchema,
    follow_up_required: z.boolean(),
    next_maintenance_date: dateOnlySchema,
  })
  .superRefine((request, context) => {
    if (request.next_maintenance_date <= request.maintenance_date) {
      context.addIssue({
        code: "custom",
        path: ["next_maintenance_date"],
        message: "Ngày bảo trì kế tiếp phải sau ngày thực hiện.",
      });
    }
    const expectedFollowUp = request.maintenance_result !== "Đã xử lý";
    if (request.follow_up_required !== expectedFollowUp) {
      context.addIssue({
        code: "custom",
        path: ["follow_up_required"],
        message: "Trạng thái theo dõi chưa nhất quán với kết quả bảo trì.",
      });
    }
  });

export const backendValidationIssueSchema = z.object({
  loc: z.array(z.union([z.string(), z.number()])),
  msg: z.string(),
  type: z.string(),
  input: z.unknown().optional(),
  ctx: z.record(z.string(), z.unknown()).optional(),
});

export const backendErrorResponseSchema = z.object({
  detail: z.union([z.string(), z.array(backendValidationIssueSchema)]),
});

export const ticketCreateResponseSchema = ticketRecordSchema;
export const ticketUpdateResponseSchema = ticketRecordSchema;

export const maintenanceLogRecordSchema = z.object({
  log_id: requiredStringSchema,
  ticket_id: z.string().nullable(),
  asset_id: requiredStringSchema,
  maintenance_date: requiredStringSchema,
  maintenance_type: z.enum(["Bảo trì định kỳ", "Bảo trì sửa chữa"]),
  technician_id: requiredStringSchema,
  inspection_result: requiredStringSchema,
  actions_taken: requiredStringSchema,
  parts_replaced: z.string().nullable(),
  technician_note: requiredStringSchema,
  maintenance_result: maintenanceResultSchema,
  follow_up_required: z.boolean(),
  next_maintenance_date: requiredStringSchema,
});

export const maintenanceLogCreateResponseSchema = maintenanceLogRecordSchema;

export const copilotRetrievalStatusSchema = z.enum([
  "success",
  "relevant",
  "conversation",
  "unrelated",
  "unsupported_asset_type",
  "missing_asset_context",
  "unavailable",
  "empty",
  "low_relevance",
  "asset_context_mismatch",
  "prompt_injection",
  "unsafe_operation",
  "unsafe_conversation",
  "unsafe_context",
  "conflicting_evidence",
  "insufficient_evidence",
]);

export const copilotRelevanceStatusSchema = z.enum(["relevant", "not_relevant", "not_applicable"]);
export const copilotResponseModeSchema = z.enum([
  "llm_grounded",
  "llm_conversation",
  "deterministic_fallback",
]);
export const copilotEvidenceStatusSchema = z.enum([
  "sufficient",
  "limited",
  "insufficient",
  "not_applicable",
]);

const copilotConversationContextSchema = z.object({
  recent_intent: z.string().trim().max(40).nullable().optional(),
  resolved_asset_type: z.string().trim().max(80).nullable().optional(),
  resolved_failure_category: z.string().trim().max(80).nullable().optional(),
  previous_source_ids: z.array(z.string().regex(/^S[1-9][0-9]{0,2}$/)).max(10).default([]),
  previous_answer_summary: z.string().trim().max(600).default(""),
}).strict();

export const copilotAskRequestSchema = z.object({
  question: z.string().trim().min(1, "Câu hỏi không được để trống.").max(1000),
  asset_id: z.string().trim().min(1).max(100).nullable().optional(),
  top_k: z.number().int().min(1).max(20).default(5),
  document_type: z.string().trim().min(1).max(100).nullable().optional(),
  failure_category: z.string().trim().min(1).max(200).nullable().optional(),
  version: z.string().trim().min(1).max(40).nullable().optional(),
  language: z.string().regex(/^[a-z]{2,3}(?:-[A-Z]{2})?$/).nullable().optional(),
  conversation_context: copilotConversationContextSchema.nullable().optional(),
});

export const copilotSourceSchema = z.object({
  doc_id: requiredStringSchema,
  document_id: z.string().nullable().optional(),
  title: requiredStringSchema,
  doc_type: requiredStringSchema,
  document_type: z.string().nullable().optional(),
  asset_type: z.string().nullable().optional(),
  failure_category: z.string().nullable().optional(),
  version: z.string().nullable().optional(),
  effective_date: z.string().nullable().optional(),
  language: z.string().nullable().optional(),
  source: requiredStringSchema,
  score: z.number(),
  citation_ids: z.array(requiredStringSchema).default([]),
});

export const copilotRetrievedChunkSchema = z.object({
  chunk_id: requiredStringSchema,
  doc_id: z.string().optional(),
  document_id: z.string().nullable().optional(),
  title: z.string().optional(),
  doc_type: z.string().optional(),
  document_type: z.string().nullable().optional(),
  asset_type: z.string().nullable().optional(),
  failure_category: z.string().nullable().optional(),
  version: z.string().nullable().optional(),
  effective_date: z.string().nullable().optional(),
  language: z.string().nullable().optional(),
  source: z.string().optional(),
  score: z.number().optional(),
  text: z.string().optional(),
  content: z.string().optional(),
  chunk_index: z.number().int().nonnegative().optional(),
  citation_id: z.string().nullable().optional(),
});

const copilotCitedStatementSchema = z.object({
  text: requiredStringSchema,
  source_ids: z.array(requiredStringSchema).min(1),
});

const copilotStructuredAnswerSchema = z.object({
  summary: requiredStringSchema,
  summary_source_ids: z.array(requiredStringSchema).min(1),
  possible_causes: z.array(copilotCitedStatementSchema),
  recommended_checks: z.array(copilotCitedStatementSchema),
  safety_warnings: z.array(copilotCitedStatementSchema),
  escalation_required: z.boolean(),
  source_ids: z.array(requiredStringSchema).min(1),
  confidence: z.enum(["low", "medium", "high"]),
  insufficient_evidence: z.boolean(),
});

const copilotCitationValidationSchema = z.object({
  valid: z.boolean(),
  cited_source_ids: z.array(requiredStringSchema),
  invalid_source_ids: z.array(requiredStringSchema),
  coverage_complete: z.boolean(),
  support_complete: z.boolean().optional(),
  unsupported_claims: z.array(requiredStringSchema).optional(),
});

export const copilotAskResponseSchema = z.object({
  answer: requiredStringSchema,
  asset_context: z.record(z.string(), z.unknown()).nullable(),
  sources: z.array(copilotSourceSchema),
  retrieved_chunks: z.array(copilotRetrievedChunkSchema),
  retrieval_status: copilotRetrievalStatusSchema,
  relevance_status: copilotRelevanceStatusSchema,
  safety_notice: z.string(),
  filters_applied: z.record(z.string(), z.string()),
  response_mode: copilotResponseModeSchema.default("deterministic_fallback"),
  fallback_reason: z.string().nullable().default(null),
  structured_answer: copilotStructuredAnswerSchema.nullable().default(null),
  llm_provider: z.string().nullable().default(null),
  llm_model: z.string().nullable().default(null),
  evidence_status: copilotEvidenceStatusSchema.default("insufficient"),
  citation_validation: copilotCitationValidationSchema.nullable().default(null),
  context_warnings: z.array(requiredStringSchema).default([]),
  confidence: z.enum(["high", "medium", "low", "insufficient_evidence", "not_applicable"]).optional(),
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

export const roleCodeSchema = z.enum([
  "administrator",
  "property_manager",
  "chief_engineer",
  "technician",
  "helpdesk",
  "storekeeper",
]);

export const userResponseSchema = z.object({
  id: z.string().uuid(),
  username: requiredStringSchema,
  email: z.string().nullable(),
  display_name: requiredStringSchema,
  role: roleCodeSchema,
  role_display_name: requiredStringSchema,
  permissions: z.array(requiredStringSchema),
  technician_id: z.string().nullable(),
  is_active: z.boolean(),
  created_at: requiredStringSchema,
  updated_at: requiredStringSchema,
  last_login_at: z.string().nullable(),
  version: z.number().int().positive(),
});

export const authResponseSchema = z.object({
  access_token: requiredStringSchema,
  token_type: z.literal("bearer"),
  expires_at: requiredStringSchema,
  user: userResponseSchema,
});

export const loginRequestSchema = z.object({
  identifier: z.string().trim().min(1, "Tên đăng nhập là bắt buộc.").max(254),
  password: z.string().min(1, "Mật khẩu là bắt buộc.").max(256),
});

export const userCreateRequestSchema = z.object({
  username: z.string().trim().min(3).max(100).regex(/^[a-zA-Z0-9._-]+$/),
  email: z.string().trim().email().max(254).nullable().optional(),
  password: z.string().min(12, "Mật khẩu cần ít nhất 12 ký tự.").max(256),
  display_name: z.string().trim().min(2).max(200),
  role: roleCodeSchema,
  technician_id: z.string().trim().min(1).max(50).nullable().optional(),
  is_active: z.boolean().default(true),
});

export const userUpdateRequestSchema = z
  .object({
    display_name: z.string().trim().min(2).max(200).optional(),
    role: roleCodeSchema.optional(),
    technician_id: z.string().trim().max(50).nullable().optional(),
    is_active: z.boolean().optional(),
  })
  .refine((request) => Object.values(request).some((value) => value !== undefined), {
    message: "Cần cung cấp ít nhất một trường để cập nhật.",
  });

export const roleOptionSchema = z.object({
  code: roleCodeSchema,
  display_name: requiredStringSchema,
  permissions: z.array(requiredStringSchema),
});

export const auditLogSchema = z.object({
  id: z.string().uuid(),
  occurred_at: requiredStringSchema,
  actor_user_id: z.string().uuid().nullable(),
  actor_display_name: z.string().nullable(),
  action: requiredStringSchema,
  resource_type: requiredStringSchema,
  resource_id: z.string().nullable(),
  request_id: requiredStringSchema,
  before_state: z.record(z.string(), z.unknown()).nullable(),
  after_state: z.record(z.string(), z.unknown()).nullable(),
  metadata: z.record(z.string(), z.unknown()).nullable(),
  outcome: requiredStringSchema,
});

export const auditLogPageSchema = z.object({
  items: z.array(auditLogSchema),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  total_pages: z.number().int().nonnegative(),
});

export const usersResponseSchema = z.array(userResponseSchema);
export const roleOptionsResponseSchema = z.array(roleOptionSchema);

export type HealthResponse = z.infer<typeof healthResponseSchema>;
export type SummaryResponse = z.infer<typeof summaryResponseSchema>;
export type AssetRecord = z.infer<typeof assetRecordSchema>;
export type AssetOverviewRecord = z.infer<typeof assetOverviewRecordSchema>;
export type AssetProfile = z.infer<typeof assetProfileSchema>;
export type AssetCatalogPage = z.infer<typeof assetCatalogPageSchema>;
export type AssetOptions = z.infer<typeof assetOptionsSchema>;
export type LocationRecord = z.infer<typeof locationRecordSchema>;
export type AssetCreateRequest = z.infer<typeof assetCreateRequestSchema>;
export type AssetUpdateRequest = z.infer<typeof assetUpdateRequestSchema>;
export type OperationalStatusRequest = z.infer<typeof operationalStatusRequestSchema>;
export type LifecycleTransitionRequest = z.infer<typeof lifecycleTransitionRequestSchema>;
export type AssetArchiveRequest = z.infer<typeof assetArchiveRequestSchema>;
export type AssetRestoreRequest = z.infer<typeof assetRestoreRequestSchema>;
export type AssetAttachment = z.infer<typeof assetAttachmentSchema>;
export type AssetQr = z.infer<typeof assetQrSchema>;
export type AssetHistoryPage = z.infer<typeof assetHistoryPageSchema>;
export type RiskRecord = z.infer<typeof riskRecordSchema>;
export type AnomalyRecord = z.infer<typeof anomalyRecordSchema>;
export type PreventiveRecord = z.infer<typeof preventiveRecordSchema>;
export type RecurringIssueRecord = z.infer<typeof recurringIssueRecordSchema>;
export type MaintenanceKpiResponse = z.infer<typeof maintenanceKpiResponseSchema>;
export type TicketRecord = z.infer<typeof ticketRecordSchema>;
export type MaintenanceLogRecord = z.infer<typeof maintenanceLogRecordSchema>;
export type AssetDetailsResponse = z.infer<typeof assetDetailsResponseSchema>;
export type TicketCreateRequest = z.infer<typeof ticketCreateRequestSchema>;
export type TicketCreateResponse = z.infer<typeof ticketCreateResponseSchema>;
export type TicketUpdateRequest = z.infer<typeof ticketUpdateRequestSchema>;
export type TicketUpdateResponse = z.infer<typeof ticketUpdateResponseSchema>;
export type MaintenanceLogCreateRequest = z.infer<typeof maintenanceLogCreateRequestSchema>;
export type MaintenanceLogCreateResponse = z.infer<typeof maintenanceLogCreateResponseSchema>;
export type CopilotAskRequest = z.infer<typeof copilotAskRequestSchema>;
export type CopilotAskResponse = z.infer<typeof copilotAskResponseSchema>;
export type CopilotSource = z.infer<typeof copilotSourceSchema>;
export type CopilotRetrievedChunk = z.infer<typeof copilotRetrievedChunkSchema>;
export type CopilotRetrievalStatus = z.infer<typeof copilotRetrievalStatusSchema>;
export type CopilotResponseMode = z.infer<typeof copilotResponseModeSchema>;
export type CopilotEvidenceStatus = z.infer<typeof copilotEvidenceStatusSchema>;
export type BackendErrorResponse = z.infer<typeof backendErrorResponseSchema>;
export type RoleCode = z.infer<typeof roleCodeSchema>;
export type UserResponse = z.infer<typeof userResponseSchema>;
export type AuthResponse = z.infer<typeof authResponseSchema>;
export type LoginRequest = z.infer<typeof loginRequestSchema>;
export type UserCreateRequest = z.infer<typeof userCreateRequestSchema>;
export type UserUpdateRequest = z.infer<typeof userUpdateRequestSchema>;
export type RoleOption = z.infer<typeof roleOptionSchema>;
export type AuditLogRecord = z.infer<typeof auditLogSchema>;
export type AuditLogPage = z.infer<typeof auditLogPageSchema>;
