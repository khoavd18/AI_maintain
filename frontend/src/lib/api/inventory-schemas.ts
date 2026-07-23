import { z } from "zod";

const text = z.string().min(1);
const nullableText = z.string().nullable();
const uuid = z.string().uuid();
const quantity = z.coerce.number().nonnegative();
const positiveQuantity = z.coerce.number().positive();
const option = z.object({ code: text, display_name: text });

export const partLifecycleSchema = z.enum(["active", "inactive", "archived"]);
export const stockLocationStatusSchema = z.enum(["active", "inactive", "archived"]);
export const stockLocationTypeSchema = z.enum([
  "main_store",
  "engineering_store",
  "technician_van",
  "maintenance_room",
  "quarantine",
  "other",
]);
export const stockStateSchema = z.enum([
  "healthy",
  "low_stock",
  "at_reorder_point",
  "out_of_stock",
  "overstock",
]);
export const movementTypeSchema = z.enum([
  "opening_balance",
  "receipt",
  "issue",
  "return",
  "transfer_out",
  "transfer_in",
  "adjustment_increase",
  "adjustment_decrease",
  "damaged_scrapped",
]);
export const requirementStatusSchema = z.enum([
  "planned",
  "partially_reserved",
  "reserved",
  "partially_issued",
  "issued",
  "partially_consumed",
  "fulfilled",
  "cancelled",
]);
export const reservationStatusSchema = z.enum([
  "active",
  "partially_issued",
  "fulfilled",
  "released",
  "expired",
  "replaced",
]);

export const inventoryOptionsSchema = z.object({
  part_lifecycle_statuses: z.array(option),
  stock_location_statuses: z.array(option),
  stock_location_types: z.array(option),
  movement_types: z.array(option),
  requirement_statuses: z.array(option),
  reservation_statuses: z.array(option),
  stock_states: z.array(option),
  attachment_categories: z.array(option),
  compatible_asset_types: z.array(option),
});

export const partCategorySchema = z.object({
  id: uuid,
  code: text,
  name_vi: text,
  name_en: nullableText,
  description: nullableText,
  is_active: z.boolean(),
  version: z.number().int().positive(),
  created_at: text,
  updated_at: text,
});

export const unitOfMeasureSchema = z.object({
  id: uuid,
  code: text,
  name_vi: text,
  name_en: nullableText,
  symbol: text,
  quantity_precision: z.number().int().min(0).max(3),
  is_active: z.boolean(),
  version: z.number().int().positive(),
  created_at: text,
  updated_at: text,
});

export const sparePartSchema = z.object({
  id: uuid,
  part_number: text,
  name_vi: text,
  name_en: nullableText,
  category_id: uuid,
  category_code: text,
  category_name_vi: text,
  unit_of_measure_id: uuid,
  unit_code: text,
  unit_name_vi: text,
  unit_symbol: text,
  quantity_precision: z.number().int().min(0).max(3),
  manufacturer_reference: nullableText,
  compatible_asset_types: z.array(z.string()),
  lifecycle_status: partLifecycleSchema,
  lifecycle_status_display: text,
  minimum_stock: quantity,
  reorder_point: quantity,
  maximum_stock: quantity.nullable(),
  unit_cost: quantity.nullable(),
  currency_code: nullableText,
  total_on_hand_quantity: quantity,
  total_reserved_quantity: quantity,
  total_available_quantity: quantity,
  stock_state: stockStateSchema,
  stock_state_display: text,
  archived_at: nullableText,
  archive_reason: nullableText,
  version: z.number().int().positive(),
  created_at: text,
  updated_at: text,
});

export const sparePartPageSchema = z.object({
  items: z.array(sparePartSchema),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  total_pages: z.number().int().nonnegative(),
});

export const stockLocationSchema = z.object({
  id: uuid,
  code: text,
  name: text,
  location_type: stockLocationTypeSchema,
  location_type_display: text,
  description: nullableText,
  lifecycle_status: stockLocationStatusSchema,
  lifecycle_status_display: text,
  archived_at: nullableText,
  archive_reason: nullableText,
  version: z.number().int().positive(),
  created_at: text,
  updated_at: text,
});

export const inventoryBalanceSchema = z.object({
  id: uuid,
  part_id: uuid,
  part_number: text,
  part_name_vi: text,
  lifecycle_status: partLifecycleSchema,
  stock_location_id: uuid,
  stock_location_code: text,
  stock_location_name: text,
  stock_location_status: stockLocationStatusSchema,
  unit_of_measure_id: uuid,
  unit_code: text,
  unit_symbol: text,
  on_hand_quantity: quantity,
  reserved_quantity: quantity,
  available_quantity: quantity,
  minimum_stock: quantity,
  reorder_point: quantity,
  maximum_stock: quantity.nullable(),
  stock_state: stockStateSchema,
  stock_state_display: text,
  suggested_reorder_quantity: quantity,
  version: z.number().int().positive(),
  updated_at: text,
});

