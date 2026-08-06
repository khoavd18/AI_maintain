"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import type {
  AssetArchiveRequest,
  AssetCreateRequest,
  AssetRestoreRequest,
  AssetUpdateRequest,
  LifecycleTransitionRequest,
  OperationalStatusRequest,
} from "@/lib/api/schemas";

import { invalidateAssetQueries } from "./common";

export function useCreateAsset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: AssetCreateRequest) => api.createAsset(request),
    onSuccess: async (asset) => {
      await invalidateAssetQueries(queryClient, asset.asset_id);
      await queryClient.invalidateQueries({ queryKey: queryKeys.locations(false) });
    },
  });
}

export function useUpdateAsset(assetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: AssetUpdateRequest) => api.updateAsset(assetId, request),
    onSuccess: async () => invalidateAssetQueries(queryClient, assetId),
  });
}

export function useChangeAssetOperationalStatus(assetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: OperationalStatusRequest) =>
      api.changeAssetOperationalStatus(assetId, request),
    onSuccess: async () => invalidateAssetQueries(queryClient, assetId),
  });
}

export function useTransitionAssetLifecycle(assetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: LifecycleTransitionRequest) =>
      api.transitionAssetLifecycle(assetId, request),
    onSuccess: async () => invalidateAssetQueries(queryClient, assetId),
  });
}

export function useArchiveAsset(assetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: AssetArchiveRequest) => api.archiveAsset(assetId, request),
    onSuccess: async () => invalidateAssetQueries(queryClient, assetId),
  });
}

export function useRestoreAsset(assetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: AssetRestoreRequest) => api.restoreAsset(assetId, request),
    onSuccess: async () => invalidateAssetQueries(queryClient, assetId),
  });
}

export function useUploadAssetAttachment(assetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ category, file }: { category: string; file: File }) =>
      api.uploadAssetAttachment(assetId, category, file),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.assetAttachments(assetId) });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.assetHistory(assetId),
      });
    },
  });
}

export function useDeleteAssetAttachment(assetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (attachmentId: string) => api.deleteAssetAttachment(assetId, attachmentId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.assetAttachments(assetId) });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.assetHistory(assetId),
      });
    },
  });
}
