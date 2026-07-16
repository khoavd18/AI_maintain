import { afterEach, describe, expect, it, vi } from "vitest";

import { getJson } from "@/lib/api/client";
import { normalizeApiBaseUrl } from "@/lib/api/config";
import { UserSafeApiError } from "@/lib/api/errors";
import {
  healthResponseSchema,
  ticketsResponseSchema,
} from "@/lib/api/schemas";
import { healthFixture, ticketsFixture } from "@/test/fixtures";

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
});

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