export const inventoryBalancePageSchema = z.object({
  items: z.array(inventoryBalanceSchema),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  total_pages: z.number().int().nonnegative(),
});

export const inventoryMovementSchema = z.object({
  id: uuid,
  movement_number: text,
  part_id: uuid,
  part_number: text,
  part_name_vi: text,
  stock_location_id: uuid,
  stock_location_code: text,
  stock_location_name: text,
  quantity: positiveQuantity,
  unit_of_measure_id: uuid,
  unit_code: text,
  unit_symbol: text,
  movement_type: movementTypeSchema,
  movement_type_display: text,
  business_reference: text,
  actor_user_id: uuid,
  actor_display_name: text,
  occurred_at: text,
  reason: text,
  work_order_id: uuid.nullable(),
  work_order_number: nullableText,
  source_location_id: uuid.nullable(),
  source_location_code: nullableText,
  destination_location_id: uuid.nullable(),
  destination_location_code: nullableText,
  transfer_group_id: uuid.nullable(),
  unit_cost_snapshot: quantity.nullable(),
  resulting_on_hand_quantity: quantity,
  resulting_reserved_quantity: quantity,
  resulting_available_quantity: quantity,
  idempotency_key: text,
  created_at: text,
});

export const inventoryMovementPageSchema = z.object({
  items: z.array(inventoryMovementSchema),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  total_pages: z.number().int().nonnegative(),
});

export const transferResponseSchema = z.object({
  transfer_group_id: uuid,
  transfer_out: inventoryMovementSchema,
  transfer_in: inventoryMovementSchema,
});

export const requirementSchema = z.object({
  id: uuid,
  work_order_id: uuid,
  work_order_number: text,
  part_id: uuid,
  part_number: text,
  part_name_vi: text,
  unit_code: text,
  unit_symbol: text,
  planned_quantity: positiveQuantity,
  required_by_date: nullableText,
  source_stock_location_id: uuid,
  source_stock_location_code: text,
  source_stock_location_name: text,
  status: requirementStatusSchema,
  status_display: text,
  notes: nullableText,
  reserved_quantity: quantity,
  issued_quantity: quantity,
  returned_quantity: quantity,
  consumed_quantity: quantity,
  outstanding_issued_quantity: quantity,
  shortage_quantity: quantity,
  version: z.number().int().positive(),
  created_at: text,
  updated_at: text,
});

export const reservationEventSchema = z.object({
  id: uuid,
  event_type: z.enum([
    "reserved",
    "released",
    "expired",
    "replaced",
    "issued",
    "fulfilled",
  ]),
  quantity: positiveQuantity,
  reason: text,
  actor_user_id: uuid,
  actor_display_name: text,
  occurred_at: text,
});

export const reservationSchema = z.object({
  id: uuid,
  reservation_number: text,
  requirement_id: uuid,
  work_order_id: uuid,
  work_order_number: text,
  part_id: uuid,
  part_number: text,
  part_name_vi: text,
  stock_location_id: uuid,
  stock_location_code: text,
  stock_location_name: text,
  occurrence_number: z.number().int().positive(),
  quantity: positiveQuantity,
  issued_quantity: quantity,
  remaining_quantity: quantity,
  status: reservationStatusSchema,
  status_display: text,
  expires_at: nullableText,
  replaced_by_reservation_id: uuid.nullable(),
  version: z.number().int().positive(),
  created_at: text,
  updated_at: text,
  events: z.array(reservationEventSchema),
});

export const reservationPageSchema = z.object({
  items: z.array(reservationSchema),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  total_pages: z.number().int().nonnegative(),
});

export const consumptionSchema = z.object({
  id: uuid,
  issue_id: uuid,
  work_order_id: uuid,
  part_id: uuid,
  quantity: positiveQuantity,
  consumed_by_user_id: uuid,
  consumed_by_display_name: text,
  consumed_at: text,
  note: nullableText,
});

export const returnSchema = z.object({
  id: uuid,
  return_number: text,
  issue_id: uuid,
  work_order_id: uuid,
  part_id: uuid,
  part_number: text,
  stock_location_id: uuid,
  stock_location_code: text,
  quantity: positiveQuantity,
  returned_by_user_id: uuid,
  returned_by_display_name: text,
  returned_at: text,
  reason: text,
  movement_id: uuid,
});

