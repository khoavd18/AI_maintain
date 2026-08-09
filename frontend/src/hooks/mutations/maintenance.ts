"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { maintenanceApi, type ChecklistTemplateVersionRequest, type CorrectiveWorkOrderCreateRequest, type PlanArchiveRequest, type PlanResumeRequest, type WorkOrderAssignRequest, type WorkOrderCancelRequest, type WorkOrderReopenRequest, type WorkOrderTransitionRequest } from "@/lib/api/maintenance-endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import type { ChecklistTemplateCreateRequest, GenerationRequest, MaintenancePlanCreateRequest, MaintenancePlanUpdateRequest, WorkOrderChecklistUpdateRequest, WorkOrderCompleteRequest, WorkOrderCreateRequest, WorkOrderUpdateRequest } from "@/lib/api/maintenance-schemas";

import { invalidateMaintenancePlanning, invalidateWorkOrderQueries } from "./common";

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
