"use client";

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { inventoryApi } from "@/lib/api/inventory-endpoints";
import type {
  AdjustmentRequest,
  ConsumptionRequest,
  IssueCreateRequest,
  LocationCreateRequest,
  PartCreateRequest,
  RequirementCreateRequest,
  ReservationActionRequest,
  ReservationCreateRequest,
  ReservationReplaceRequest,
  ReturnRequest,
  StockOperationRequest,
  TransferRequest,
} from "@/lib/api/inventory-schemas";
import { queryKeys, type QueryFilters } from "@/lib/api/query-keys";

export function useInventoryOptionsQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.inventoryOptions,
    queryFn: ({ signal }) => inventoryApi.options(signal),
    enabled,
    staleTime: 5 * 60_000,
  });
}

export function useInventoryCategoriesQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.inventoryCategories,
    queryFn: ({ signal }) => inventoryApi.categories(signal),
    enabled,
    staleTime: 5 * 60_000,
  });
}

export function useInventoryUnitsQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.inventoryUnits,
    queryFn: ({ signal }) => inventoryApi.units(signal),
    enabled,
    staleTime: 5 * 60_000,
  });
}

export function useInventoryLocationsQuery(
  includeArchived = false,
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.inventoryLocations(includeArchived),
    queryFn: ({ signal }) =>
      inventoryApi.locations(includeArchived, signal),
    enabled,
    staleTime: 60_000,
  });
}

export function useInventoryPartsQuery(
  filters: QueryFilters = {},
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.inventoryParts(filters),
    queryFn: ({ signal }) => inventoryApi.parts(filters, signal),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useInventoryPartQuery(partId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.inventoryPart(partId),
    queryFn: ({ signal }) => inventoryApi.part(partId, signal),
    enabled: Boolean(partId) && enabled,
  });
}

export function useInventoryBalancesQuery(
  filters: QueryFilters = {},
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.inventoryBalances(filters),
    queryFn: ({ signal }) => inventoryApi.balances(filters, signal),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });
}

export function useLowStockQuery(
  filters: QueryFilters = {},
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.inventoryLowStock(filters),
    queryFn: ({ signal }) => inventoryApi.lowStock(filters, signal),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });
}

export function useInventoryMovementsQuery(
  filters: QueryFilters = {},
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.inventoryMovements(filters),
    queryFn: ({ signal }) => inventoryApi.movements(filters, signal),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });
}

export function useInventoryMetricsQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.inventoryMetrics,
    queryFn: ({ signal }) => inventoryApi.metrics(signal),
    enabled,
    staleTime: 15_000,
  });
}

export function useInventoryReservationsQuery(
  filters: QueryFilters = {},
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.inventoryReservations(filters),
    queryFn: ({ signal }) => inventoryApi.reservations(filters, signal),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });
}

export function useWorkOrderPartsQuery(
  workOrderId: string,
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.workOrderParts(workOrderId),
    queryFn: ({ signal }) =>
      inventoryApi.workOrderParts(workOrderId, signal),
    enabled: Boolean(workOrderId) && enabled,
    staleTime: 15_000,
  });
}

export function useCreatePartMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: PartCreateRequest) =>
      inventoryApi.createPart(request),
    onSuccess: async () => invalidateInventory(queryClient),
  });
}

export function useCreateLocationMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: LocationCreateRequest) =>
      inventoryApi.createLocation(request),
    onSuccess: async () => invalidateInventory(queryClient),
  });
}

export function useStockLocationLifecycleMutation(locationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      action,
      expectedVersion,
      reason,
    }: {
      action: "activate" | "deactivate" | "archive" | "restore";
      expectedVersion: number;
      reason: string | null;
    }) =>
      inventoryApi.stockLocationLifecycle(locationId, action, {
        expected_version: expectedVersion,
        reason,
      }),
    onSuccess: async () => invalidateInventory(queryClient),
  });
}

export function usePartLifecycleMutation(partId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      action,
      expectedVersion,
      reason,
    }: {
      action: "activate" | "deactivate" | "archive" | "restore";
      expectedVersion: number;
      reason: string | null;
    }) =>
      inventoryApi.partLifecycle(partId, action, {
        expected_version: expectedVersion,
        reason,
      }),
    onSuccess: async (part) => {
      queryClient.setQueryData(queryKeys.inventoryPart(partId), part);
      await invalidateInventory(queryClient);
    },
  });
}

