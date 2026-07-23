export type QueryFilterValue = string | number | boolean | null | undefined;
export type QueryFilters = Record<string, QueryFilterValue>;

export function serializeFilters(filters: QueryFilters = {}): string {
  const params = new URLSearchParams();
  Object.entries(filters)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .sort(([left], [right]) => left.localeCompare(right))
    .forEach(([key, value]) => params.set(key, String(value)));
  return params.toString();
}

export function withQuery(path: string, filters: QueryFilters = {}): string {
  const query = serializeFilters(filters);
  return query ? `${path}?${query}` : path;
}

export const queryKeys = {
  health: ["health"] as const,
  summary: ["summary"] as const,
  kpis: ["maintenance", "kpis"] as const,
  assetLists: ["assets", "list"] as const,
  assets: (filters: QueryFilters = {}) =>
    ["assets", "list", serializeFilters(filters)] as const,
  assetCatalogs: ["assets", "catalog"] as const,
  assetCatalog: (filters: QueryFilters = {}) =>
    ["assets", "catalog", serializeFilters(filters)] as const,
  assetOptions: ["assets", "options"] as const,
  locations: (includeArchived: boolean) =>
    ["locations", includeArchived ? "all" : "active"] as const,
  assetProfiles: ["assets", "profile"] as const,
  assetProfile: (assetId: string) => ["assets", "profile", assetId] as const,
  assetDetailsRoot: (assetId?: string) =>
    assetId ? (["assets", "details", assetId] as const) : (["assets", "details"] as const),
  assetDetails: (assetId: string, limit: number) =>
    ["assets", "details", assetId, limit] as const,
  assetAttachments: (assetId: string) => ["assets", assetId, "attachments"] as const,
  assetQr: (assetId: string) => ["assets", assetId, "qr"] as const,
  assetHistory: (assetId: string, filters: QueryFilters = {}) =>
    ["assets", assetId, "history", serializeFilters(filters)] as const,
  qrLookup: (lookupToken: string) => ["assets", "qr-lookup", lookupToken] as const,
  risks: (filters: QueryFilters = {}) => ["assets", "risk", serializeFilters(filters)] as const,
  ticketLists: ["tickets"] as const,
  tickets: (filters: QueryFilters = {}) => ["tickets", serializeFilters(filters)] as const,
  maintenanceLogLists: ["maintenance", "logs"] as const,
  maintenanceLogs: (filters: QueryFilters = {}) =>
    ["maintenance", "logs", serializeFilters(filters)] as const,
  maintenanceOptions: ["maintenance-planning", "options"] as const,
  maintenancePlanLists: ["maintenance-planning", "plans"] as const,
  maintenancePlans: (filters: QueryFilters = {}) =>
    ["maintenance-planning", "plans", serializeFilters(filters)] as const,
  maintenancePlan: (planId: string) =>
    ["maintenance-planning", "plans", planId] as const,
  maintenancePlanOccurrences: (planId: string, filters: QueryFilters = {}) =>
    ["maintenance-planning", "plans", planId, "occurrences", serializeFilters(filters)] as const,
  checklistTemplateLists: ["maintenance-planning", "checklists"] as const,
  checklistTemplates: (filters: QueryFilters = {}) =>
    ["maintenance-planning", "checklists", serializeFilters(filters)] as const,
  checklistTemplate: (templateId: string) =>
    ["maintenance-planning", "checklists", templateId] as const,
  workOrderLists: ["work-orders", "list"] as const,
  workOrders: (filters: QueryFilters = {}) =>
    ["work-orders", "list", serializeFilters(filters)] as const,
  workOrder: (workOrderId: string) => ["work-orders", workOrderId] as const,
  workOrderAttachments: (workOrderId: string) =>
    ["work-orders", workOrderId, "attachments"] as const,
  workOrderSchedule: (filters: QueryFilters = {}) =>
    ["work-orders", "calendar", serializeFilters(filters)] as const,
  workOrderMetrics: (asOfDate: string) =>
    ["work-orders", "metrics", asOfDate] as const,
  ticketWorkOrders: (ticketId: string) => ["ticket-work-orders", ticketId] as const,
  anomalies: (filters: QueryFilters = {}) =>
    ["assets", "anomalies", serializeFilters(filters)] as const,
  preventive: (filters: QueryFilters = {}) =>
    ["maintenance", "preventive", serializeFilters(filters)] as const,
  recurringIssues: (filters: QueryFilters = {}) =>
    ["maintenance", "recurring-issues", serializeFilters(filters)] as const,
  users: ["users"] as const,
  roleOptions: ["users", "roles"] as const,
  auditLogs: (filters: QueryFilters = {}) =>
    ["audit-logs", serializeFilters(filters)] as const,
};
