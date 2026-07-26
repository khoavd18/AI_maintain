"use client";

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { operationsApi } from "@/lib/api/operations-endpoints";
import { queryKeys, type QueryFilters } from "@/lib/api/query-keys";

export function useNotificationsQuery(
  filters: QueryFilters = {},
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.notifications(filters),
    queryFn: ({ signal }) => operationsApi.notifications(filters, signal),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });
}

export function useUnreadNotificationCountQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.notificationUnreadCount,
    queryFn: ({ signal }) => operationsApi.unreadCount(signal),
    enabled,
    refetchInterval: 30_000,
    staleTime: 10_000,
  });
}

export function useNotificationActionMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      notificationId,
      action,
      expectedVersion,
    }: {
      notificationId: string;
      action: "read" | "unread" | "dismiss";
      expectedVersion: number;
    }) =>
      operationsApi.notificationAction(
        notificationId,
        action,
        expectedVersion,
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.notificationRoot,
      });
    },
  });
}

export function useReadAllNotificationsMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => operationsApi.readAll(),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.notificationRoot,
      });
    },
  });
}

export function useJobsQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.operationsJobs,
    queryFn: ({ signal }) => operationsApi.jobs(signal),
    enabled,
    staleTime: 10_000,
  });
}

export function useJobExecutionsQuery(
  filters: QueryFilters = {},
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.operationsExecutions(filters),
    queryFn: ({ signal }) => operationsApi.executions(filters, signal),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  });
}

export function useOutboxQuery(
  filters: QueryFilters = {},
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.operationsOutbox(filters),
    queryFn: ({ signal }) => operationsApi.outbox(filters, signal),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  });
}

export function useOperationalMetricsQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.operationsMetrics,
    queryFn: ({ signal }) => operationsApi.metrics(signal),
    enabled,
    refetchInterval: 30_000,
  });
}

export function useWorkerHealthQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.workerHealth,
    queryFn: ({ signal }) => operationsApi.workerHealth(signal),
    enabled,
    refetchInterval: 30_000,
    retry: false,
  });
}

export function useJobStateMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      jobKey,
      enabled,
      expectedVersion,
    }: {
      jobKey: string;
      enabled: boolean;
      expectedVersion: number;
    }) =>
      operationsApi.updateJob(jobKey, {
        enabled,
        expected_version: expectedVersion,
      }),
    onSuccess: async () => invalidateOperations(queryClient),
  });
}

export function useTriggerJobMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      jobKey,
      idempotencyKey,
    }: {
      jobKey: string;
      idempotencyKey: string;
    }) => operationsApi.triggerJob(jobKey, idempotencyKey),
    onSuccess: async () => invalidateOperations(queryClient),
  });
}

export function useRetryExecutionMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      executionId,
      idempotencyKey,
    }: {
      executionId: string;
      idempotencyKey: string;
    }) => operationsApi.retryExecution(executionId, idempotencyKey),
    onSuccess: async () => invalidateOperations(queryClient),
  });
}

async function invalidateOperations(
  queryClient: ReturnType<typeof useQueryClient>,
) {
  await queryClient.invalidateQueries({
    queryKey: queryKeys.operationsRoot,
  });
}