export function useReceiveStockMutation(
  operation: "opening_balance" | "receipt" = "receipt",
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      request,
      idempotencyKey,
    }: {
      request: StockOperationRequest;
      idempotencyKey: string;
    }) =>
      operation === "opening_balance"
        ? inventoryApi.openingBalance(request, idempotencyKey)
        : inventoryApi.receive(request, idempotencyKey),
    onSuccess: async () => invalidateInventory(queryClient),
  });
}

export function useTransferStockMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      request,
      idempotencyKey,
    }: {
      request: TransferRequest;
      idempotencyKey: string;
    }) => inventoryApi.transfer(request, idempotencyKey),
    onSuccess: async () => invalidateInventory(queryClient),
  });
}

export function useAdjustStockMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      request,
      idempotencyKey,
    }: {
      request: AdjustmentRequest;
      idempotencyKey: string;
    }) => inventoryApi.adjust(request, idempotencyKey),
    onSuccess: async () => invalidateInventory(queryClient),
  });
}

export function useCreateRequirementMutation(workOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: RequirementCreateRequest) =>
      inventoryApi.createRequirement(workOrderId, request),
    onSuccess: async () => invalidateWorkOrderParts(queryClient, workOrderId),
  });
}

export function useReserveStockMutation(workOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      requirementId,
      request,
      idempotencyKey,
    }: {
      requirementId: string;
      request: ReservationCreateRequest;
      idempotencyKey: string;
    }) => inventoryApi.reserve(requirementId, request, idempotencyKey),
    onSuccess: async () => invalidateWorkOrderParts(queryClient, workOrderId),
  });
}

export function useReservationActionMutation(workOrderId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      reservationId,
      action,
      request,
      idempotencyKey,
    }: {
      reservationId: string;
      action: "release" | "expire";
      request: ReservationActionRequest;
      idempotencyKey: string;
    }) =>
      inventoryApi.reservationAction(
        reservationId,
        action,
        request,
        idempotencyKey,
      ),
    onSuccess: async () => {
      await invalidateInventory(queryClient);
      if (workOrderId) {
        await invalidateWorkOrderParts(queryClient, workOrderId);
      }
    },
  });
}

export function useReplaceReservationMutation(workOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      reservationId,
      request,
      idempotencyKey,
    }: {
      reservationId: string;
      request: ReservationReplaceRequest;
      idempotencyKey: string;
    }) =>
      inventoryApi.replaceReservation(
        reservationId,
        request,
        idempotencyKey,
      ),
    onSuccess: async () => invalidateWorkOrderParts(queryClient, workOrderId),
  });
}

export function useIssueStockMutation(workOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      request,
      idempotencyKey,
    }: {
      request: IssueCreateRequest;
      idempotencyKey: string;
    }) => inventoryApi.issue(workOrderId, request, idempotencyKey),
    onSuccess: async () => invalidateWorkOrderParts(queryClient, workOrderId),
  });
}

export function useConsumeStockMutation(workOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      issueId,
      request,
      idempotencyKey,
    }: {
      issueId: string;
      request: ConsumptionRequest;
      idempotencyKey: string;
    }) => inventoryApi.consume(issueId, request, idempotencyKey),
    onSuccess: async () => invalidateWorkOrderParts(queryClient, workOrderId),
  });
}

export function useReturnStockMutation(workOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      issueId,
      request,
      idempotencyKey,
    }: {
      issueId: string;
      request: ReturnRequest;
      idempotencyKey: string;
    }) => inventoryApi.returnPart(issueId, request, idempotencyKey),
    onSuccess: async () => invalidateWorkOrderParts(queryClient, workOrderId),
  });
}

export function useUploadInventoryEvidenceMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      movementId,
      category,
      file,
    }: {
      movementId: string;
      category: string;
      file: File;
    }) => inventoryApi.uploadEvidence(movementId, category, file),
    onSuccess: async (attachment) => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.inventoryEvidence(attachment.movement_id),
      });
    },
  });
}

async function invalidateInventory(queryClient: ReturnType<typeof useQueryClient>) {
  await queryClient.invalidateQueries({ queryKey: queryKeys.inventoryRoot });
}

async function invalidateWorkOrderParts(
  queryClient: ReturnType<typeof useQueryClient>,
  workOrderId: string,
) {
  await invalidateInventory(queryClient);
  await queryClient.invalidateQueries({
    queryKey: queryKeys.workOrderParts(workOrderId),
  });
}
