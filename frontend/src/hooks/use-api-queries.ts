"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/endpoints";
import { queryKeys, type QueryFilters } from "@/lib/api/query-keys";

export function useHealthQuery() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => api.health(signal),
    staleTime: 30_000,
  });
}

export function useSummaryQuery() {
  return useQuery({ queryKey: queryKeys.summary, queryFn: ({ signal }) => api.summary(signal) });
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

export function useAssetDetailsQuery(assetId: string, limit = 10) {
  return useQuery({
    queryKey: queryKeys.assetDetails(assetId, limit),
    queryFn: ({ signal }) => api.assetDetails(assetId, limit, signal),
    enabled: Boolean(assetId),
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
