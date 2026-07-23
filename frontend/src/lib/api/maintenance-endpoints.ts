import { z } from "zod";

import { deleteJson, getBinary, getJson, patchJson, postForm, postJson } from "@/lib/api/client";
import { withQuery, type QueryFilters } from "@/lib/api/query-keys";
import {
  checklistTemplateCreateRequestSchema,
  checklistTemplatePageSchema,
  checklistTemplateSchema,
  generationRequestSchema,
  generationResponseSchema,
  maintenanceOptionsSchema,
  maintenancePlanCreateRequestSchema,
  maintenancePlanPageSchema,
  maintenancePlanSchema,
  maintenancePlanUpdateRequestSchema,
  occurrencePreviewSchema,
  scheduleViewSchema,
  workOrderAttachmentSchema,
  workOrderAttachmentsSchema,
  workOrderChecklistUpdateRequestSchema,
  workOrderCompleteRequestSchema,
  workOrderCreateRequestSchema,
  workOrderMetricsSchema,
  workOrderPageSchema,
  workOrderSchema,
  workOrderUpdateRequestSchema,
  type ChecklistTemplateCreateRequest,
  type GenerationRequest,
  type MaintenancePlanCreateRequest,
  type MaintenancePlanUpdateRequest,
  type WorkOrderChecklistUpdateRequest,
  type WorkOrderCompleteRequest,
  type WorkOrderCreateRequest,
  type WorkOrderUpdateRequest,
} from "@/lib/api/maintenance-schemas";

const versionRequestSchema = z.object({ expected_version: z.number().int().positive() });
const planResumeRequestSchema = versionRequestSchema.extend({ resume_date: z.string().min(1) });
const planArchiveRequestSchema = versionRequestSchema.extend({ archive_reason: z.string().trim().min(3).max(1000) });
const assignRequestSchema = versionRequestSchema.extend({ assigned_to_user_id: z.string().uuid() });
const transitionRequestSchema = versionRequestSchema.extend({
  target_status: z.enum(["assigned", "in_progress", "on_hold"]),
  hold_reason: z.string().trim().max(1000).nullable(),
});
const cancelRequestSchema = versionRequestSchema.extend({ cancellation_reason: z.string().trim().min(3).max(1000) });
const reopenRequestSchema = versionRequestSchema.extend({ reason: z.string().trim().min(3).max(1000) });
const correctiveRequestSchema = workOrderCreateRequestSchema
  .omit({ work_order_type: true, asset_id: true, preventive_plan_id: true, source_ticket_id: true })
  .partial({ title: true, description: true, priority: true });
const templateVersionRequestSchema = checklistTemplateCreateRequestSchema
  .omit({ code: true })
  .partial();

