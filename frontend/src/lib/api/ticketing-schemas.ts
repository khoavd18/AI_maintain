import { z } from "zod";

const requiredText = z.string().min(1);
const nullableText = z.string().nullable();
const uuid = z.string().uuid();
const nullableUuid = uuid.nullable();
const jsonObject = z.record(z.string(), z.unknown());

export const ticketStatusSchema = z.enum([
  "open",
  "assigned",
  "in_progress",
  "waiting",
  "resolved",
  "closed",
  "cancelled",
  "reopened",
]);
export const ticketImpactSchema = z.enum(["low", "medium", "high", "critical"]);
export const ticketUrgencySchema = z.enum(["low", "medium", "high", "immediate"]);
export const ticketPriorityCodeSchema = z.enum(["low", "medium", "high", "critical"]);
export const commentVisibilitySchema = z.enum(["internal", "requester"]);
export const ticketQueueSchema = z.enum([
  "unassigned",
  "assigned_to_me",
  "assigned_to_queue",
  "critical",
  "due_soon",
  "sla_breached",
  "waiting",
  "recently_resolved",
  "reopened",
]);

export const ticketingOptionSchema = z.object({
  code: requiredText,
  display_name: requiredText,
});

export const ticketReferenceSchema = z.object({
  id: uuid,
  code: requiredText,
  name: requiredText,
  is_active: z.boolean(),
  category_id: nullableUuid.optional(),
});

export const ticketAssigneeSchema = z.object({
  id: uuid,
  display_name: requiredText,
  role: requiredText,
  technician_id: nullableText,
  is_active: z.boolean(),
});

export const priorityMatrixRecordSchema = z.object({
  impact: ticketImpactSchema,
  urgency: ticketUrgencySchema,
  priority: ticketPriorityCodeSchema,
  priority_display: requiredText,
});

export const ticketingOptionsSchema = z.object({
  categories: z.array(ticketReferenceSchema),
  subcategories: z.array(ticketReferenceSchema),
  intake_sources: z.array(ticketReferenceSchema),
  support_groups: z.array(ticketReferenceSchema),
  assignees: z.array(ticketAssigneeSchema),
  statuses: z.array(ticketingOptionSchema),
  impacts: z.array(ticketingOptionSchema),
  urgencies: z.array(ticketingOptionSchema),
  priorities: z.array(ticketingOptionSchema),
  comment_visibilities: z.array(ticketingOptionSchema),
  sla_statuses: z.array(ticketingOptionSchema),
  queues: z.array(ticketingOptionSchema),
  failure_categories: z.array(ticketingOptionSchema),
  priority_matrix: z.array(priorityMatrixRecordSchema),
});

export const priorityPreviewSchema = z.object({
  impact: ticketImpactSchema,
  impact_display: requiredText,
  urgency: ticketUrgencySchema,
  urgency_display: requiredText,
  priority: ticketPriorityCodeSchema,
  priority_display: requiredText,
});

export const ticketIntakeRequestSchema = z.object({
  asset_id: z.string().trim().min(1, "Asset ID là bắt buộc.").max(50),
  issue_description: z
    .string()
    .trim()
    .min(5, "Mô tả cần ít nhất 5 ký tự.")
    .max(4000),
  failure_category: z.enum([
    "cooling_issue",
    "vibration_issue",
    "electrical_issue",
    "pressure_issue",
    "runtime_issue",
    "sensor_issue",
    "false_alarm",
    "no_failure",
  ]),
  reporter_name: z.string().trim().max(200).nullable(),
  reporter_email: z
    .union([z.string().trim().email("Email người báo không hợp lệ."), z.literal("")])
    .nullable()
    .transform((value) => value || null),
  reporter_phone: z.string().trim().max(40).nullable(),
  category_id: nullableUuid,
  subcategory_id: nullableUuid,
  impact: ticketImpactSchema,
  urgency: ticketUrgencySchema,
  intake_source_id: nullableUuid,
  support_group_id: nullableUuid,
  assigned_user_id: nullableUuid,
  manager_note: z.string().trim().max(1000).nullable(),
});

