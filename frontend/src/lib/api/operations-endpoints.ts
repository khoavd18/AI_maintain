import { z } from "zod";

import { getJson, patchJson, postJson } from "@/lib/api/client";
import {
  jobEnabledRequestSchema,
  jobExecutionPageSchema,
  manualTriggerResponseSchema,
  notificationPageSchema,
  notificationSchema,
  operationalMetricsSchema,
  outboxEventPageSchema,
  readAllSchema,
  scheduledJobSchema,
  unreadCountSchema,
  versionRequestSchema,
  workerHealthSchema,
} from "@/lib/api/operations-schemas";
import { withQuery, type QueryFilters } from "@/lib/api/query-keys";

const emptyRequestSchema = z.object({});

export const operationsApi = {
  notifications: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(withQuery("/notifications", filters), notificationPageSchema, { signal }),
  unreadCount: (signal?: AbortSignal) =>
    getJson("/notifications/unread-count", unreadCountSchema, { signal }),
  notificationAction: (
    notificationId: string,
    action: "read" | "unread" | "dismiss",
    expectedVersion: number,
    signal?: AbortSignal,
  ) =>
    postJson(
      `/notifications/${encodeURIComponent(notificationId)}/${action}`,
      { expected_version: expectedVersion },
      versionRequestSchema,
      notificationSchema,
      { signal },
    ),
  readAll: (signal?: AbortSignal) =>
    postJson("/notifications/read-all", {}, emptyRequestSchema, readAllSchema, {
      signal,
    }),
  jobs: (signal?: AbortSignal) =>
    getJson("/operations/jobs", z.array(scheduledJobSchema), { signal }),
  updateJob: (
    jobKey: string,
    request: z.infer<typeof jobEnabledRequestSchema>,
    signal?: AbortSignal,
  ) =>
    patchJson(
      `/operations/jobs/${encodeURIComponent(jobKey)}`,
      request,
      jobEnabledRequestSchema,
      scheduledJobSchema,
      { signal },
    ),
  triggerJob: (jobKey: string, idempotencyKey: string, signal?: AbortSignal) =>
    postJson(
      `/operations/jobs/${encodeURIComponent(jobKey)}/trigger`,
      {},
      emptyRequestSchema,
      manualTriggerResponseSchema,
      { signal, idempotencyKey },
    ),
  retryExecution: (
    executionId: string,
    idempotencyKey: string,
    signal?: AbortSignal,
  ) =>
    postJson(
      `/operations/executions/${encodeURIComponent(executionId)}/retry`,
      {},
      emptyRequestSchema,
      manualTriggerResponseSchema,
      { signal, idempotencyKey },
    ),
  executions: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(
      withQuery("/operations/executions", filters),
      jobExecutionPageSchema,
      { signal },
    ),
  outbox: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(withQuery("/operations/outbox", filters), outboxEventPageSchema, {
      signal,
    }),
  metrics: (signal?: AbortSignal) =>
    getJson("/operations/metrics", operationalMetricsSchema, { signal }),
  workerHealth: (signal?: AbortSignal) =>
    getJson("/health/worker", workerHealthSchema, { signal, skipAuth: true }),
};
