import { z } from "zod";

import { getJson, patchJson, postJson } from "@/lib/api/client";
import { withQuery, type QueryFilters } from "@/lib/api/query-keys";
import {
  businessCalendarRequestSchema,
  businessCalendarSchema,
  businessCalendarUpdateRequestSchema,
  escalationEvaluationRequestSchema,
  escalationEvaluationSchema,
  priorityPreviewSchema,
  slaPolicyRequestSchema,
  slaPolicySchema,
  slaPolicyUpdateRequestSchema,
  slaSummarySchema,
  ticketAssignRequestSchema,
  ticketCommentRequestSchema,
  ticketCommentSchema,
  ticketDetailSchema,
  ticketIntakeRequestSchema,
  ticketPriorityRequestSchema,
  ticketQueuePageSchema,
  ticketReasonActionSchema,
  ticketResolveRequestSchema,
  ticketSlaOverrideRequestSchema,
  ticketingOptionsSchema,
  versionedActionSchema,
  type BusinessCalendarRequest,
  type BusinessCalendarUpdateRequest,
  type EscalationEvaluationRequest,
  type SlaPolicyRequest,
  type SlaPolicyUpdateRequest,
  type TicketAssignRequest,
  type TicketCommentRequest,
  type TicketImpact,
  type TicketIntakeRequest,
  type TicketPriorityRequest,
  type TicketQueue,
  type TicketReasonAction,
  type TicketResolveRequest,
  type TicketSlaOverrideRequest,
  type TicketUrgency,
  type VersionedAction,
} from "@/lib/api/ticketing-schemas";

export type TicketActionCommand =
  | { action: "assign"; request: TicketAssignRequest }
  | { action: "acknowledge" | "start" | "resume" | "close"; request: VersionedAction }
  | { action: "hold" | "reopen" | "cancel"; request: TicketReasonAction }
  | { action: "resolve"; request: TicketResolveRequest }
  | { action: "priority"; request: TicketPriorityRequest }
  | { action: "sla-policy"; request: TicketSlaOverrideRequest };

export const ticketingApi = {
  options: (signal?: AbortSignal) =>
    getJson("/ticketing/options", ticketingOptionsSchema, { signal }),

  priorityPreview: (
    impact: TicketImpact,
    urgency: TicketUrgency,
    signal?: AbortSignal,
  ) =>
    getJson(
      withQuery("/ticketing/priority-preview", { impact, urgency }),
      priorityPreviewSchema,
      { signal },
    ),

  queue: (
    queue: TicketQueue,
    filters: QueryFilters = {},
    signal?: AbortSignal,
  ) =>
    getJson(
      withQuery(`/ticket-queues/${encodeURIComponent(queue)}`, filters),
      ticketQueuePageSchema,
      { signal },
    ),

  ticket: (ticketId: string, signal?: AbortSignal) =>
    getJson(
      `/tickets/${encodeURIComponent(ticketId)}`,
      ticketDetailSchema,
      { signal },
    ),

  intake: (request: TicketIntakeRequest, signal?: AbortSignal) =>
    postJson(
      "/tickets/intake",
      request,
      ticketIntakeRequestSchema,
      ticketDetailSchema,
      { signal },
    ),

  action: (
    ticketId: string,
    command: TicketActionCommand,
    signal?: AbortSignal,
  ) => {
    const path = `/tickets/${encodeURIComponent(ticketId)}/${command.action}`;
    switch (command.action) {
      case "assign":
        return postJson(path, command.request, ticketAssignRequestSchema, ticketDetailSchema, {
          signal,
        });
      case "hold":
      case "reopen":
      case "cancel":
        return postJson(path, command.request, ticketReasonActionSchema, ticketDetailSchema, {
          signal,
        });
      case "resolve":
        return postJson(path, command.request, ticketResolveRequestSchema, ticketDetailSchema, {
          signal,
        });
      case "priority":
        return postJson(path, command.request, ticketPriorityRequestSchema, ticketDetailSchema, {
          signal,
        });
      case "sla-policy":
        return postJson(
          path,
          command.request,
          ticketSlaOverrideRequestSchema,
          ticketDetailSchema,
          { signal },
        );
      default:
        return postJson(path, command.request, versionedActionSchema, ticketDetailSchema, {
          signal,
        });
    }
  },

  comments: (ticketId: string, signal?: AbortSignal) =>
    getJson(
      `/tickets/${encodeURIComponent(ticketId)}/comments`,
      z.array(ticketCommentSchema),
      { signal },
    ),

  addComment: (
    ticketId: string,
    request: TicketCommentRequest,
    signal?: AbortSignal,
  ) =>
    postJson(
      `/tickets/${encodeURIComponent(ticketId)}/comments`,
      request,
      ticketCommentRequestSchema,
      ticketCommentSchema,
      { signal },
    ),

  calendars: (signal?: AbortSignal) =>
    getJson(
      "/ticketing/business-calendars",
      z.array(businessCalendarSchema),
      { signal },
    ),

  createCalendar: (
    request: BusinessCalendarRequest,
    signal?: AbortSignal,
  ) =>
    postJson(
      "/ticketing/business-calendars",
      request,
      businessCalendarRequestSchema,
      businessCalendarSchema,
      { signal },
    ),

  updateCalendar: (
    calendarId: string,
    request: BusinessCalendarUpdateRequest,
    signal?: AbortSignal,
  ) =>
    patchJson(
      `/ticketing/business-calendars/${encodeURIComponent(calendarId)}`,
      request,
      businessCalendarUpdateRequestSchema,
      businessCalendarSchema,
      { signal },
    ),

  policies: (signal?: AbortSignal) =>
    getJson(
      "/ticketing/sla-policies",
      z.array(slaPolicySchema),
      { signal },
    ),

  createPolicy: (request: SlaPolicyRequest, signal?: AbortSignal) =>
    postJson(
      "/ticketing/sla-policies",
      request,
      slaPolicyRequestSchema,
      slaPolicySchema,
      { signal },
    ),

  updatePolicy: (
    policyId: string,
    request: SlaPolicyUpdateRequest,
    signal?: AbortSignal,
  ) =>
    patchJson(
      `/ticketing/sla-policies/${encodeURIComponent(policyId)}`,
      request,
      slaPolicyUpdateRequestSchema,
      slaPolicySchema,
      { signal },
    ),

  slaSummary: (signal?: AbortSignal) =>
    getJson("/ticketing/sla-summary", slaSummarySchema, { signal }),

  evaluateEscalations: (
    request: EscalationEvaluationRequest,
    signal?: AbortSignal,
  ) =>
    postJson(
      "/ticketing/escalations/evaluate",
      request,
      escalationEvaluationRequestSchema,
      escalationEvaluationSchema,
      { signal },
    ),
};
