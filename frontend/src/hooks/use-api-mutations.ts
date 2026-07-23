"use client";

import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "@/lib/api/endpoints";
import {
  maintenanceApi,
  type ChecklistTemplateVersionRequest,
  type CorrectiveWorkOrderCreateRequest,
  type PlanArchiveRequest,
  type PlanResumeRequest,
  type WorkOrderAssignRequest,
  type WorkOrderCancelRequest,
  type WorkOrderReopenRequest,
  type WorkOrderTransitionRequest,
} from "@/lib/api/maintenance-endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import type {
  ChecklistTemplateCreateRequest,
  GenerationRequest,
  MaintenancePlanCreateRequest,
  MaintenancePlanUpdateRequest,
  WorkOrderChecklistUpdateRequest,
  WorkOrderCompleteRequest,
  WorkOrderCreateRequest,
  WorkOrderUpdateRequest,
} from "@/lib/api/maintenance-schemas";
import type {
  AssetArchiveRequest,
  AssetCreateRequest,
  AssetRestoreRequest,
  AssetUpdateRequest,
  CopilotAskRequest,
  LifecycleTransitionRequest,
  MaintenanceLogCreateRequest,
  OperationalStatusRequest,
  TicketCreateRequest,
  TicketUpdateRequest,
  UserCreateRequest,
  UserUpdateRequest,
} from "@/lib/api/schemas";

type QueryKey = readonly unknown[];

export function useAskCopilot() {
  return useMutation({
    mutationFn: (request: CopilotAskRequest) => api.askCopilot(request),
  });
}

export function useCreateAsset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: AssetCreateRequest) => api.createAsset(request),
    onSuccess: async (asset) => {
      await invalidateAssetQueries(queryClient, asset.asset_id);
      await queryClient.invalidateQueries({ queryKey: queryKeys.locations(false) });
    },
  });
}

export function useUpdateAsset(assetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: AssetUpdateRequest) => api.updateAsset(assetId, request),
    onSuccess: async () => invalidateAssetQueries(queryClient, assetId),
  });
}

export function useChangeAssetOperationalStatus(assetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: OperationalStatusRequest) =>
      api.changeAssetOperationalStatus(assetId, request),
    onSuccess: async () => invalidateAssetQueries(queryClient, assetId),
  });
}

export function useTransitionAssetLifecycle(assetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: LifecycleTransitionRequest) =>
      api.transitionAssetLifecycle(assetId, request),
    onSuccess: async () => invalidateAssetQueries(queryClient, assetId),
  });
}

export function useArchiveAsset(assetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: AssetArchiveRequest) => api.archiveAsset(assetId, request),
    onSuccess: async () => invalidateAssetQueries(queryClient, assetId),
  });
}

export function useRestoreAsset(assetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: AssetRestoreRequest) => api.restoreAsset(assetId, request),
    onSuccess: async () => invalidateAssetQueries(queryClient, assetId),
  });
}

export function useUploadAssetAttachment(assetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ category, file }: { category: string; file: File }) =>
      api.uploadAssetAttachment(assetId, category, file),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.assetAttachments(assetId) });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.assetHistory(assetId),
      });
    },
  });
}

export function useDeleteAssetAttachment(assetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (attachmentId: string) => api.deleteAssetAttachment(assetId, attachmentId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.assetAttachments(assetId) });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.assetHistory(assetId),
      });
    },
  });
}

export function useCreateTicket() {
  const queryClient = useQueryClient();
  const [refreshFailed, setRefreshFailed] = useState(false);
  const mutation = useMutation({
    mutationFn: (request: TicketCreateRequest) => api.createTicket(request),
    onMutate: () => setRefreshFailed(false),
    onSuccess: async (ticket) => {
      setRefreshFailed(
        !(await refreshAffectedQueries(queryClient, [
          queryKeys.ticketLists,
          queryKeys.assetLists,
          queryKeys.assetDetailsRoot(ticket.asset_id),
        ])),
      );
    },
  });
  return { ...mutation, refreshFailed };
}

export function useUpdateTicket(ticketId: string) {
  const queryClient = useQueryClient();
  const [refreshFailed, setRefreshFailed] = useState(false);
  const mutation = useMutation({
    mutationFn: (request: TicketUpdateRequest) => api.updateTicket(ticketId, request),
    onMutate: () => setRefreshFailed(false),
    onSuccess: async (ticket) => {
      setRefreshFailed(
        !(await refreshAffectedQueries(queryClient, [
          queryKeys.ticketLists,
          queryKeys.assetLists,
          queryKeys.assetDetailsRoot(ticket.asset_id),
        ])),
      );
    },
  });
  return { ...mutation, refreshFailed };
}