export const slaClockSchema = z.object({
  status: requiredText,
  status_display: requiredText,
  due_at: requiredText,
  completed_at: nullableText,
  remaining_business_minutes: z.number().int().nullable(),
});

export const ticketSlaSchema = z.object({
  id: uuid,
  policy_id: uuid,
  policy_code: requiredText,
  policy_name: requiredText,
  calendar_id: uuid,
  calendar_code: requiredText,
  timezone: requiredText,
  calendar_snapshot: jsonObject,
  pause_on_waiting: z.boolean(),
  due_soon_percent: z.number().int().min(1).max(100),
  first_response_target_minutes: z.number().int().positive(),
  resolution_target_minutes: z.number().int().positive(),
  started_at: requiredText,
  first_response_due_at: requiredText,
  resolution_due_at: requiredText,
  first_response_remaining_minutes: z.number().int().nullable(),
  resolution_remaining_minutes: z.number().int().nullable(),
  paused_at: nullableText,
  resolution_stopped_at: nullableText,
  occurrence_number: z.number().int().positive(),
  version: z.number().int().positive(),
  first_response: slaClockSchema,
  resolution: slaClockSchema,
});

export const ticketCommentSchema = z.object({
  id: uuid,
  ticket_id: requiredText,
  author_user_id: uuid,
  author_name: requiredText,
  visibility: commentVisibilitySchema,
  body: requiredText,
  created_at: requiredText,
  attachments: z.array(
    z.object({
      asset_attachment_id: nullableUuid,
      work_order_attachment_id: nullableUuid,
    }),
  ),
});

export const ticketSlaEventSchema = z.object({
  id: uuid,
  event_type: requiredText,
  clock_type: nullableText,
  occurrence_number: z.number().int().positive(),
  occurred_at: requiredText,
  details: jsonObject.nullable(),
});

export const ticketEscalationSchema = z.object({
  id: uuid,
  ticket_id: requiredText,
  rule_code: requiredText,
  clock_type: nullableText,
  occurrence_number: z.number().int().positive(),
  detected_at: requiredText,
  due_at: nullableText,
  details: jsonObject.nullable(),
});

export const linkedTicketWorkOrderSchema = z.object({
  id: uuid,
  work_order_number: requiredText,
  title: requiredText,
  status: requiredText,
  priority: requiredText,
  due_date: requiredText,
});

export const ticketDetailSchema = z.object({
  ticket_id: requiredText,
  asset_id: requiredText,
  issue_description: requiredText,
  failure_category: requiredText,
  failure_category_display: requiredText,
  reporter_name: nullableText,
  reporter_email: nullableText,
  reporter_phone: nullableText,
  reporter_redacted: z.boolean(),
  category_id: nullableUuid,
  category_name: nullableText,
  subcategory_id: nullableUuid,
  subcategory_name: nullableText,
  impact: ticketImpactSchema,
  impact_display: requiredText,
  urgency: ticketUrgencySchema,
  urgency_display: requiredText,
  priority: ticketPriorityCodeSchema,
  priority_display: requiredText,
  status: ticketStatusSchema,
  status_display: requiredText,
  intake_source_id: nullableUuid,
  intake_source_name: nullableText,
  support_group_id: nullableUuid,
  support_group_name: nullableText,
  assigned_user_id: nullableUuid,
  assigned_user_name: nullableText,
  technician_id: requiredText,
  created_at: requiredText,
  first_response_at: nullableText,
  waiting_reason: nullableText,
  waiting_previous_status: nullableText,
  resolved_at: nullableText,
  closed_at: nullableText,
  reopened_at: nullableText,
  cancelled_at: nullableText,
  cancellation_reason: nullableText,
  reopen_count: z.number().int().nonnegative(),
  manager_note: nullableText,
  note: nullableText,
  updated_at: requiredText,
  version: z.number().int().positive(),
  sla: ticketSlaSchema.nullable(),
  comments: z.array(ticketCommentSchema).default([]),
  sla_events: z.array(ticketSlaEventSchema).default([]),
  escalations: z.array(ticketEscalationSchema).default([]),
  linked_work_orders: z.array(linkedTicketWorkOrderSchema).default([]),
});

