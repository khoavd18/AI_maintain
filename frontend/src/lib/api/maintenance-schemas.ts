import { z } from "zod";

const text = z.string().min(1);
const nullableText = z.string().nullable();
const optionSchema = z.object({ code: text, display_name: text });

export const technicianOptionSchema = z.object({
  id: z.string().uuid(),
  display_name: text,
  role: text,
  technician_id: text,
  is_active: z.boolean(),
});

export const maintenanceOptionsSchema = z.object({
  plan_statuses: z.array(optionSchema),
  interval_units: z.array(optionSchema),
  work_order_types: z.array(optionSchema),
  work_order_statuses: z.array(optionSchema),
  checklist_response_types: z.array(optionSchema),
  priorities: z.array(optionSchema),
  maintenance_results: z.array(optionSchema),
  evidence_categories: z.array(optionSchema),
  technicians: z.array(technicianOptionSchema),
});

export const checklistTemplateItemSchema = z.object({
  id: z.string().uuid(),
  sequence: z.number().int().positive(),
  instruction: text,
  response_type: text,
  response_type_display: text,
  is_required: z.boolean(),
  safety_critical: z.boolean(),
  allow_not_applicable: z.boolean(),
  expected_unit: nullableText,
  minimum_value: z.number().nullable(),
  maximum_value: z.number().nullable(),
  guidance: nullableText,
});

export const checklistTemplateSchema = z.object({
  id: z.string().uuid(),
  code: text,
  name: text,
  asset_type: nullableText,
  description: nullableText,
  version_number: z.number().int().positive(),
  status: text,
  status_display: text,
  created_by_user_id: z.string().uuid(),
  created_at: text,
  updated_at: text,
  archived_at: nullableText,
  version: z.number().int().positive(),
  item_count: z.number().int().nonnegative(),
  items: z.array(checklistTemplateItemSchema),
});

export const checklistTemplatePageSchema = z.object({
  items: z.array(checklistTemplateSchema),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  total_pages: z.number().int().nonnegative(),
});

export const checklistItemRequestSchema = z.object({
  sequence: z.number().int().min(1).max(100),
  instruction: z.string().trim().min(2).max(2000),
  response_type: z.enum(["checkbox", "pass_fail", "numeric", "text"]),
  is_required: z.boolean(),
  safety_critical: z.boolean(),
  allow_not_applicable: z.boolean(),
  expected_unit: z.string().trim().max(40).nullable(),
  minimum_value: z.number().nullable(),
  maximum_value: z.number().nullable(),
  guidance: z.string().trim().max(2000).nullable(),
}).superRefine((item, context) => {
  if (item.response_type !== "numeric" && (item.expected_unit !== null || item.minimum_value !== null || item.maximum_value !== null)) {
    context.addIssue({ code: "custom", path: ["response_type"], message: "Đơn vị và giới hạn chỉ dùng cho kiểu numeric." });
  }
  if (item.minimum_value !== null && item.maximum_value !== null && item.minimum_value > item.maximum_value) {
    context.addIssue({ code: "custom", path: ["maximum_value"], message: "Giá trị tối đa phải lớn hơn hoặc bằng giá trị tối thiểu." });
  }
});

export const checklistTemplateCreateRequestSchema = z.object({
  code: z.string().trim().min(3).max(50),
  name: z.string().trim().min(2).max(200),
  asset_type: z.enum(["hvac", "pump", "generator"]).nullable(),
  description: z.string().trim().max(2000).nullable(),
  items: z.array(checklistItemRequestSchema).min(1).max(100),
});