export function useCreateMaintenanceLog() {
  const queryClient = useQueryClient();
  const [refreshFailed, setRefreshFailed] = useState(false);
  const mutation = useMutation({
    mutationFn: (request: MaintenanceLogCreateRequest) => api.createMaintenanceLog(request),
    onMutate: () => setRefreshFailed(false),
    onSuccess: async (log) => {
      setRefreshFailed(
        !(await refreshAffectedQueries(queryClient, [
          queryKeys.maintenanceLogLists,
          queryKeys.assetLists,
          queryKeys.assetDetailsRoot(log.asset_id),
        ])),
      );
    },
  });
  return { ...mutation, refreshFailed };
}

export function useCreateMaintenancePlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: MaintenancePlanCreateRequest) => maintenanceApi.createPlan(request),
    onSuccess: async (plan) => invalidateMaintenancePlanning(queryClient, plan.id),
  });
}

export function useUpdateMaintenancePlan(planId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: MaintenancePlanUpdateRequest) =>
      maintenanceApi.updatePlan(planId, request),
    onSuccess: async () => invalidateMaintenancePlanning(queryClient, planId),
  });
}

export function usePauseMaintenancePlan(planId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (expectedVersion: number) =>
      maintenanceApi.pausePlan(planId, { expected_version: expectedVersion }),
    onSuccess: async () => invalidateMaintenancePlanning(queryClient, planId),
  });
}

export function useResumeMaintenancePlan(planId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: PlanResumeRequest) => maintenanceApi.resumePlan(planId, request),
    onSuccess: async () => invalidateMaintenancePlanning(queryClient, planId),
  });
}

export function useArchiveMaintenancePlan(planId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: PlanArchiveRequest) => maintenanceApi.archivePlan(planId, request),
    onSuccess: async () => invalidateMaintenancePlanning(queryClient, planId),
  });
}

export function useGenerateMaintenanceWorkOrders(dryRun: boolean) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: GenerationRequest) => maintenanceApi.generate(request, dryRun),
    onSuccess: async () => {
      if (!dryRun) await invalidateWorkOrderQueries(queryClient);
      await queryClient.invalidateQueries({ queryKey: queryKeys.maintenancePlanLists });
    },
  });
}

export function useCreateChecklistTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: ChecklistTemplateCreateRequest) =>
      maintenanceApi.createTemplate(request),
    onSuccess: async (template) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.checklistTemplateLists });
      queryClient.setQueryData(queryKeys.checklistTemplate(template.id), template);
    },
  });
}

export function useVersionChecklistTemplate(templateId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: ChecklistTemplateVersionRequest) =>
      maintenanceApi.versionTemplate(templateId, request),
    onSuccess: async (template) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.checklistTemplateLists });
      queryClient.setQueryData(queryKeys.checklistTemplate(template.id), template);
    },
  });
}

export function useArchiveChecklistTemplate(templateId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (expectedVersion: number) =>
      maintenanceApi.archiveTemplate(templateId, { expected_version: expectedVersion }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.checklistTemplateLists });
      await queryClient.invalidateQueries({ queryKey: queryKeys.checklistTemplate(templateId) });
    },
  });
}

export function useCreateWorkOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: WorkOrderCreateRequest) => maintenanceApi.createWorkOrder(request),
    onSuccess: async (workOrder) => invalidateWorkOrderQueries(queryClient, workOrder.id),
  });
}

export function useCreateCorrectiveWorkOrder(ticketId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: CorrectiveWorkOrderCreateRequest) =>
      maintenanceApi.createTicketWorkOrder(ticketId, request),
    onSuccess: async (workOrder) => {
      await invalidateWorkOrderQueries(queryClient, workOrder.id);
      await queryClient.invalidateQueries({ queryKey: queryKeys.ticketWorkOrders(ticketId) });
    },
  });
}

export function useUpdateWorkOrder(workOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: WorkOrderUpdateRequest) =>
      maintenanceApi.updateWorkOrder(workOrderId, request),
    onSuccess: async () => invalidateWorkOrderQueries(queryClient, workOrderId),
  });
}

export function useAssignWorkOrder(workOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: WorkOrderAssignRequest) =>
      maintenanceApi.assignWorkOrder(workOrderId, request),
    onSuccess: async () => invalidateWorkOrderQueries(queryClient, workOrderId),
  });
}

