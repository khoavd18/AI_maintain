import { afterEach, describe, expect, it, vi } from "vitest";

import { getJson, postJson } from "@/lib/api/client";
import { normalizeApiBaseUrl } from "@/lib/api/config";
import { api } from "@/lib/api/endpoints";
import { UserSafeApiError } from "@/lib/api/errors";
import {
  healthResponseSchema,
  copilotAskRequestSchema,
  copilotAskResponseSchema,
  ticketCreateRequestSchema,
  ticketCreateResponseSchema,
  ticketsResponseSchema,
} from "@/lib/api/schemas";
import { copilotResponseFixture, copilotUnavailableFixture, healthFixture, ticketsFixture } from "@/test/fixtures";

describe("API configuration", () => {
  it("normalizes trailing slashes", () => {
    expect(normalizeApiBaseUrl(" http://127.0.0.1:8000/// ")).toBe(
      "http://127.0.0.1:8000",
    );
  });

  it("rejects a missing base URL with a friendly error", () => {
    expect(() => normalizeApiBaseUrl(undefined)).toThrow("NEXT_PUBLIC_API_BASE_URL");
  });
});

describe("typed API client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("parses a successful API response", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(healthFixture)));

    await expect(getJson("/health", healthResponseSchema)).resolves.toEqual(healthFixture);
  });

  it("accepts contract-defined nullable fields", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(ticketsFixture)));

    const result = await getJson("/tickets", ticketsResponseSchema);
    expect(result[0].resolved_at).toBeNull();
    expect(result[0].manager_note).toBeNull();
  });

  it("rejects an invalid response instead of coercing it", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ ...healthFixture, status: "maybe" })));

    await expect(getJson("/health", healthResponseSchema)).rejects.toMatchObject({
      code: "invalid_response",
    });
  });

  it("maps network failures to a safe retryable error", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("socket details"); }));

    await expect(getJson("/health", healthResponseSchema)).rejects.toMatchObject({
      code: "network",
      retryable: true,
    });
  });

  it.each([
    [404, "not_found"],
    [422, "validation"],
    [503, "analytics_unavailable"],
  ])("maps HTTP %i without exposing backend details", async (status, code) => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: "C:\\private\\data.csv" }, status)));

    let caught: unknown;
    try {
      await getJson("/health", healthResponseSchema);
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(UserSafeApiError);
    expect(caught).toMatchObject({ code, status });
    expect((caught as Error).message).not.toContain("private");
  });

  it("rejects invalid JSON", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    vi.stubGlobal("fetch", vi.fn(async () => new Response("not-json", { status: 200 })));

    await expect(getJson("/health", healthResponseSchema)).rejects.toMatchObject({
      code: "invalid_response",
    });
  });

  it("creates a ticket with the exact POST contract", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    const fetchMock = vi.fn(async () => jsonResponse(createdTicket, 201));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.createTicket(ticketCreateRequest)).resolves.toEqual(createdTicket);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/tickets",
      expect.objectContaining({ method: "POST", body: JSON.stringify(ticketCreateRequest) }),
    );
  });

  it("updates a ticket with PATCH and validates the response", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    const response = { ...createdTicket, status: "Đang xử lý" as const };
    const fetchMock = vi.fn(async () => jsonResponse(response));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.updateTicket(createdTicket.ticket_id, { status: "Đang xử lý" })).resolves.toEqual(response);
    expect(fetchMock).toHaveBeenCalledWith(
      `http://127.0.0.1:8000/tickets/${createdTicket.ticket_id}`,
      expect.objectContaining({ method: "PATCH" }),
    );
  });

  it("creates a maintenance log with the exact POST contract", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    const fetchMock = vi.fn(async () => jsonResponse(createdLog, 201));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.createMaintenanceLog(maintenanceRequest)).resolves.toEqual(createdLog);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/maintenance/logs",
      expect.objectContaining({ method: "POST", body: JSON.stringify(maintenanceRequest) }),
    );
  });

  it.each([
    [400, "business_rule"],
    [404, "not_found"],
    [409, "conflict"],
    [503, "write_unavailable"],
  ])("maps write HTTP %i to %s", async (status, code) => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: "Yêu cầu bị từ chối." }, status)));
    await expect(api.createTicket(ticketCreateRequest)).rejects.toMatchObject({ code, status });
  });

  it("maps backend 422 issues to fields", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({
      detail: [{ loc: ["body", "technician_id"], msg: "Field required", type: "missing" }],
    }, 422)));
    await expect(api.createTicket(ticketCreateRequest)).rejects.toMatchObject({
      code: "validation",
      fieldErrors: { technician_id: "Field required" },
    });
  });

  it("does not silently accept a malformed successful write response", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ ticket_id: "TCK-000043" }, 201)));
    await expect(api.createTicket(ticketCreateRequest)).rejects.toMatchObject({
      code: "invalid_response",
      ambiguousWrite: true,
    });
  });

  it("marks a write network failure as ambiguous and non-retryable", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("socket closed"); }));
    await expect(api.createTicket(ticketCreateRequest)).rejects.toMatchObject({
      code: "network",
      ambiguousWrite: true,
      retryable: false,
    });
  });

  it("marks a timed-out write as ambiguous", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    vi.stubGlobal("fetch", vi.fn((_input, init?: RequestInit) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    })));
    await expect(postJson(
      "/tickets",
      ticketCreateRequest,
      ticketCreateRequestSchema,
      ticketCreateResponseSchema,
      { timeoutMs: 1 },
    )).rejects.toMatchObject({ code: "timeout", ambiguousWrite: true });
  });

  it("asks Copilot with the exact backend request contract", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    const fetchMock = vi.fn(async () => jsonResponse(copilotResponseFixture));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.askCopilot(copilotRequest)).resolves.toEqual(copilotResponseFixture);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/copilot/ask",
      expect.objectContaining({ method: "POST", body: JSON.stringify(copilotRequest) }),
    );
  });

  it("accepts a confirmed RAG fallback as a valid response", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(copilotUnavailableFixture)));

    await expect(api.askCopilot(copilotRequest)).resolves.toMatchObject({
      retrieval_status: "unavailable",
      sources: [],
    });
  });

  it.each([
    [400, "business_rule"],
    [404, "not_found"],
    [422, "validation"],
    [503, "rag_unavailable"],
  ])("maps Copilot HTTP %i to %s", async (status, code) => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: "Yêu cầu Copilot không khả dụng." }, status)));
    await expect(api.askCopilot(copilotRequest)).rejects.toMatchObject({ code, status });
  });

  it("treats Copilot network and malformed responses as retryable reads, not ambiguous writes", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("socket closed"); }));
    await expect(api.askCopilot(copilotRequest)).rejects.toMatchObject({
      code: "network",
      ambiguousWrite: false,
      retryable: true,
    });

    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ answer: "missing fields" })));
    await expect(api.askCopilot(copilotRequest)).rejects.toMatchObject({
      code: "invalid_response",
      ambiguousWrite: false,
    });
  });

  it("maps a Copilot timeout without marking a CSV write as ambiguous", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    vi.stubGlobal("fetch", vi.fn((_input, init?: RequestInit) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    })));
    await expect(postJson(
      "/copilot/ask",
      copilotRequest,
      copilotAskRequestSchema,
      copilotAskResponseSchema,
      { timeoutMs: 1, operation: "copilot" },
    )).rejects.toMatchObject({ code: "timeout", ambiguousWrite: false, retryable: true });
  });
});

const copilotRequest = {
  question: "Vì sao GENERATOR_002 đang rủi ro cao?",
  asset_id: "GENERATOR_002",
  top_k: 5,
  failure_category: "Lỗi điện",
};

const ticketCreateRequest = {
  asset_id: "GENERATOR_002",
  issue_description: "Kiểm tra cảnh báo điện áp ắc quy.",
  priority: "Cao" as const,
  failure_category: "Lỗi điện" as const,
  technician_id: "TECH_003",
  manager_note: null,
};

const createdTicket = {
  ticket_id: "TCK-000043",
  ...ticketCreateRequest,
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
  technician_note: "Điện áp ổn định sau kiểm tra.",
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

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
