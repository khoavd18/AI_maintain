import { getJson } from "@/lib/api/client";
import { withQuery, type QueryFilters } from "@/lib/api/query-keys";
import {
  anomaliesResponseSchema,
  assetDetailsResponseSchema,
  assetsResponseSchema,
  healthResponseSchema,
  maintenanceKpiResponseSchema,
  maintenanceLogsResponseSchema,
  preventiveResponseSchema,
  recurringIssuesResponseSchema,
  risksResponseSchema,
  summaryResponseSchema,
  ticketsResponseSchema,
} from "@/lib/api/schemas";

export const api = {
  health: (signal?: AbortSignal) => getJson("/health", healthResponseSchema, { signal }),
  summary: (signal?: AbortSignal) => getJson("/summary", summaryResponseSchema, { signal }),
  maintenanceKpis: (signal?: AbortSignal) =>
    getJson("/maintenance/kpis", maintenanceKpiResponseSchema, { signal }),
  assets: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(withQuery("/assets", filters), assetsResponseSchema, { signal }),
  assetDetails: (assetId: string, limit = 10, signal?: AbortSignal) =>
    getJson(
      withQuery(`/assets/${encodeURIComponent(assetId)}/details`, { limit }),
      assetDetailsResponseSchema,
      { signal },
    ),
  risks: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(withQuery("/assets/risk", filters), risksResponseSchema, { signal }),
  tickets: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(withQuery("/tickets", filters), ticketsResponseSchema, { signal }),
  maintenanceLogs: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(withQuery("/maintenance/logs", filters), maintenanceLogsResponseSchema, { signal }),
  anomalies: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(withQuery("/assets/anomalies", filters), anomaliesResponseSchema, { signal }),
  preventive: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(withQuery("/maintenance/preventive", filters), preventiveResponseSchema, { signal }),
  recurringIssues: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(
      withQuery("/maintenance/recurring-issues", filters),
      recurringIssuesResponseSchema,
      { signal },
    ),
};
