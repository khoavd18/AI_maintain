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
  assets: (filters: QueryFilters = {}) => ["assets", serializeFilters(filters)] as const,
  assetDetails: (assetId: string, limit: number) =>
    ["assets", "details", assetId, limit] as const,
  risks: (filters: QueryFilters = {}) => ["assets", "risk", serializeFilters(filters)] as const,
  tickets: (filters: QueryFilters = {}) => ["tickets", serializeFilters(filters)] as const,
  maintenanceLogs: (filters: QueryFilters = {}) =>
    ["maintenance", "logs", serializeFilters(filters)] as const,
  anomalies: (filters: QueryFilters = {}) =>
    ["assets", "anomalies", serializeFilters(filters)] as const,
  preventive: (filters: QueryFilters = {}) =>
    ["maintenance", "preventive", serializeFilters(filters)] as const,
  recurringIssues: (filters: QueryFilters = {}) =>
    ["maintenance", "recurring-issues", serializeFilters(filters)] as const,
};
