"use client";

import type { QueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/lib/api/query-keys";

type QueryKey = readonly unknown[];

export async function refreshAffectedQueries(queryClient: QueryClient, keys: QueryKey[]) {
  await Promise.all(
    keys.map((queryKey) => queryClient.invalidateQueries({ queryKey, refetchType: "none" })),
  );
  try {
    await Promise.all(
      keys.map((queryKey) =>
        queryClient.refetchQueries({ queryKey, type: "active" }, { throwOnError: true }),
      ),
    );
    return true;
  } catch {
    return false;
  }
}

export async function invalidateAssetQueries(queryClient: QueryClient, assetId: string) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.assetCatalogs }),
    queryClient.invalidateQueries({ queryKey: queryKeys.assetLists }),
    queryClient.invalidateQueries({ queryKey: queryKeys.assetProfile(assetId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.assetDetailsRoot(assetId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.assetHistory(assetId) }),
  ]);
}

export async function invalidateMaintenancePlanning(queryClient: QueryClient, planId?: string) {
  const operations = [
    queryClient.invalidateQueries({ queryKey: queryKeys.maintenancePlanLists }),
    queryClient.invalidateQueries({ queryKey: queryKeys.workOrderSchedule() }),
  ];
  if (planId) {
    operations.push(
      queryClient.invalidateQueries({ queryKey: queryKeys.maintenancePlan(planId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.maintenancePlanOccurrences(planId) }),
    );
  }
  await Promise.all(operations);
}

export async function invalidateWorkOrderQueries(queryClient: QueryClient, workOrderId?: string) {
  const operations = [
    queryClient.invalidateQueries({ queryKey: queryKeys.workOrderLists }),
    queryClient.invalidateQueries({ queryKey: ["work-orders", "calendar"] }),
    queryClient.invalidateQueries({ queryKey: ["work-orders", "metrics"] }),
  ];
  if (workOrderId) {
    operations.push(queryClient.invalidateQueries({ queryKey: queryKeys.workOrder(workOrderId) }));
  }
  await Promise.all(operations);
}
