"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/endpoints";
import { maintenanceApi } from "@/lib/api/maintenance-endpoints";
import { queryKeys, type QueryFilters } from "@/lib/api/query-keys";

export function useHealthQuery() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => api.health(signal),
    staleTime: 30_000,
  });
}

export function useSummaryQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.summary,
    queryFn: ({ signal }) => api.summary(signal),
    enabled,
  });
}

export function useMaintenanceKpisQuery() {
  return useQuery({
    queryKey: queryKeys.kpis,
    queryFn: ({ signal }) => api.maintenanceKpis(signal),
  });
}

export function useAssetsQuery(filters: QueryFilters = {}) {
  return useQuery({
    queryKey: queryKeys.assets(filters),
    queryFn: ({ signal }) => api.assets(filters, signal),
    placeholderData: keepPreviousData,
  });
}

export function useAssetCatalogQuery(filters: QueryFilters = {}) {
  return useQuery({
    queryKey: queryKeys.assetCatalog(filters),
    queryFn: ({ signal }) => api.assetCatalog(filters, signal),
    placeholderData: keepPreviousData,
  });
}

export function useAssetOptionsQuery() {
  return useQuery({
    queryKey: queryKeys.assetOptions,
    queryFn: ({ signal }) => api.assetOptions(signal),
    staleTime: 5 * 60_000,
  });
}

export function useLocationsQuery(includeArchived = false, enabled = true) {
  return useQuery({
    queryKey: queryKeys.locations(includeArchived),
    queryFn: ({ signal }) => api.locations(includeArchived, signal),
    enabled,
    staleTime: 60_000,
  });
}

export function useAssetProfileQuery(assetId: string) {
  return useQuery({
    queryKey: queryKeys.assetProfile(assetId),
    queryFn: ({ signal }) => api.assetProfile(assetId, signal),
    enabled: Boolean(assetId),
  });
}

export function useAssetDetailsQuery(assetId: string, limit = 10) {
  return useQuery({
    queryKey: queryKeys.assetDetails(assetId, limit),
    queryFn: ({ signal }) => api.assetDetails(assetId, limit, signal),
    enabled: Boolean(assetId),
  });
}

export function useAssetAttachmentsQuery(assetId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.assetAttachments(assetId),
    queryFn: ({ signal }) => api.assetAttachments(assetId, signal),
    enabled: Boolean(assetId) && enabled,
  });
}

export function useAssetQrQuery(assetId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.assetQr(assetId),
    queryFn: ({ signal }) => api.assetQr(assetId, signal),
    enabled: Boolean(assetId) && enabled,
    staleTime: Number.POSITIVE_INFINITY,
  });
}

export function useAssetHistoryQuery(
  assetId: string,
  filters: QueryFilters = { page: 1, page_size: 20 },
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.assetHistory(assetId, filters),
    queryFn: ({ signal }) => api.assetHistory(assetId, filters, signal),
    enabled: Boolean(assetId) && enabled,
    placeholderData: keepPreviousData,
  });
}

export function useQrLookupQuery(lookupToken: string) {
  return useQuery({
    queryKey: queryKeys.qrLookup(lookupToken),
    queryFn: ({ signal }) => api.qrLookup(lookupToken, signal),
    enabled: Boolean(lookupToken),
  });
}

export function useRisksQuery(filters: QueryFilters = {}) {
  return useQuery({
    queryKey: queryKeys.risks(filters),
    queryFn: ({ signal }) => api.risks(filters, signal),
    placeholderData: keepPreviousData,
  });
}

export function useTicketsQuery(filters: QueryFilters = {}) {
  return useQuery({
    queryKey: queryKeys.tickets(filters),
    queryFn: ({ signal }) => api.tickets(filters, signal),
    placeholderData: keepPreviousData,
  });
}

export function useMaintenanceLogsQuery(filters: QueryFilters = {}) {
  return useQuery({
    queryKey: queryKeys.maintenanceLogs(filters),
    queryFn: ({ signal }) => api.maintenanceLogs(filters, signal),
    placeholderData: keepPreviousData,
  });
}

export function useMaintenanceOptionsQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.maintenanceOptions,
    queryFn: ({ signal }) => maintenanceApi.options(signal),
    enabled,
    staleTime: 5 * 60_000,
  });
}