export const maintenancePlanSchema = z.object({
  id: z.string().uuid(),
  plan_code: text,
  name: text,
  description: nullableText,
  asset_id: text,
  asset_name: text,
  schedule_type: text,
  interval_value: z.number().int().positive(),
  interval_unit: text,
  recurrence_summary: text,
  recurrence_rule: nullableText,
  start_date: text,
  end_date: nullableText,
  local_timezone: text,
  lead_time_days: z.number().int().nonnegative(),
  grace_period_days: z.number().int().nonnegative(),
  next_due_date: nullableText,
  last_generated_due_date: nullableText,
  estimated_duration_minutes: z.number().int().positive(),
  default_priority: text,
  default_priority_display: text,
  default_assignee_user_id: z.string().uuid().nullable(),
  default_assignee_name: nullableText,
  checklist_template_id: z.string().uuid().nullable(),
  checklist_template_name: nullableText,
  instructions: nullableText,
  status: text,
  status_display: text,
  is_active: z.boolean(),
  paused_at: nullableText,
  archived_at: nullableText,
  archive_reason: nullableText,
  created_by_user_id: z.string().uuid(),
  updated_by_user_id: z.string().uuid(),
  created_at: text,
  updated_at: text,
  version: z.number().int().positive(),
});

export const maintenancePlanPageSchema = z.object({
  items: z.array(maintenancePlanSchema),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  total_pages: z.number().int().nonnegative(),
});

const maintenancePlanRequestFieldsSchema = z.object({
  plan_code: z.string().trim().min(3).max(50),
  name: z.string().trim().min(2).max(200),
  description: z.string().trim().max(2000).nullable(),
  asset_id: z.string().trim().min(1).max(50),
  interval_value: z.number().int().min(1).max(366),
  interval_unit: z.enum(["day", "week", "month", "year"]),
  start_date: text,
  end_date: nullableText,
  local_timezone: z.string().trim().min(1).max(64),
  lead_time_days: z.number().int().min(0).max(365),
  grace_period_days: z.number().int().min(0).max(365),
  estimated_duration_minutes: z.number().int().min(1).max(10080),
  default_priority: z.enum(["low", "medium", "high", "critical"]),
  default_assignee_user_id: z.string().uuid().nullable(),
  checklist_template_id: z.string().uuid().nullable(),
  instructions: z.string().trim().max(4000).nullable(),
  recurrence_rule: z.null(),
});

export const maintenancePlanCreateRequestSchema = maintenancePlanRequestFieldsSchema.superRefine((plan, context) => {
  if (plan.end_date !== null && plan.end_date < plan.start_date) {
    context.addIssue({ code: "custom", path: ["end_date"], message: "Ngày kết thúc không được sớm hơn ngày bắt đầu." });
  }
});

export const maintenancePlanUpdateRequestSchema = maintenancePlanRequestFieldsSchema
  .omit({ plan_code: true, asset_id: true, recurrence_rule: true })
  .partial()
  .extend({ expected_version: z.number().int().positive() })
  .superRefine((plan, context) => {
    if (plan.end_date && plan.start_date && plan.end_date < plan.start_date) {
      context.addIssue({ code: "custom", path: ["end_date"], message: "Ngày kết thúc không được sớm hơn ngày bắt đầu." });
    }
  });

export const occurrencePreviewSchema = z.object({
  plan_id: z.string().uuid(),
  timezone: text,
  date_from: text,
  date_to: text,
  items: z.array(z.object({
    due_date: text,
    generated: z.boolean(),
    generation_release_date: text,
  })),
});

export const workOrderChecklistItemSchema = z.object({
  id: z.string().uuid(),
  source_template_item_id: z.string().uuid().nullable(),
  sequence: z.number().int().positive(),
  instruction: text,
  response_type: text,
  response_type_display: text,
  is_required: z.boolean(),
  safety_critical: z.boolean(),
  allow_not_applicable: z.boolean(),
  expected_unit: nullableText,
  minimum_value: z.number().nullable(),
  maximum_value: z.number().nullable(),
  guidance: nullableText,
  result_status: text,
  result_status_display: text,
  boolean_value: z.boolean().nullable(),
  numeric_value: z.number().nullable(),
  text_value: nullableText,
  note: nullableText,
  completed_by_user_id: z.string().uuid().nullable(),
  completed_at: nullableText,
});

