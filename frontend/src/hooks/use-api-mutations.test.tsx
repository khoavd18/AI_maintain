import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAskCopilot, useCreateMaintenanceLog, useCreateTicket, useUpdateTicket } from "@/hooks/use-api-mutations";
import { queryKeys } from "@/lib/api/query-keys";
import { copilotResponseFixture, copilotUnavailableFixture } from "@/test/fixtures";

describe("API mutation hooks", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
  });
  afterEach(() => vi.unstubAllGlobals());

  it("exposes pending state and invalidates only affected ticket and asset queries", async () => {
    const queryClient = createQueryClient();
    queryClient.setQueryData(queryKeys.tickets({ limit: 1000 }), []);
    queryClient.setQueryData(queryKeys.assets(), []);
    queryClient.setQueryData(queryKeys.risks(), []);
    let resolveResponse!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { resolveResponse = resolve; })));
    const { result } = renderHook(() => useCreateTicket(), { wrapper: wrapper(queryClient) });

    act(() => result.current.mutate(ticketRequest));
    await waitFor(() => expect(result.current.isPending).toBe(true));
    resolveResponse(jsonResponse(createdTicket, 201));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(queryClient.getQueryState(queryKeys.tickets({ limit: 1000 }))?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(queryKeys.assets())?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(queryKeys.risks())?.isInvalidated).toBe(false);
  });

  it("does not invalidate server data after a rejected write", async () => {
    const queryClient = createQueryClient();
    queryClient.setQueryData(queryKeys.tickets(), []);
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: "Quy tắc nghiệp vụ." }, 400)));
    const { result } = renderHook(() => useCreateTicket(), { wrapper: wrapper(queryClient) });

    await act(async () => { await expect(result.current.mutateAsync(ticketRequest)).rejects.toMatchObject({ code: "business_rule" }); });
    expect(queryClient.getQueryState(queryKeys.tickets())?.isInvalidated).toBe(false);
  });

  it("keeps a confirmed write successful when an active refetch fails", async () => {
    const queryClient = createQueryClient();
    let failRefresh = false;
    let queryRuns = 0;
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(createdTicket, 201)));
    const { result } = renderHook(() => {
      useQuery({
        queryKey: queryKeys.tickets({ limit: 1000 }),
        queryFn: async () => {
          queryRuns += 1;
          if (failRefresh) throw new Error("offline during refetch");
          return [];
        },
        retry: false,
      });
      return useCreateTicket();
    }, { wrapper: wrapper(queryClient) });
    await waitFor(() => expect(queryRuns).toBe(1));

    failRefresh = true;
    await act(async () => { await result.current.mutateAsync(ticketRequest); });
    await waitFor(() => expect(result.current.refreshFailed).toBe(true));
    expect(result.current.isSuccess).toBe(true);
  });

  it("uses focused update-ticket and maintenance-log mutations", async () => {
    const queryClient = createQueryClient();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ ...createdTicket, status: "Đang xử lý" }))
      .mockResolvedValueOnce(jsonResponse(createdLog, 201));
    vi.stubGlobal("fetch", fetchMock);
    const update = renderHook(() => useUpdateTicket(createdTicket.ticket_id), { wrapper: wrapper(queryClient) });
    const log = renderHook(() => useCreateMaintenanceLog(), { wrapper: wrapper(queryClient) });

    await act(async () => { await update.result.current.mutateAsync({ status: "Đang xử lý" }); });
    await act(async () => { await log.result.current.mutateAsync(maintenanceRequest); });

    expect(update.result.current.isSuccess).toBe(true);
    expect(log.result.current.isSuccess).toBe(true);
    expect(fetchMock).toHaveBeenNthCalledWith(1, expect.stringContaining("/tickets/TCK-000043"), expect.objectContaining({ method: "PATCH" }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, expect.stringContaining("/maintenance/logs"), expect.objectContaining({ method: "POST" }));
  });

  it("exposes Copilot pending and successful response states without invalidating analytics", async () => {
    const queryClient = createQueryClient();
    queryClient.setQueryData(queryKeys.assets(), [{ asset_id: "GENERATOR_002" }]);
    let resolveResponse!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { resolveResponse = resolve; })));
    const { result } = renderHook(() => useAskCopilot(), { wrapper: wrapper(queryClient) });

    act(() => result.current.mutate(copilotRequest));
    await waitFor(() => expect(result.current.isPending).toBe(true));
    resolveResponse(jsonResponse(copilotResponseFixture));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.retrieval_status).toBe("success");
    expect(queryClient.getQueryState(queryKeys.assets())?.isInvalidated).toBe(false);
  });

  it("keeps a confirmed fallback successful and supports retry after a transport failure", async () => {
    const queryClient = createQueryClient();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(copilotUnavailableFixture))
      .mockResolvedValueOnce(jsonResponse({ detail: "RAG unavailable" }, 503))
      .mockResolvedValueOnce(jsonResponse(copilotResponseFixture));
    vi.stubGlobal("fetch", fetchMock);
    const fallback = renderHook(() => useAskCopilot(), { wrapper: wrapper(queryClient) });

    await act(async () => { await fallback.result.current.mutateAsync(copilotRequest); });
    await waitFor(() => expect(fallback.result.current.isSuccess).toBe(true));
    expect(fallback.result.current.data?.retrieval_status).toBe("unavailable");

    const retry = renderHook(() => useAskCopilot(), { wrapper: wrapper(queryClient) });
    await act(async () => {
      await expect(retry.result.current.mutateAsync(copilotRequest)).rejects.toMatchObject({ code: "rag_unavailable" });
    });
    await act(async () => { await retry.result.current.mutateAsync(copilotRequest); });
    await waitFor(() => expect(retry.result.current.isSuccess).toBe(true));
  });
});

function createQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

function wrapper(queryClient: QueryClient) {
  return function TestWrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const ticketRequest = {
  asset_id: "GENERATOR_002",
  issue_description: "Kiểm tra cảnh báo điện áp ắc quy.",
  priority: "Cao" as const,
  failure_category: "Lỗi điện" as const,
  technician_id: "TECH_003",
  manager_note: null,
};

const copilotRequest = {
  question: "Vì sao GENERATOR_002 đang rủi ro cao?",
  asset_id: "GENERATOR_002",
  top_k: 5,
  failure_category: "Lỗi điện",
};

const createdTicket = {
  ticket_id: "TCK-000043",
  ...ticketRequest,
  status: "Mới tạo" as const,
  created_at: "2026-07-16T07:00:00+00:00",
  resolved_at: null,
  note: null,
};

const maintenanceRequest = {
  ticket_id: createdTicket.ticket_id,
  asset_id: createdTicket.asset_id,
  maintenance_date: "2026-07-16",
  inspection_result: "Ắc quy cần vệ sinh đầu cực.",
  actions_taken: "Vệ sinh đầu cực và đo lại điện áp.",
  parts_replaced: null,
  technician_note: "Điện áp ổn định.",
  maintenance_result: "Đã xử lý" as const,
  follow_up_required: false,
  next_maintenance_date: "2026-11-13",
};

const createdLog = {
  log_id: "LOG-000087",
  ...maintenanceRequest,
  maintenance_type: "Bảo trì sửa chữa" as const,
  technician_id: createdTicket.technician_id,
};
