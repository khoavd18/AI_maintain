"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import type { MaintenanceLogCreateRequest, TicketCreateRequest, TicketUpdateRequest } from "@/lib/api/schemas";

import { refreshAffectedQueries } from "./common";

export function useCreateTicket() {
  const queryClient = useQueryClient();
  const [refreshFailed, setRefreshFailed] = useState(false);
  const mutation = useMutation({
    mutationFn: (request: TicketCreateRequest) => api.createTicket(request),
    onMutate: () => setRefreshFailed(false),
    onSuccess: async (ticket) => {
      setRefreshFailed(
        !(await refreshAffectedQueries(queryClient, [
          queryKeys.ticketLists,
          queryKeys.assetLists,
          queryKeys.assetDetailsRoot(ticket.asset_id),
        ])),
      );
    },
  });
  return { ...mutation, refreshFailed };
}

export function useUpdateTicket(ticketId: string) {
  const queryClient = useQueryClient();
  const [refreshFailed, setRefreshFailed] = useState(false);
  const mutation = useMutation({
    mutationFn: (request: TicketUpdateRequest) => api.updateTicket(ticketId, request),
    onMutate: () => setRefreshFailed(false),
    onSuccess: async (ticket) => {
      setRefreshFailed(
        !(await refreshAffectedQueries(queryClient, [
          queryKeys.ticketLists,
          queryKeys.assetLists,
          queryKeys.assetDetailsRoot(ticket.asset_id),
        ])),
      );
    },
  });
  return { ...mutation, refreshFailed };
}

export function useCreateMaintenanceLog() {
  const queryClient = useQueryClient();
  const [refreshFailed, setRefreshFailed] = useState(false);
  const mutation = useMutation({
    mutationFn: (request: MaintenanceLogCreateRequest) => api.createMaintenanceLog(request),
    onMutate: () => setRefreshFailed(false),
    onSuccess: async (log) => {
      setRefreshFailed(
        !(await refreshAffectedQueries(queryClient, [
          queryKeys.maintenanceLogLists,
          queryKeys.assetLists,
          queryKeys.assetDetailsRoot(log.asset_id),
        ])),
      );
    },
  });
  return { ...mutation, refreshFailed };
}