export const ticketQueuePageSchema = z.object({
  items: z.array(ticketDetailSchema),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  queue: ticketQueueSchema,
  queue_display: requiredText,
  as_of: requiredText,
});

export const versionedActionSchema = z.object({
  expected_version: z.number().int().positive(),
});
export const ticketAssignRequestSchema = versionedActionSchema.extend({
  assigned_user_id: nullableUuid,
  support_group_id: nullableUuid,
});
export const ticketReasonActionSchema = versionedActionSchema.extend({
  reason: z.string().trim().min(3, "Lý do cần ít nhất 3 ký tự.").max(1000),
});
export const ticketResolveRequestSchema = versionedActionSchema.extend({
  resolved_at: z.string().nullable().optional(),
});
export const ticketPriorityRequestSchema = ticketReasonActionSchema.extend({
  impact: ticketImpactSchema,
  urgency: ticketUrgencySchema,
});
export const ticketSlaOverrideRequestSchema = ticketReasonActionSchema.extend({
  policy_id: uuid,
});
export const ticketCommentRequestSchema = z.object({
  visibility: commentVisibilitySchema,
  body: z.string().trim().min(1, "Nội dung comment là bắt buộc.").max(4000),
  asset_attachment_ids: z.array(uuid).max(10).default([]),
  work_order_attachment_ids: z.array(uuid).max(10).default([]),
});

export const workingPeriodSchema = z.object({
  weekday: z.number().int().min(0).max(6),
  start_time: requiredText,
  end_time: requiredText,
});
export const calendarHolidaySchema = z.object({
  holiday_date: requiredText,
  name: requiredText,
});
export const businessCalendarSchema = z.object({
  id: uuid,
  code: requiredText,
  name: requiredText,
  timezone: requiredText,
  is_active: z.boolean(),
  periods: z.array(workingPeriodSchema),
  holidays: z.array(calendarHolidaySchema),
  version: z.number().int().positive(),
});
export const businessCalendarRequestSchema = z.object({
  code: z.string().trim().min(3).max(50),
  name: z.string().trim().min(1).max(160),
  timezone: z.string().trim().min(1).max(64),
  is_active: z.boolean(),
  periods: z.array(workingPeriodSchema).min(1).max(21),
  holidays: z.array(calendarHolidaySchema).max(366),
});
export const businessCalendarUpdateRequestSchema =
  businessCalendarRequestSchema.extend({
    expected_version: z.number().int().positive(),
  });

export const slaPolicyTargetSchema = z.object({
  priority: ticketPriorityCodeSchema,
  first_response_minutes: z.number().int().positive().max(525600),
  resolution_minutes: z.number().int().positive().max(525600),
});
export const slaPolicySchema = z.object({
  id: uuid,
  code: requiredText,
  name: requiredText,
  calendar_id: uuid,
  calendar_code: requiredText,
  calendar: businessCalendarSchema.nullable(),
  category_id: nullableUuid,
  category_name: nullableText,
  timezone: requiredText,
  pause_on_waiting: z.boolean(),
  due_soon_percent: z.number().int().min(1).max(100),
  effective_from: requiredText,
  effective_to: nullableText,
  is_active: z.boolean(),
  targets: z.array(slaPolicyTargetSchema),
  version: z.number().int().positive(),
});
export const slaPolicyRequestSchema = z
  .object({
    code: z.string().trim().min(3).max(50),
    name: z.string().trim().min(1).max(200),
    calendar_id: uuid,
    category_id: nullableUuid,
    timezone: z.string().trim().min(1).max(64),
    pause_on_waiting: z.boolean(),
    due_soon_percent: z.number().int().min(1).max(100),
    effective_from: requiredText,
    effective_to: nullableText,
    is_active: z.boolean(),
    targets: z.array(slaPolicyTargetSchema).length(4),
  })
  .refine(
    (value) => !value.effective_to || value.effective_to >= value.effective_from,
    {
      path: ["effective_to"],
      message: "Ngày kết thúc không được sớm hơn ngày hiệu lực.",
    },
  );