export const issueSchema = z.object({
  id: uuid,
  issue_number: text,
  work_order_id: uuid,
  work_order_number: text,
  requirement_id: uuid.nullable(),
  reservation_id: uuid.nullable(),
  part_id: uuid,
  part_number: text,
  part_name_vi: text,
  stock_location_id: uuid,
  stock_location_code: text,
  stock_location_name: text,
  unit_code: text,
  unit_symbol: text,
  quantity: positiveQuantity,
  reserved_quantity_used: quantity,
  consumed_quantity: quantity,
  returned_quantity: quantity,
  outstanding_quantity: quantity,
  issued_to_user_id: uuid.nullable(),
  issued_to_display_name: nullableText,
  issued_by_user_id: uuid,
  issued_by_display_name: text,
  issued_at: text,
  reason: text,
  movement_id: uuid,
  consumptions: z.array(consumptionSchema),
  returns: z.array(returnSchema),
});

export const workOrderPartsSummarySchema = z.object({
  work_order_id: uuid,
  work_order_number: text,
  work_order_status: text,
  work_order_status_display: text,
  assigned_to_user_id: uuid.nullable(),
  requirements: z.array(requirementSchema),
  reservations: z.array(reservationSchema),
  issues: z.array(issueSchema),
  movements: z.array(inventoryMovementSchema),
  total_planned_quantity: quantity,
  total_reserved_quantity: quantity,
  total_issued_quantity: quantity,
  total_returned_quantity: quantity,
  net_consumed_quantity: quantity,
  open_shortage_count: z.number().int().nonnegative(),
  has_unresolved_issued_stock: z.boolean(),
  completion_policy: text,
  completion_warning: nullableText,
});

export const inventoryMetricsSchema = z.object({
  total_active_parts: z.number().int().nonnegative(),
  total_on_hand_units: quantity,
  total_reserved_units: quantity,
  total_available_units: quantity,
  low_stock_parts: z.number().int().nonnegative(),
  out_of_stock_parts: z.number().int().nonnegative(),
  open_shortages: z.number().int().nonnegative(),
  work_orders_waiting_for_parts: z.number().int().nonnegative(),
  movements_by_type: z.record(z.string(), z.number().int().nonnegative()),
  data_notice: text,
});

export const inventoryAttachmentSchema = z.object({
  id: uuid,
  movement_id: uuid,
  category: z.enum([
    "adjustment_evidence",
    "damage_evidence",
    "receipt_evidence",
    "transfer_evidence",
    "other",
  ]),
  original_filename: text,
  media_type: text,
  size_bytes: z.number().int().nonnegative(),
  checksum: text,
  uploaded_by_user_id: uuid,
  created_at: text,
  deleted_at: nullableText,
});

export const partCreateRequestSchema = z
  .object({
    part_number: z.string().trim().min(2).max(80),
    name_vi: z.string().trim().min(2).max(200),
    name_en: z.string().trim().max(200).nullable(),
    category_id: uuid,
    unit_of_measure_id: uuid,
    manufacturer_reference: z.string().trim().max(200).nullable(),
    compatible_asset_types: z.array(z.enum(["hvac", "pump", "generator"])).max(3),
    minimum_stock: quantity,
    reorder_point: quantity,
    maximum_stock: quantity.nullable(),
    unit_cost: quantity.nullable(),
    currency_code: z.string().length(3).nullable(),
  })
  .superRefine((value, context) => {
    if (value.reorder_point < value.minimum_stock) {
      context.addIssue({
        code: "custom",
        path: ["reorder_point"],
        message: "Điểm đặt lại phải lớn hơn hoặc bằng tồn tối thiểu.",
      });
    }
    if (value.maximum_stock !== null && value.maximum_stock < value.reorder_point) {
      context.addIssue({
        code: "custom",
        path: ["maximum_stock"],
        message: "Tồn tối đa phải lớn hơn hoặc bằng điểm đặt lại.",
      });
    }
    if ((value.unit_cost === null) !== (value.currency_code === null)) {
      context.addIssue({
        code: "custom",
        path: ["unit_cost"],
        message: "Đơn giá và mã tiền tệ phải được nhập cùng nhau.",
      });
    }
  });

export const locationCreateRequestSchema = z.object({
  code: z.string().trim().min(2).max(50),
  name: z.string().trim().min(2).max(200),
  location_type: stockLocationTypeSchema,
  description: z.string().trim().max(1000).nullable(),
});

