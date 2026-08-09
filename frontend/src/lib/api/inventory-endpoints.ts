import { z } from "zod";

import {
  deleteJson,
  getBinary,
  getJson,
  postForm,
  postJson,
} from "@/lib/api/client";
import {
  adjustmentRequestSchema,
  consumptionRequestSchema,
  consumptionSchema,
  inventoryAttachmentSchema,
  inventoryBalancePageSchema,
  inventoryMetricsSchema,
  inventoryMovementPageSchema,
  inventoryMovementSchema,
  inventoryOptionsSchema,
  issueCreateRequestSchema,
  issueSchema,
  lifecycleRequestSchema,
  locationCreateRequestSchema,
  partCategorySchema,
  partCreateRequestSchema,
  requirementCreateRequestSchema,
  requirementSchema,
  reservationActionRequestSchema,
  reservationCreateRequestSchema,
  reservationReplaceRequestSchema,
  reservationPageSchema,
  reservationSchema,
  returnRequestSchema,
  returnSchema,
  sparePartPageSchema,
  sparePartSchema,
  stockLocationSchema,
  stockOperationRequestSchema,
  transferRequestSchema,
  transferResponseSchema,
  unitOfMeasureSchema,
  workOrderPartsSummarySchema,
  type AdjustmentRequest,
  type ConsumptionRequest,
  type IssueCreateRequest,
  type LocationCreateRequest,
  type PartCreateRequest,
  type RequirementCreateRequest,
  type ReservationActionRequest,
  type ReservationCreateRequest,
  type ReservationReplaceRequest,
  type ReturnRequest,
  type StockOperationRequest,
  type TransferRequest,
} from "@/lib/api/inventory-schemas";
import { withQuery, type QueryFilters } from "@/lib/api/query-keys";

const lifecycleResponseSchema = sparePartSchema;

