"use client";

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import {
  ticketingApi,
  type TicketActionCommand,
} from "@/lib/api/ticketing-endpoints";
import { queryKeys, type QueryFilters } from "@/lib/api/query-keys";
import type {
  BusinessCalendarRequest,
  BusinessCalendarUpdateRequest,
  EscalationEvaluationRequest,
  SlaPolicyRequest,
  SlaPolicyUpdateRequest,
  TicketCommentRequest,
  TicketImpact,
  TicketIntakeRequest,
  TicketQueue,
  TicketUrgency,
} from "@/lib/api/ticketing-schemas";

export function useTicketingOptionsQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.ticketingOptions,
    queryFn: ({ signal }) => ticketingApi.options(signal),
    enabled,
    staleTime: 5 * 60_000,
  });
}

export function useTicketPriorityPreviewQuery(
  impact: TicketImpact,
  urgency: TicketUrgency,
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.ticketPriorityPreview(impact, urgency),
    queryFn: ({ signal }) =>
      ticketingApi.priorityPreview(impact, urgency, signal),
    enabled,
    staleTime: 5 * 60_000,
  });
}

export function useTicketQueueQuery(
  queue: TicketQueue,
  filters: QueryFilters,
) {
  return useQuery({
    queryKey: queryKeys.ticketQueue(queue, filters),
    queryFn: ({ signal }) => ticketingApi.queue(queue, filters, signal),
    placeholderData: keepPreviousData,
  });
}

export function useTicketDetailQuery(ticketId: string) {
  return useQuery({
    queryKey: queryKeys.ticketDetail(ticketId),
    queryFn: ({ signal }) => ticketingApi.ticket(ticketId, signal),
    enabled: Boolean(ticketId),
  });
}

export function useBusinessCalendarsQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.businessCalendars,
    queryFn: ({ signal }) => ticketingApi.calendars(signal),
    enabled,
    staleTime: 60_000,
  });
}

export function useSlaPoliciesQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.slaPolicies,
    queryFn: ({ signal }) => ticketingApi.policies(signal),
    enabled,
    staleTime: 60_000,
  });
}

export function useSlaSummaryQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.slaSummary,
    queryFn: ({ signal }) => ticketingApi.slaSummary(signal),
    enabled,
  });
}

export function useTicketIntakeMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: TicketIntakeRequest) =>
      ticketingApi.intake(request),
    onSuccess: async (ticket) => {
      queryClient.setQueryData(queryKeys.ticketDetail(ticket.ticket_id), ticket);
      await invalidateTicketOperations(queryClient);
    },
  });
}

export function useTicketActionMutation(ticketId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (command: TicketActionCommand) =>
      ticketingApi.action(ticketId, command),
    onSuccess: async (ticket) => {
      queryClient.setQueryData(queryKeys.ticketDetail(ticketId), ticket);
      await invalidateTicketOperations(queryClient);
    },
  });
}

export function useTicketCommentMutation(ticketId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: TicketCommentRequest) =>
      ticketingApi.addComment(ticketId, request),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.ticketDetail(ticketId),
      });
    },
  });
}

export function useCreateBusinessCalendarMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: BusinessCalendarRequest) =>
      ticketingApi.createCalendar(request),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.businessCalendars,
      });
    },
  });
}

export function useUpdateBusinessCalendarMutation(calendarId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: BusinessCalendarUpdateRequest) =>
      ticketingApi.updateCalendar(calendarId, request),
    onSuccess: async () => {
      await invalidateSlaConfiguration(queryClient);
    },
  });
}

export function useCreateSlaPolicyMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: SlaPolicyRequest) =>
      ticketingApi.createPolicy(request),
    onSuccess: async () => {
      await invalidateSlaConfiguration(queryClient);
    },
  });
}

export function useUpdateSlaPolicyMutation(policyId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: SlaPolicyUpdateRequest) =>
      ticketingApi.updatePolicy(policyId, request),
    onSuccess: async () => {
      await invalidateSlaConfiguration(queryClient);
    },
  });
}

export function useEvaluateEscalationsMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: EscalationEvaluationRequest) =>
      ticketingApi.evaluateEscalations(request),
    onSuccess: async (result) => {
      if (!result.dry_run) {
        await invalidateTicketOperations(queryClient);
      }
      await queryClient.invalidateQueries({ queryKey: queryKeys.slaSummary });
    },
  });
}

async function invalidateTicketOperations(queryClient: QueryClient) {
  await queryClient.invalidateQueries({ queryKey: queryKeys.ticketLists });
  await queryClient.invalidateQueries({ queryKey: queryKeys.slaSummary });
}

async function invalidateSlaConfiguration(queryClient: QueryClient) {
  await queryClient.invalidateQueries({ queryKey: queryKeys.businessCalendars });
  await queryClient.invalidateQueries({ queryKey: queryKeys.slaPolicies });
}