export function useMaintenancePlansQuery(filters: QueryFilters = {}, enabled = true) {
  return useQuery({
    queryKey: queryKeys.maintenancePlans(filters),
    queryFn: ({ signal }) => maintenanceApi.plans(filters, signal),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useMaintenancePlanQuery(planId: string) {
  return useQuery({
    queryKey: queryKeys.maintenancePlan(planId),
    queryFn: ({ signal }) => maintenanceApi.plan(planId, signal),
    enabled: Boolean(planId),
  });
}

export function useMaintenancePlanOccurrencesQuery(
  planId: string,
  filters: QueryFilters,
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.maintenancePlanOccurrences(planId, filters),
    queryFn: ({ signal }) => maintenanceApi.occurrences(planId, filters, signal),
    enabled: Boolean(planId) && enabled,
  });
}

export function useChecklistTemplatesQuery(filters: QueryFilters = {}, enabled = true) {
  return useQuery({
    queryKey: queryKeys.checklistTemplates(filters),
    queryFn: ({ signal }) => maintenanceApi.templates(filters, signal),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useChecklistTemplateQuery(templateId: string) {
  return useQuery({
    queryKey: queryKeys.checklistTemplate(templateId),
    queryFn: ({ signal }) => maintenanceApi.template(templateId, signal),
    enabled: Boolean(templateId),
  });
}

export function useWorkOrdersQuery(filters: QueryFilters = {}, enabled = true) {
  return useQuery({
    queryKey: queryKeys.workOrders(filters),
    queryFn: ({ signal }) => maintenanceApi.workOrders(filters, signal),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useWorkOrderQuery(workOrderId: string) {
  return useQuery({
    queryKey: queryKeys.workOrder(workOrderId),
    queryFn: ({ signal }) => maintenanceApi.workOrder(workOrderId, signal),
    enabled: Boolean(workOrderId),
  });
}

export function useWorkOrderAttachmentsQuery(workOrderId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.workOrderAttachments(workOrderId),
    queryFn: ({ signal }) => maintenanceApi.attachments(workOrderId, signal),
    enabled: Boolean(workOrderId) && enabled,
  });
}

export function useWorkOrderScheduleQuery(filters: QueryFilters, enabled = true) {
  return useQuery({
    queryKey: queryKeys.workOrderSchedule(filters),
    queryFn: ({ signal }) => maintenanceApi.schedule(filters, signal),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useWorkOrderMetricsQuery(asOfDate: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.workOrderMetrics(asOfDate),
    queryFn: ({ signal }) => maintenanceApi.metrics(asOfDate, signal),
    enabled: Boolean(asOfDate) && enabled,
  });
}

export function useTicketWorkOrdersQuery(ticketId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.ticketWorkOrders(ticketId),
    queryFn: ({ signal }) => maintenanceApi.ticketWorkOrders(ticketId, signal),
    enabled: Boolean(ticketId) && enabled,
  });
}

export function useAnomaliesQuery(filters: QueryFilters = {}) {
  return useQuery({
    queryKey: queryKeys.anomalies(filters),
    queryFn: ({ signal }) => api.anomalies(filters, signal),
    placeholderData: keepPreviousData,
  });
}

export function usePreventiveQuery(filters: QueryFilters = {}) {
  return useQuery({
    queryKey: queryKeys.preventive(filters),
    queryFn: ({ signal }) => api.preventive(filters, signal),
    placeholderData: keepPreviousData,
  });
}

export function useRecurringIssuesQuery(filters: QueryFilters = {}) {
  return useQuery({
    queryKey: queryKeys.recurringIssues(filters),
    queryFn: ({ signal }) => api.recurringIssues(filters, signal),
    placeholderData: keepPreviousData,
  });
}

export function useUsersQuery() {
  return useQuery({ queryKey: queryKeys.users, queryFn: ({ signal }) => api.users(signal) });
}

export function useRoleOptionsQuery() {
  return useQuery({
    queryKey: queryKeys.roleOptions,
    queryFn: ({ signal }) => api.roleOptions(signal),
  });
}

export function useAuditLogsQuery(filters: QueryFilters = {}) {
  return useQuery({
    queryKey: queryKeys.auditLogs(filters),
    queryFn: ({ signal }) => api.auditLogs(filters, signal),
    placeholderData: keepPreviousData,
  });
}
