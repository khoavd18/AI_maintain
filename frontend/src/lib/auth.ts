export const permissions = {
  assetsRead: "assets:read",
  assetsCreate: "assets:create",
  assetsUpdate: "assets:update",
  assetsChangeStatus: "assets:change_status",
  assetsArchive: "assets:archive",
  assetsRestore: "assets:restore",
  locationsRead: "locations:read",
  locationsCreate: "locations:create",
  locationsUpdate: "locations:update",
  locationsArchive: "locations:archive",
  attachmentsRead: "attachments:read",
  attachmentsCreate: "attachments:create",
  attachmentsDelete: "attachments:delete",
  ticketsRead: "tickets:read",
  ticketsCreate: "tickets:create",
  ticketsAssign: "tickets:assign",
  ticketsUpdate: "tickets:update",
  ticketsResolve: "tickets:resolve",
  ticketsAcknowledge: "tickets:acknowledge",
  ticketsExecute: "tickets:execute",
  ticketsClose: "tickets:close",
  ticketsReopen: "tickets:reopen",
  ticketsCancel: "tickets:cancel",
  ticketCommentsInternal: "ticket_comments:internal",
  ticketCommentsRequester: "ticket_comments:requester",
  ticketPiiRead: "ticket_pii:read",
  slaPoliciesRead: "sla_policies:read",
  slaPoliciesManage: "sla_policies:manage",
  escalationsEvaluate: "escalations:evaluate",
  escalationsExecute: "escalations:execute",
  maintenanceLogsRead: "maintenance_logs:read",
  maintenanceLogsCreate: "maintenance_logs:create",
  maintenancePlansRead: "maintenance_plans:read",
  maintenancePlansCreate: "maintenance_plans:create",
  maintenancePlansUpdate: "maintenance_plans:update",
  maintenancePlansPause: "maintenance_plans:pause",
  maintenancePlansArchive: "maintenance_plans:archive",
  checklistTemplatesRead: "checklist_templates:read",
  checklistTemplatesCreate: "checklist_templates:create",
  checklistTemplatesUpdate: "checklist_templates:update",
  workOrdersRead: "work_orders:read",
  workOrdersCreate: "work_orders:create",
  workOrdersAssign: "work_orders:assign",
  workOrdersUpdate: "work_orders:update",
  workOrdersExecute: "work_orders:execute",
  workOrdersComplete: "work_orders:complete",
  workOrdersVerify: "work_orders:verify",
  workOrdersCancel: "work_orders:cancel",
  workOrdersReopen: "work_orders:reopen",
  workOrderAttachmentsRead: "work_order_attachments:read",
  workOrderAttachmentsCreate: "work_order_attachments:create",
  workOrderAttachmentsDelete: "work_order_attachments:delete",
  maintenanceGenerationRun: "maintenance_generation:run",
  inventoryRead: "inventory:read",
  inventoryPartsManage: "inventory_parts:manage",
  inventoryLocationsManage: "inventory_locations:manage",
  inventoryReceive: "inventory:receive",
  inventoryReserve: "inventory:reserve",
  inventoryIssue: "inventory:issue",
  inventoryReturn: "inventory:return",
  inventoryTransfer: "inventory:transfer",
  inventoryAdjust: "inventory:adjust",
  inventoryRequirementsManage: "inventory_requirements:manage",
  inventoryConsume: "inventory:consume",
  workOrderPartsRead: "work_order_parts:read",
  inventoryAttachmentsRead: "inventory_attachments:read",
  inventoryAttachmentsCreate: "inventory_attachments:create",
  inventoryAttachmentsDelete: "inventory_attachments:delete",
  analyticsRead: "analytics:read",
  copilotUse: "copilot:use",
  usersRead: "users:read",
  usersCreate: "users:create",
  usersUpdate: "users:update",
  auditLogsRead: "audit_logs:read",
} as const;

export type Permission = (typeof permissions)[keyof typeof permissions];

export function hasPermission(
  currentPermissions: readonly string[],
  permission: Permission,
) {
  return currentPermissions.includes(permission);
}

export function safeReturnPath(value: string | null | undefined): string | null {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return null;
  try {
    const url = new URL(value, "http://local.invalid");
    if (url.origin !== "http://local.invalid") return null;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return null;
  }
}