export const stockOperationRequestSchema = z.object({
  part_id: uuid,
  stock_location_id: uuid,
  quantity: positiveQuantity,
  business_reference: z.string().trim().min(2).max(160),
  occurred_at: z.string().nullable().optional(),
  reason: z.string().trim().min(3).max(1000),
  unit_cost_snapshot: quantity.nullable().optional(),
});

export const transferRequestSchema = z
  .object({
    part_id: uuid,
    source_stock_location_id: uuid,
    destination_stock_location_id: uuid,
    quantity: positiveQuantity,
    business_reference: z.string().trim().min(2).max(160),
    occurred_at: z.string().nullable().optional(),
    reason: z.string().trim().min(3).max(1000),
  })
  .refine(
    (value) => value.source_stock_location_id !== value.destination_stock_location_id,
    { path: ["destination_stock_location_id"], message: "Kho đích phải khác kho nguồn." },
  );

export const adjustmentRequestSchema = stockOperationRequestSchema.extend({
  adjustment_type: z.enum(["increase", "decrease", "damaged_scrapped"]),
  supporting_note: z.string().trim().min(3).max(2000),
});

export const requirementCreateRequestSchema = z.object({
  part_id: uuid,
  planned_quantity: positiveQuantity,
  required_by_date: z.string().nullable(),
  source_stock_location_id: uuid,
  notes: z.string().trim().max(1000).nullable(),
});

export const reservationCreateRequestSchema = z.object({
  quantity: positiveQuantity,
  expected_requirement_version: z.number().int().positive(),
  expires_at: z.string().nullable(),
  reason: z.string().trim().min(3).max(1000),
});

export const reservationActionRequestSchema = z.object({
  expected_version: z.number().int().positive(),
  reason: z.string().trim().min(3).max(1000),
});

export const reservationReplaceRequestSchema = z.object({
  quantity: positiveQuantity,
  stock_location_id: uuid,
  expected_version: z.number().int().positive(),
  expires_at: z.string().nullable(),
  reason: z.string().trim().min(3).max(1000),
});

export const issueCreateRequestSchema = z.object({
  part_id: uuid,
  stock_location_id: uuid,
  quantity: positiveQuantity,
  requirement_id: uuid.nullable(),
  reservation_id: uuid.nullable(),
  issued_to_user_id: uuid.nullable(),
  issued_at: z.string().nullable(),
  reason: z.string().trim().min(3).max(1000),
});

export const consumptionRequestSchema = z.object({
  quantity: positiveQuantity,
  consumed_at: z.string().nullable(),
  note: z.string().trim().max(1000).nullable(),
});

export const returnRequestSchema = z.object({
  stock_location_id: uuid,
  quantity: positiveQuantity,
  returned_at: z.string().nullable(),
  reason: z.string().trim().min(3).max(1000),
});

export const lifecycleRequestSchema = z.object({
  expected_version: z.number().int().positive(),
  reason: z.string().trim().min(3).max(1000).nullable(),
});

export type InventoryOptions = z.infer<typeof inventoryOptionsSchema>;
export type PartCategory = z.infer<typeof partCategorySchema>;
export type UnitOfMeasure = z.infer<typeof unitOfMeasureSchema>;
export type SparePart = z.infer<typeof sparePartSchema>;
export type InventoryBalance = z.infer<typeof inventoryBalanceSchema>;
export type InventoryMovement = z.infer<typeof inventoryMovementSchema>;
export type StockLocation = z.infer<typeof stockLocationSchema>;
export type Requirement = z.infer<typeof requirementSchema>;
export type Reservation = z.infer<typeof reservationSchema>;
export type PartIssue = z.infer<typeof issueSchema>;
export type WorkOrderPartsSummary = z.infer<typeof workOrderPartsSummarySchema>;
export type PartCreateRequest = z.infer<typeof partCreateRequestSchema>;
export type LocationCreateRequest = z.infer<typeof locationCreateRequestSchema>;
export type StockOperationRequest = z.infer<typeof stockOperationRequestSchema>;
export type TransferRequest = z.infer<typeof transferRequestSchema>;
export type AdjustmentRequest = z.infer<typeof adjustmentRequestSchema>;
export type RequirementCreateRequest = z.infer<typeof requirementCreateRequestSchema>;
export type ReservationCreateRequest = z.infer<typeof reservationCreateRequestSchema>;
export type ReservationActionRequest = z.infer<typeof reservationActionRequestSchema>;
export type ReservationReplaceRequest = z.infer<typeof reservationReplaceRequestSchema>;
export type IssueCreateRequest = z.infer<typeof issueCreateRequestSchema>;
export type ConsumptionRequest = z.infer<typeof consumptionRequestSchema>;
export type ReturnRequest = z.infer<typeof returnRequestSchema>;