export const workOrderHistoryItemSchema = z.object({
  id: z.string().uuid(),
  occurred_at: text,
  actor_display_name: nullableText,
  action: text,
  resource_type: text,
  resource_id: nullableText,
});

export const workOrderSchema = z.object({
  id: z.string().uuid(),
  work_order_number: text,
  title: text,
  description: nullableText,
  work_order_type: text,
  work_order_type_display: text,
  asset_id: text,
  asset_name: text,
  location: nullableText,
  preventive_plan_id: z.string().uuid().nullable(),
  preventive_plan_code: nullableText,
  source_ticket_id: nullableText,
  assigned_to_user_id: z.string().uuid().nullable(),
  assigned_to_name: nullableText,
  created_by_user_id: z.string().uuid(),
  verified_by_user_id: z.string().uuid().nullable(),
  verified_by_name: nullableText,
  maintenance_log_id: nullableText,
  priority: text,
  priority_display: text,
  scheduled_start_at: nullableText,
  scheduled_end_at: nullableText,
  due_date: text,
  local_timezone: text,
  grace_period_days: z.number().int().nonnegative(),
  is_overdue: z.boolean(),
  estimated_duration_minutes: z.number().int().positive(),
  started_at: nullableText,
  completed_at: nullableText,
  verified_at: nullableText,
  cancelled_at: nullableText,
  cancellation_reason: nullableText,
  completion_summary: nullableText,
  safety_notes: nullableText,
  labor_minutes: z.number().int().nonnegative().nullable(),
  status: text,
  status_display: text,
  hold_reason: nullableText,
  created_at: text,
  updated_at: text,
  version: z.number().int().positive(),
  checklist: z.array(workOrderChecklistItemSchema),
  history: z.array(workOrderHistoryItemSchema),
});

export const workOrderPageSchema = z.object({
  items: z.array(workOrderSchema),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  total_pages: z.number().int().nonnegative(),
});

export const workOrderCreateRequestSchema = z.object({
  title: z.string().trim().min(2).max(200),
  description: z.string().trim().max(4000).nullable(),
  work_order_type: z.enum(["preventive", "corrective", "inspection", "emergency"]),
  asset_id: z.string().trim().min(1).max(50),
  preventive_plan_id: z.string().uuid().nullable(),
  source_ticket_id: z.string().trim().max(50).nullable(),
  assigned_to_user_id: z.string().uuid().nullable(),
  priority: z.enum(["low", "medium", "high", "critical"]),
  scheduled_start_at: nullableText,
  scheduled_end_at: nullableText,
  due_date: text,
  local_timezone: text,
  grace_period_days: z.number().int().min(0).max(365),
  estimated_duration_minutes: z.number().int().min(1).max(10080),
  checklist_template_id: z.string().uuid().nullable(),
});

export const workOrderUpdateRequestSchema = workOrderCreateRequestSchema
  .pick({ title: true, description: true, priority: true, scheduled_start_at: true, scheduled_end_at: true, due_date: true, estimated_duration_minutes: true })
  .partial()
  .extend({ expected_version: z.number().int().positive() });

export const workOrderChecklistUpdateRequestSchema = z.object({
  expected_version: z.number().int().positive(),
  responses: z.array(z.object({
    item_id: z.string().uuid(),
    result_status: z.enum(["completed", "pass", "fail", "not_applicable"]),
    boolean_value: z.boolean().nullable(),
    numeric_value: z.number().nullable(),
    text_value: z.string().max(2000).nullable(),
    note: z.string().max(1000).nullable(),
  })).min(1),
});