export const slaPolicyUpdateRequestSchema = slaPolicyRequestSchema.safeExtend({
  expected_version: z.number().int().positive(),
});

export const slaSummarySchema = z.object({
  as_of: requiredText,
  active_count: z.number().int().nonnegative(),
  waiting_count: z.number().int().nonnegative(),
  critical_count: z.number().int().nonnegative(),
  due_soon_count: z.number().int().nonnegative(),
  breached_count: z.number().int().nonnegative(),
  without_sla_count: z.number().int().nonnegative(),
});

export const escalationEvaluationRequestSchema = z.object({
  dry_run: z.boolean(),
  as_of: z.string().nullable().optional(),
});
export const escalationCandidateSchema = z.object({
  ticket_id: requiredText,
  rule_code: requiredText,
  rule_display: requiredText,
  clock_type: nullableText,
  occurrence_number: z.number().int().positive(),
  due_at: nullableText,
});
export const escalationEvaluationSchema = z.object({
  dry_run: z.boolean(),
  as_of: requiredText,
  candidate_count: z.number().int().nonnegative(),
  created_count: z.number().int().nonnegative(),
  candidates: z.array(escalationCandidateSchema),
});

export type TicketStatusCode = z.infer<typeof ticketStatusSchema>;
export type TicketImpact = z.infer<typeof ticketImpactSchema>;
export type TicketUrgency = z.infer<typeof ticketUrgencySchema>;
export type TicketPriorityCode = z.infer<typeof ticketPriorityCodeSchema>;
export type TicketQueue = z.infer<typeof ticketQueueSchema>;
export type TicketingOptions = z.infer<typeof ticketingOptionsSchema>;
export type PriorityPreview = z.infer<typeof priorityPreviewSchema>;
export type TicketIntakeRequest = z.infer<typeof ticketIntakeRequestSchema>;
export type TicketDetail = z.infer<typeof ticketDetailSchema>;
export type TicketQueuePage = z.infer<typeof ticketQueuePageSchema>;
export type VersionedAction = z.infer<typeof versionedActionSchema>;
export type TicketAssignRequest = z.infer<typeof ticketAssignRequestSchema>;
export type TicketReasonAction = z.infer<typeof ticketReasonActionSchema>;
export type TicketResolveRequest = z.infer<typeof ticketResolveRequestSchema>;
export type TicketPriorityRequest = z.infer<typeof ticketPriorityRequestSchema>;
export type TicketSlaOverrideRequest = z.infer<typeof ticketSlaOverrideRequestSchema>;
export type TicketCommentRequest = z.infer<typeof ticketCommentRequestSchema>;
export type BusinessCalendar = z.infer<typeof businessCalendarSchema>;
export type BusinessCalendarRequest = z.infer<typeof businessCalendarRequestSchema>;
export type BusinessCalendarUpdateRequest = z.infer<
  typeof businessCalendarUpdateRequestSchema
>;
export type SlaPolicy = z.infer<typeof slaPolicySchema>;
export type SlaPolicyRequest = z.infer<typeof slaPolicyRequestSchema>;
export type SlaPolicyUpdateRequest = z.infer<typeof slaPolicyUpdateRequestSchema>;
export type EscalationEvaluationRequest = z.infer<
  typeof escalationEvaluationRequestSchema
>;
