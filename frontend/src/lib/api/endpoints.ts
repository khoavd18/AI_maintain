import { z } from "zod";

import {
  deleteJson,
  getBinary,
  getJson,
  patchJson,
  postForm,
  postJson,
  postNoContent,
} from "@/lib/api/client";
import { withQuery, type QueryFilters } from "@/lib/api/query-keys";
import {
  anomaliesResponseSchema,
  auditLogPageSchema,
  assetArchiveRequestSchema,
  assetAttachmentSchema,
  assetAttachmentsSchema,
  assetCatalogPageSchema,
  assetCreateRequestSchema,
  authResponseSchema,
  assetDetailsResponseSchema,
  assetsResponseSchema,
  assetHistoryPageSchema,
  assetOptionsSchema,
  assetProfileSchema,
  assetQrSchema,
  assetRestoreRequestSchema,
  assetUpdateRequestSchema,
  copilotAskRequestSchema,
  copilotAskResponseSchema,
  healthResponseSchema,
  loginRequestSchema,
  lifecycleTransitionRequestSchema,
  locationsResponseSchema,
  maintenanceKpiResponseSchema,
  maintenanceLogsResponseSchema,
  maintenanceLogCreateRequestSchema,
  maintenanceLogCreateResponseSchema,
  operationalStatusRequestSchema,
  preventiveResponseSchema,
  recurringIssuesResponseSchema,
  risksResponseSchema,
  summaryResponseSchema,
  ticketsResponseSchema,
  ticketCreateRequestSchema,
  ticketCreateResponseSchema,
  ticketUpdateRequestSchema,
  ticketUpdateResponseSchema,
  roleOptionsResponseSchema,
  userCreateRequestSchema,
  userResponseSchema,
  usersResponseSchema,
  userUpdateRequestSchema,
  type LoginRequest,
  type AssetArchiveRequest,
  type AssetCreateRequest,
  type AssetRestoreRequest,
  type AssetUpdateRequest,
  type LifecycleTransitionRequest,
  type OperationalStatusRequest,
  type UserCreateRequest,
  type UserUpdateRequest,
  type CopilotAskRequest,
  type MaintenanceLogCreateRequest,
  type TicketCreateRequest,
  type TicketUpdateRequest,
} from "@/lib/api/schemas";

const emptyRequestSchema = z.object({});