export const workOrderCompleteRequestSchema = z.object({
  expected_version: z.number().int().positive(),
  maintenance_date: text,
  inspection_result: z.string().trim().min(2).max(4000),
  actions_taken: z.string().trim().min(2).max(4000),
  parts_replaced: z.string().trim().max(2000).nullable(),
  technician_note: z.string().trim().min(2).max(4000),
  maintenance_result: z.enum(["resolved", "partially_resolved", "monitoring_required", "vendor_required"]),
  follow_up_required: z.boolean(),
  completion_summary: z.string().trim().min(2).max(4000),
  safety_notes: z.string().trim().max(4000).nullable(),
  labor_minutes: z.number().int().min(0).max(10080),
});

export const generationRequestSchema = z.object({
  as_of_date: text,
  plan_id: z.string().uuid().nullable(),
});

export const generationResponseSchema = z.object({
  dry_run: z.boolean(),
  as_of_date: text,
  requested_by_user_id: z.string().uuid(),
  generated_count: z.number().int().nonnegative(),
  would_generate_count: z.number().int().nonnegative(),
  skipped_count: z.number().int().nonnegative(),
  plans: z.array(z.object({
    plan_id: z.string().uuid(),
    plan_code: text,
    generated: z.array(text),
    would_generate_due_dates: z.array(text),
    skipped_due_dates: z.array(text),
    reason: nullableText,
  })),
});

export const workOrderAttachmentSchema = z.object({
  id: z.string().uuid(),
  work_order_id: z.string().uuid(),
  asset_id: text,
  category: text,
  category_display: text,
  original_filename: text,
  media_type: text,
  size_bytes: z.number().int().positive(),
  checksum: text,
  uploaded_by_user_id: z.string().uuid(),
  created_at: text,
  deleted_at: nullableText,
  deleted_by_user_id: z.string().uuid().nullable(),
});

export const workOrderAttachmentsSchema = z.array(workOrderAttachmentSchema);

export const scheduleViewSchema = z.object({
  date_from: text,
  date_to: text,
  work_orders: z.array(workOrderSchema),
  upcoming_occurrences: z.array(z.object({
    due_date: text,
    generated: z.boolean(),
    generation_release_date: text,
    plan_id: z.string().uuid(),
    plan_code: text,
    plan_name: text,
    asset_id: text,
  })),
});

export const workOrderMetricsSchema = z.object({
  as_of_date: text,
  total_work_orders: z.number().int().nonnegative(),
  by_status: z.record(z.string(), z.number().int().nonnegative()),
  overdue_count: z.number().int().nonnegative(),
  upcoming_preventive_count: z.number().int().nonnegative(),
  completed_count: z.number().int().nonnegative(),
  verified_count: z.number().int().nonnegative(),
  completed_on_time_count: z.number().int().nonnegative(),
  technician_workload: z.array(z.object({
    user_id: text,
    display_name: nullableText,
    open_count: z.number().int().nonnegative(),
  })),
  data_notice: text,
});

export type MaintenanceOptions = z.infer<typeof maintenanceOptionsSchema>;
export type MaintenancePlan = z.infer<typeof maintenancePlanSchema>;
export type MaintenancePlanCreateRequest = z.infer<typeof maintenancePlanCreateRequestSchema>;
export type MaintenancePlanUpdateRequest = z.infer<typeof maintenancePlanUpdateRequestSchema>;
export type ChecklistTemplate = z.infer<typeof checklistTemplateSchema>;
export type ChecklistTemplateCreateRequest = z.infer<typeof checklistTemplateCreateRequestSchema>;
export type WorkOrder = z.infer<typeof workOrderSchema>;
export type WorkOrderCreateRequest = z.infer<typeof workOrderCreateRequestSchema>;
export type WorkOrderUpdateRequest = z.infer<typeof workOrderUpdateRequestSchema>;
export type WorkOrderChecklistUpdateRequest = z.infer<typeof workOrderChecklistUpdateRequestSchema>;
export type WorkOrderCompleteRequest = z.infer<typeof workOrderCompleteRequestSchema>;
export type GenerationRequest = z.infer<typeof generationRequestSchema>;
export type WorkOrderAttachment = z.infer<typeof workOrderAttachmentSchema>;
