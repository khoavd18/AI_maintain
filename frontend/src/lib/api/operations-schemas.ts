import { z } from "zod";

const text = z.string().min(1);
const nullableText = z.string().nullable();
const uuid = z.string().uuid();

export const notificationSeveritySchema = z.enum(["info", "warning", "critical"]);
export const notificationSchema = z.object({
  id: uuid,
  notification_type: text,
  title: text,
  body: text,
  structured_content: z.record(z.string(), z.unknown()).nullable(),
  severity: notificationSeveritySchema,
  related_entity_type: nullableText,
  related_entity_id: nullableText,
  created_at: text,
  read_at: nullableText,
  dismissed_at: nullableText,
  version: z.number().int().positive(),
});
export const notificationPageSchema = z.object({
  items: z.array(notificationSchema),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
});
export const unreadCountSchema = z.object({
  unread_count: z.number().int().nonnegative(),
});
export const versionRequestSchema = z.object({
  expected_version: z.number().int().positive(),
});
export const readAllSchema = z.object({
  updated_count: z.number().int().nonnegative(),
});

export const scheduledJobSchema = z.object({
  job_key: text,
  job_type: text,
  display_name: text,
  enabled: z.boolean(),
  interval_seconds: z.number().int().positive(),
  timezone: text,
  next_run_at: text,
  last_successful_run_at: nullableText,
  concurrency_policy: text,
  run_as_user_id: uuid.nullable(),
  max_attempts: z.number().int().positive(),
  retry_backoff_seconds: z.number().int().positive(),
  lease_seconds: z.number().int().positive(),
  created_at: text,
  updated_at: text,
  version: z.number().int().positive(),
});
export const jobEnabledRequestSchema = z.object({
  enabled: z.boolean(),
  expected_version: z.number().int().positive(),
});
export const jobExecutionStatusSchema = z.enum([
  "pending",
  "running",
  "succeeded",
  "failed",
  "retry_scheduled",
  "dead_lettered",
  "cancelled",
  "skipped",
]);
export const jobExecutionSchema = z.object({
  id: uuid,
  job_key: text,
  scheduled_for: text,
  trigger_type: z.enum(["scheduled", "manual"]),
  requested_by_user_id: uuid.nullable(),
  status: jobExecutionStatusSchema,
  attempt_number: z.number().int().nonnegative(),
  worker_identity: nullableText,
  available_after: text,
  lease_expires_at: nullableText,
  started_at: nullableText,
  completed_at: nullableText,
  execution_summary: z.record(z.string(), z.unknown()).nullable(),
  safe_error_code: nullableText,
  safe_error_summary: nullableText,
  correlation_id: text,
  created_at: text,
  updated_at: text,
  version: z.number().int().positive(),
});
export const jobExecutionPageSchema = z.object({
  items: z.array(jobExecutionSchema),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
});
export const manualTriggerResponseSchema = z.object({
  execution: jobExecutionSchema,
  created: z.boolean(),
});
export const outboxEventSchema = z.object({
  id: uuid,
  event_type: text,
  aggregate_type: text,
  aggregate_id: text,
  scope_id: nullableText,
  created_at: text,
  available_after: text,
  status: z.enum([
    "pending",
    "processing",
    "processed",
    "retry_scheduled",
    "dead_lettered",
  ]),
  attempt_count: z.number().int().nonnegative(),
  lease_owner: nullableText,
  lease_expires_at: nullableText,
  processed_at: nullableText,
  last_safe_error_code: nullableText,
  last_safe_error_summary: nullableText,
  updated_at: text,
  version: z.number().int().positive(),
});
export const outboxEventPageSchema = z.object({
  items: z.array(outboxEventSchema),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
});
export const operationalMetricsSchema = z.object({
  as_of: text,
  pending_job_count: z.number().int().nonnegative(),
  failed_job_count: z.number().int().nonnegative(),
  dead_letter_job_count: z.number().int().nonnegative(),
  pending_outbox_count: z.number().int().nonnegative(),
  dead_letter_outbox_count: z.number().int().nonnegative(),
  oldest_pending_outbox_age_seconds: z.number().int().nonnegative().nullable(),
  last_successful_run_by_job: z.record(z.string(), z.string().nullable()),
});
export const workerHealthSchema = z.object({
  status: z.enum(["ready", "starting", "stopping", "error", "stale", "missing"]),
  ready: z.boolean(),
  worker_identity: nullableText,
  last_seen_at: nullableText,
  age_seconds: z.number().int().nonnegative().nullable(),
});

export type NotificationRecord = z.infer<typeof notificationSchema>;
export type NotificationSeverity = z.infer<typeof notificationSeveritySchema>;
export type ScheduledJob = z.infer<typeof scheduledJobSchema>;
export type JobExecution = z.infer<typeof jobExecutionSchema>;