export function useTransitionWorkOrder(workOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: WorkOrderTransitionRequest) =>
      maintenanceApi.transitionWorkOrder(workOrderId, request),
    onSuccess: async () => invalidateWorkOrderQueries(queryClient, workOrderId),
  });
}

export function useUpdateWorkOrderChecklist(workOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: WorkOrderChecklistUpdateRequest) =>
      maintenanceApi.updateChecklist(workOrderId, request),
    onSuccess: async () => invalidateWorkOrderQueries(queryClient, workOrderId),
  });
}

export function useCompleteWorkOrder(workOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: WorkOrderCompleteRequest) =>
      maintenanceApi.completeWorkOrder(workOrderId, request),
    onSuccess: async (workOrder) => {
      await invalidateWorkOrderQueries(queryClient, workOrderId);
      await queryClient.invalidateQueries({ queryKey: queryKeys.maintenanceLogLists });
      await queryClient.invalidateQueries({ queryKey: queryKeys.assetDetailsRoot(workOrder.asset_id) });
    },
  });
}

export function useVerifyWorkOrder(workOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (expectedVersion: number) =>
      maintenanceApi.verifyWorkOrder(workOrderId, { expected_version: expectedVersion }),
    onSuccess: async (workOrder) => {
      await invalidateWorkOrderQueries(queryClient, workOrderId);
      await queryClient.invalidateQueries({ queryKey: queryKeys.assetDetailsRoot(workOrder.asset_id) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.assetLists });
    },
  });
}

export function useCancelWorkOrder(workOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: WorkOrderCancelRequest) =>
      maintenanceApi.cancelWorkOrder(workOrderId, request),
    onSuccess: async () => invalidateWorkOrderQueries(queryClient, workOrderId),
  });
}

export function useReopenWorkOrder(workOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: WorkOrderReopenRequest) =>
      maintenanceApi.reopenWorkOrder(workOrderId, request),
    onSuccess: async () => invalidateWorkOrderQueries(queryClient, workOrderId),
  });
}

export function useUploadWorkOrderAttachment(workOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ category, file }: { category: string; file: File }) =>
      maintenanceApi.uploadAttachment(workOrderId, category, file),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.workOrderAttachments(workOrderId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.workOrder(workOrderId) });
    },
  });
}

export function useDeleteWorkOrderAttachment(workOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (attachmentId: string) =>
      maintenanceApi.deleteAttachment(workOrderId, attachmentId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.workOrderAttachments(workOrderId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.workOrder(workOrderId) });
    },
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: UserCreateRequest) => api.createUser(request),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.users });
    },
  });
}

export function useUpdateUser(userId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: UserUpdateRequest) => api.updateUser(userId, request),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.users });
    },
  });
}

async function refreshAffectedQueries(queryClient: QueryClient, keys: QueryKey[]) {
  await Promise.all(
    keys.map((queryKey) => queryClient.invalidateQueries({ queryKey, refetchType: "none" })),
  );
  try {
    await Promise.all(
      keys.map((queryKey) =>
        queryClient.refetchQueries({ queryKey, type: "active" }, { throwOnError: true }),
      ),
    );
    return true;
  } catch {
    return false;
  }
}

async function invalidateAssetQueries(queryClient: QueryClient, assetId: string) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.assetCatalogs }),
    queryClient.invalidateQueries({ queryKey: queryKeys.assetLists }),
    queryClient.invalidateQueries({ queryKey: queryKeys.assetProfile(assetId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.assetDetailsRoot(assetId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.assetHistory(assetId) }),
  ]);
}

async function invalidateMaintenancePlanning(queryClient: QueryClient, planId?: string) {
  const operations = [
    queryClient.invalidateQueries({ queryKey: queryKeys.maintenancePlanLists }),
    queryClient.invalidateQueries({ queryKey: queryKeys.workOrderSchedule() }),
  ];
  if (planId) {
    operations.push(
      queryClient.invalidateQueries({ queryKey: queryKeys.maintenancePlan(planId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.maintenancePlanOccurrences(planId) }),
    );
  }
  await Promise.all(operations);
}

async function invalidateWorkOrderQueries(queryClient: QueryClient, workOrderId?: string) {
  const operations = [
    queryClient.invalidateQueries({ queryKey: queryKeys.workOrderLists }),
    queryClient.invalidateQueries({ queryKey: ["work-orders", "calendar"] }),
    queryClient.invalidateQueries({ queryKey: ["work-orders", "metrics"] }),
  ];
  if (workOrderId) {
    operations.push(queryClient.invalidateQueries({ queryKey: queryKeys.workOrder(workOrderId) }));
  }
  await Promise.all(operations);
}