export const inventoryApi = {
  options: (signal?: AbortSignal) =>
    getJson("/inventory/options", inventoryOptionsSchema, { signal }),
  categories: (signal?: AbortSignal) =>
    getJson("/part-categories", z.array(partCategorySchema), { signal }),
  units: (signal?: AbortSignal) =>
    getJson("/units-of-measure", z.array(unitOfMeasureSchema), { signal }),
  locations: (includeArchived = false, signal?: AbortSignal) =>
    getJson(
      withQuery("/stock-locations", { include_archived: includeArchived }),
      z.array(stockLocationSchema),
      { signal },
    ),
  parts: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(withQuery("/parts", filters), sparePartPageSchema, { signal }),
  part: (partId: string, signal?: AbortSignal) =>
    getJson(`/parts/${encodeURIComponent(partId)}`, sparePartSchema, { signal }),
  balances: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(withQuery("/inventory/balances", filters), inventoryBalancePageSchema, {
      signal,
    }),
  lowStock: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(withQuery("/inventory/low-stock", filters), inventoryBalancePageSchema, {
      signal,
    }),
  movements: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(withQuery("/inventory/movements", filters), inventoryMovementPageSchema, {
      signal,
    }),
  metrics: (signal?: AbortSignal) =>
    getJson("/inventory/metrics", inventoryMetricsSchema, { signal }),
  reservations: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(withQuery("/inventory/reservations", filters), reservationPageSchema, {
      signal,
    }),
  workOrderParts: (workOrderId: string, signal?: AbortSignal) =>
    getJson(
      `/work-orders/${encodeURIComponent(workOrderId)}/parts`,
      workOrderPartsSummarySchema,
      { signal },
    ),
  createPart: (request: PartCreateRequest, signal?: AbortSignal) =>
    postJson("/parts", request, partCreateRequestSchema, sparePartSchema, { signal }),
  createLocation: (request: LocationCreateRequest, signal?: AbortSignal) =>
    postJson(
      "/stock-locations",
      request,
      locationCreateRequestSchema,
      stockLocationSchema,
      { signal },
    ),
  stockLocationLifecycle: (
    locationId: string,
    action: "activate" | "deactivate" | "archive" | "restore",
    request: z.infer<typeof lifecycleRequestSchema>,
    signal?: AbortSignal,
  ) =>
    postJson(
      `/stock-locations/${encodeURIComponent(locationId)}/${action}`,
      request,
      lifecycleRequestSchema,
      stockLocationSchema,
      { signal },
    ),
  partLifecycle: (
    partId: string,
    action: "activate" | "deactivate" | "archive" | "restore",
    request: z.infer<typeof lifecycleRequestSchema>,
    signal?: AbortSignal,
  ) =>
    postJson(
      `/parts/${encodeURIComponent(partId)}/${action}`,
      request,
      lifecycleRequestSchema,
      lifecycleResponseSchema,
      { signal },
    ),
  openingBalance: (
    request: StockOperationRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ) =>
    postJson(
      "/inventory/opening-balances",
      request,
      stockOperationRequestSchema,
      inventoryMovementSchema,
      { signal, idempotencyKey },
    ),
  receive: (
    request: StockOperationRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ) =>
    postJson(
      "/inventory/receipts",
      request,
      stockOperationRequestSchema,
      inventoryMovementSchema,
      { signal, idempotencyKey },
    ),
  transfer: (
    request: TransferRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ) =>
    postJson(
      "/inventory/transfers",
      request,
      transferRequestSchema,
      transferResponseSchema,
      { signal, idempotencyKey },
    ),
  adjust: (
    request: AdjustmentRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ) =>
    postJson(
      "/inventory/adjustments",
      request,
      adjustmentRequestSchema,
      inventoryMovementSchema,
      { signal, idempotencyKey },
    ),
  createRequirement: (
    workOrderId: string,
    request: RequirementCreateRequest,
    signal?: AbortSignal,
  ) =>
    postJson(
      `/work-orders/${encodeURIComponent(workOrderId)}/part-requirements`,
      request,
      requirementCreateRequestSchema,
      requirementSchema,
      { signal },
    ),
  reserve: (
    requirementId: string,
    request: ReservationCreateRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ) =>
    postJson(
      `/work-order-part-requirements/${encodeURIComponent(requirementId)}/reservations`,
      request,
      reservationCreateRequestSchema,
      reservationSchema,
      { signal, idempotencyKey },
    ),
  reservationAction: (
    reservationId: string,
    action: "release" | "expire",
    request: ReservationActionRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ) =>
    postJson(
      `/stock-reservations/${encodeURIComponent(reservationId)}/${action}`,
      request,
      reservationActionRequestSchema,
      reservationSchema,
      { signal, idempotencyKey },
    ),
  replaceReservation: (
    reservationId: string,
    request: ReservationReplaceRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ) =>
    postJson(
      `/stock-reservations/${encodeURIComponent(reservationId)}/replace`,
      request,
      reservationReplaceRequestSchema,
      reservationSchema,
      { signal, idempotencyKey },
    ),
  issue: (
    workOrderId: string,
    request: IssueCreateRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ) =>
    postJson(
      `/work-orders/${encodeURIComponent(workOrderId)}/part-issues`,
      request,
      issueCreateRequestSchema,
      issueSchema,
      { signal, idempotencyKey },
    ),
  consume: (
    issueId: string,
    request: ConsumptionRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ) =>
    postJson(
      `/part-issues/${encodeURIComponent(issueId)}/consumptions`,
      request,
      consumptionRequestSchema,
      consumptionSchema,
      { signal, idempotencyKey },
    ),
  returnPart: (
    issueId: string,
    request: ReturnRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ) =>
    postJson(
      `/part-issues/${encodeURIComponent(issueId)}/returns`,
      request,
      returnRequestSchema,
      returnSchema,
      { signal, idempotencyKey },
    ),
  evidence: (movementId: string, signal?: AbortSignal) =>
    getJson(
      `/inventory/movements/${encodeURIComponent(movementId)}/attachments`,
      z.array(inventoryAttachmentSchema),
      { signal },
    ),
  uploadEvidence: (
    movementId: string,
    category: string,
    file: File,
    signal?: AbortSignal,
  ) => {
    const body = new FormData();
    body.set("category", category);
    body.set("file", file);
    return postForm(
      `/inventory/movements/${encodeURIComponent(movementId)}/attachments`,
      body,
      inventoryAttachmentSchema,
      { signal },
    );
  },
  downloadEvidence: (
    movementId: string,
    attachmentId: string,
    signal?: AbortSignal,
  ) =>
    getBinary(
      `/inventory/movements/${encodeURIComponent(movementId)}/attachments/${encodeURIComponent(attachmentId)}`,
      { signal },
    ),
  deleteEvidence: (
    movementId: string,
    attachmentId: string,
    signal?: AbortSignal,
  ) =>
    deleteJson(
      `/inventory/movements/${encodeURIComponent(movementId)}/attachments/${encodeURIComponent(attachmentId)}`,
      inventoryAttachmentSchema,
      { signal },
    ),
};