export const api = {
  health: (signal?: AbortSignal) => getJson("/health", healthResponseSchema, { signal }),
  summary: (signal?: AbortSignal) => getJson("/summary", summaryResponseSchema, { signal }),
  maintenanceKpis: (signal?: AbortSignal) =>
    getJson("/maintenance/kpis", maintenanceKpiResponseSchema, { signal }),
  assets: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(withQuery("/assets", filters), assetsResponseSchema, { signal }),
  assetCatalog: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(withQuery("/assets/catalog", filters), assetCatalogPageSchema, { signal }),
  assetOptions: (signal?: AbortSignal) =>
    getJson("/assets/options", assetOptionsSchema, { signal }),
  assetProfile: (assetId: string, signal?: AbortSignal) =>
    getJson(`/assets/${encodeURIComponent(assetId)}/profile`, assetProfileSchema, { signal }),
  locations: (includeArchived = false, signal?: AbortSignal) =>
    getJson(
      withQuery("/locations", { include_archived: includeArchived }),
      locationsResponseSchema,
      { signal },
    ),
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
  createTicket: (request: TicketCreateRequest, signal?: AbortSignal) =>
    postJson(
      "/tickets",
      request,
      ticketCreateRequestSchema,
      ticketCreateResponseSchema,
      { signal },
    ),
  createAsset: (request: AssetCreateRequest, signal?: AbortSignal) =>
    postJson("/assets", request, assetCreateRequestSchema, assetProfileSchema, { signal }),
  updateAsset: (assetId: string, request: AssetUpdateRequest, signal?: AbortSignal) =>
    patchJson(
      `/assets/${encodeURIComponent(assetId)}`,
      request,
      assetUpdateRequestSchema,
      assetProfileSchema,
      { signal },
    ),
  changeAssetOperationalStatus: (
    assetId: string,
    request: OperationalStatusRequest,
    signal?: AbortSignal,
  ) =>
    postJson(
      `/assets/${encodeURIComponent(assetId)}/operational-status`,
      request,
      operationalStatusRequestSchema,
      assetProfileSchema,
      { signal },
    ),
  transitionAssetLifecycle: (
    assetId: string,
    request: LifecycleTransitionRequest,
    signal?: AbortSignal,
  ) =>
    postJson(
      `/assets/${encodeURIComponent(assetId)}/lifecycle-transition`,
      request,
      lifecycleTransitionRequestSchema,
      assetProfileSchema,
      { signal },
    ),
  archiveAsset: (assetId: string, request: AssetArchiveRequest, signal?: AbortSignal) =>
    postJson(
      `/assets/${encodeURIComponent(assetId)}/archive`,
      request,
      assetArchiveRequestSchema,
      assetProfileSchema,
      { signal },
    ),
  restoreAsset: (assetId: string, request: AssetRestoreRequest, signal?: AbortSignal) =>
    postJson(
      `/assets/${encodeURIComponent(assetId)}/restore`,
      request,
      assetRestoreRequestSchema,
      assetProfileSchema,
      { signal },
    ),
  assetAttachments: (assetId: string, signal?: AbortSignal) =>
    getJson(
      `/assets/${encodeURIComponent(assetId)}/attachments`,
      assetAttachmentsSchema,
      { signal },
    ),
  uploadAssetAttachment: (
    assetId: string,
    category: string,
    file: File,
    signal?: AbortSignal,
  ) => {
    const body = new FormData();
    body.set("category", category);
    body.set("file", file);
    return postForm(
      `/assets/${encodeURIComponent(assetId)}/attachments`,
      body,
      assetAttachmentSchema,
      { signal },
    );
  },
  downloadAssetAttachment: (assetId: string, attachmentId: string, signal?: AbortSignal) =>
    getBinary(
      `/assets/${encodeURIComponent(assetId)}/attachments/${encodeURIComponent(attachmentId)}`,
      { signal },
    ),
  deleteAssetAttachment: (assetId: string, attachmentId: string, signal?: AbortSignal) =>
    deleteJson(
      `/assets/${encodeURIComponent(assetId)}/attachments/${encodeURIComponent(attachmentId)}`,
      assetAttachmentSchema,
      { signal },
    ),
  assetQr: (assetId: string, signal?: AbortSignal) =>
    getJson(`/assets/${encodeURIComponent(assetId)}/qr`, assetQrSchema, { signal }),
  qrLookup: (lookupToken: string, signal?: AbortSignal) =>
    getJson(`/asset-lookup/${encodeURIComponent(lookupToken)}`, assetProfileSchema, { signal }),
  assetHistory: (assetId: string, filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(
      withQuery(`/assets/${encodeURIComponent(assetId)}/history`, filters),
      assetHistoryPageSchema,
      { signal },
    ),
  updateTicket: (ticketId: string, request: TicketUpdateRequest, signal?: AbortSignal) =>
    patchJson(
      `/tickets/${encodeURIComponent(ticketId)}`,
      request,
      ticketUpdateRequestSchema,
      ticketUpdateResponseSchema,
      { signal },
    ),
  createMaintenanceLog: (request: MaintenanceLogCreateRequest, signal?: AbortSignal) =>
    postJson(
      "/maintenance/logs",
      request,
      maintenanceLogCreateRequestSchema,
      maintenanceLogCreateResponseSchema,
      { signal },
    ),
  askCopilot: (request: CopilotAskRequest, signal?: AbortSignal) =>
    postJson(
      "/copilot/ask",
      request,
      copilotAskRequestSchema,
      copilotAskResponseSchema,
      // Covers the default backend envelope of two 30-second provider attempts
      // plus response validation without aborting a generation still in flight.
      { signal, operation: "copilot", timeoutMs: 75_000 },
    ),
  login: (request: LoginRequest, signal?: AbortSignal) =>
    postJson("/auth/login", request, loginRequestSchema, authResponseSchema, {
      signal,
      operation: "auth",
      skipAuth: true,
      skipRefresh: true,
    }),
  refreshSession: (signal?: AbortSignal) =>
    postJson("/auth/refresh", {}, emptyRequestSchema, authResponseSchema, {
      signal,
      operation: "auth",
      skipAuth: true,
      skipRefresh: true,
      csrf: true,
    }),
  logout: (signal?: AbortSignal) =>
    postNoContent("/auth/logout", {
      signal,
      skipAuth: true,
      skipRefresh: true,
      csrf: true,
    }),
  currentUser: (signal?: AbortSignal) =>
    getJson("/auth/me", userResponseSchema, { signal }),
  users: (signal?: AbortSignal) => getJson("/users", usersResponseSchema, { signal }),
  roleOptions: (signal?: AbortSignal) =>
    getJson("/users/roles", roleOptionsResponseSchema, { signal }),
  createUser: (request: UserCreateRequest, signal?: AbortSignal) =>
    postJson("/users", request, userCreateRequestSchema, userResponseSchema, { signal }),
  updateUser: (userId: string, request: UserUpdateRequest, signal?: AbortSignal) =>
    patchJson(
      `/users/${encodeURIComponent(userId)}`,
      request,
      userUpdateRequestSchema,
      userResponseSchema,
      { signal },
    ),
  auditLogs: (filters: QueryFilters = {}, signal?: AbortSignal) =>
    getJson(withQuery("/audit-logs", filters), auditLogPageSchema, { signal }),
};