export const maintenanceApi = {
  options: (signal?: AbortSignal) => getJson("/maintenance/options", maintenanceOptionsSchema, { signal }),
  plans: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(withQuery("/maintenance-plans", filters), maintenancePlanPageSchema, { signal }),
  plan: (planId: string, signal?: AbortSignal) =>
    getJson(`/maintenance-plans/${encodeURIComponent(planId)}`, maintenancePlanSchema, { signal }),
  createPlan: (request: MaintenancePlanCreateRequest, signal?: AbortSignal) =>
    postJson("/maintenance-plans", request, maintenancePlanCreateRequestSchema, maintenancePlanSchema, { signal }),
  updatePlan: (planId: string, request: MaintenancePlanUpdateRequest, signal?: AbortSignal) =>
    patchJson(`/maintenance-plans/${encodeURIComponent(planId)}`, request, maintenancePlanUpdateRequestSchema, maintenancePlanSchema, { signal }),
  pausePlan: (planId: string, request: z.infer<typeof versionRequestSchema>, signal?: AbortSignal) =>
    postJson(`/maintenance-plans/${encodeURIComponent(planId)}/pause`, request, versionRequestSchema, maintenancePlanSchema, { signal }),
  resumePlan: (planId: string, request: z.infer<typeof planResumeRequestSchema>, signal?: AbortSignal) =>
    postJson(`/maintenance-plans/${encodeURIComponent(planId)}/resume`, request, planResumeRequestSchema, maintenancePlanSchema, { signal }),
  archivePlan: (planId: string, request: z.infer<typeof planArchiveRequestSchema>, signal?: AbortSignal) =>
    postJson(`/maintenance-plans/${encodeURIComponent(planId)}/archive`, request, planArchiveRequestSchema, maintenancePlanSchema, { signal }),
  occurrences: (planId: string, filters: QueryFilters, signal?: AbortSignal) =>
    getJson(withQuery(`/maintenance-plans/${encodeURIComponent(planId)}/occurrences`, filters), occurrencePreviewSchema, { signal }),
  generate: (request: GenerationRequest, dryRun: boolean, signal?: AbortSignal) =>
    postJson(`/maintenance-plans/generate${dryRun ? "/dry-run" : ""}`, request, generationRequestSchema, generationResponseSchema, { signal }),
  templates: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(withQuery("/checklist-templates", filters), checklistTemplatePageSchema, { signal }),
  template: (templateId: string, signal?: AbortSignal) =>
    getJson(`/checklist-templates/${encodeURIComponent(templateId)}`, checklistTemplateSchema, { signal }),
  createTemplate: (request: ChecklistTemplateCreateRequest, signal?: AbortSignal) =>
    postJson("/checklist-templates", request, checklistTemplateCreateRequestSchema, checklistTemplateSchema, { signal }),
  versionTemplate: (templateId: string, request: z.infer<typeof templateVersionRequestSchema>, signal?: AbortSignal) =>
    postJson(`/checklist-templates/${encodeURIComponent(templateId)}/versions`, request, templateVersionRequestSchema, checklistTemplateSchema, { signal }),
  archiveTemplate: (templateId: string, request: z.infer<typeof versionRequestSchema>, signal?: AbortSignal) =>
    postJson(`/checklist-templates/${encodeURIComponent(templateId)}/archive`, request, versionRequestSchema, checklistTemplateSchema, { signal }),
  workOrders: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(withQuery("/work-orders", filters), workOrderPageSchema, { signal }),
  workOrder: (workOrderId: string, signal?: AbortSignal) =>
    getJson(`/work-orders/${encodeURIComponent(workOrderId)}`, workOrderSchema, { signal }),
  createWorkOrder: (request: WorkOrderCreateRequest, signal?: AbortSignal) =>
    postJson("/work-orders", request, workOrderCreateRequestSchema, workOrderSchema, { signal }),
  updateWorkOrder: (workOrderId: string, request: WorkOrderUpdateRequest, signal?: AbortSignal) =>
    patchJson(`/work-orders/${encodeURIComponent(workOrderId)}`, request, workOrderUpdateRequestSchema, workOrderSchema, { signal }),
  assignWorkOrder: (workOrderId: string, request: z.infer<typeof assignRequestSchema>, signal?: AbortSignal) =>
    postJson(`/work-orders/${encodeURIComponent(workOrderId)}/assign`, request, assignRequestSchema, workOrderSchema, { signal }),
  transitionWorkOrder: (workOrderId: string, request: z.infer<typeof transitionRequestSchema>, signal?: AbortSignal) =>
    postJson(`/work-orders/${encodeURIComponent(workOrderId)}/transition`, request, transitionRequestSchema, workOrderSchema, { signal }),
  updateChecklist: (workOrderId: string, request: WorkOrderChecklistUpdateRequest, signal?: AbortSignal) =>
    postJson(`/work-orders/${encodeURIComponent(workOrderId)}/checklist`, request, workOrderChecklistUpdateRequestSchema, workOrderSchema, { signal }),
  completeWorkOrder: (workOrderId: string, request: WorkOrderCompleteRequest, signal?: AbortSignal) =>
    postJson(`/work-orders/${encodeURIComponent(workOrderId)}/complete`, request, workOrderCompleteRequestSchema, workOrderSchema, { signal }),
  verifyWorkOrder: (workOrderId: string, request: z.infer<typeof versionRequestSchema>, signal?: AbortSignal) =>
    postJson(`/work-orders/${encodeURIComponent(workOrderId)}/verify`, request, versionRequestSchema, workOrderSchema, { signal }),
  cancelWorkOrder: (workOrderId: string, request: z.infer<typeof cancelRequestSchema>, signal?: AbortSignal) =>
    postJson(`/work-orders/${encodeURIComponent(workOrderId)}/cancel`, request, cancelRequestSchema, workOrderSchema, { signal }),
  reopenWorkOrder: (workOrderId: string, request: z.infer<typeof reopenRequestSchema>, signal?: AbortSignal) =>
    postJson(`/work-orders/${encodeURIComponent(workOrderId)}/reopen`, request, reopenRequestSchema, workOrderSchema, { signal }),
  ticketWorkOrders: (ticketId: string, signal?: AbortSignal) =>
    getJson(`/tickets/${encodeURIComponent(ticketId)}/work-orders`, z.array(workOrderSchema), { signal }),
  createTicketWorkOrder: (ticketId: string, request: z.infer<typeof correctiveRequestSchema>, signal?: AbortSignal) =>
    postJson(`/tickets/${encodeURIComponent(ticketId)}/work-orders`, request, correctiveRequestSchema, workOrderSchema, { signal }),
  schedule: (filters: QueryFilters, signal?: AbortSignal) =>
    getJson(withQuery("/work-orders/calendar", filters), scheduleViewSchema, { signal }),
  metrics: (asOfDate: string, signal?: AbortSignal) =>
    getJson(withQuery("/work-orders/metrics", { as_of_date: asOfDate }), workOrderMetricsSchema, { signal }),
  attachments: (workOrderId: string, signal?: AbortSignal) =>
    getJson(`/work-orders/${encodeURIComponent(workOrderId)}/attachments`, workOrderAttachmentsSchema, { signal }),
  uploadAttachment: (workOrderId: string, category: string, file: File, signal?: AbortSignal) => {
    const body = new FormData();
    body.set("category", category);
    body.set("file", file);
    return postForm(`/work-orders/${encodeURIComponent(workOrderId)}/attachments`, body, workOrderAttachmentSchema, { signal });
  },
  downloadAttachment: (workOrderId: string, attachmentId: string, signal?: AbortSignal) =>
    getBinary(`/work-orders/${encodeURIComponent(workOrderId)}/attachments/${encodeURIComponent(attachmentId)}`, { signal }),
  deleteAttachment: (workOrderId: string, attachmentId: string, signal?: AbortSignal) =>
    deleteJson(`/work-orders/${encodeURIComponent(workOrderId)}/attachments/${encodeURIComponent(attachmentId)}`, workOrderAttachmentSchema, { signal }),
};

export type PlanResumeRequest = z.infer<typeof planResumeRequestSchema>;
export type PlanArchiveRequest = z.infer<typeof planArchiveRequestSchema>;
export type WorkOrderAssignRequest = z.infer<typeof assignRequestSchema>;
export type WorkOrderTransitionRequest = z.infer<typeof transitionRequestSchema>;
export type WorkOrderCancelRequest = z.infer<typeof cancelRequestSchema>;
export type WorkOrderReopenRequest = z.infer<typeof reopenRequestSchema>;
export type CorrectiveWorkOrderCreateRequest = z.infer<typeof correctiveRequestSchema>;
export type ChecklistTemplateVersionRequest = z.infer<typeof templateVersionRequestSchema>;
