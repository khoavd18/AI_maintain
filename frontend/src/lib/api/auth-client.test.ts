import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  registerAuthHandlers,
  setAccessToken,
} from "@/lib/api/auth-session";
import { api } from "@/lib/api/endpoints";
import { summaryFixture } from "@/test/fixtures";

describe("authenticated API client", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
  });

  afterEach(() => {
    document.cookie = "maintenance_csrf=; Max-Age=0; Path=/";
  });

  it("holds access tokens in memory and attaches credentials centrally", async () => {
    const storageSpy = vi.spyOn(Storage.prototype, "setItem");
    setAccessToken("memory-access-token");
    const fetchMock = vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
      expect(new Headers(init?.headers).get("Authorization")).toBe(
        "Bearer memory-access-token",
      );
      expect(init?.credentials).toBe("include");
      return jsonResponse(summaryFixture);
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.summary()).resolves.toEqual(summaryFixture);
    expect(storageSpy).not.toHaveBeenCalled();
  });

  it("performs one controlled refresh and retries the original request once", async () => {
    setAccessToken("expired-access-token");
    let refreshCount = 0;
    let expiredCount = 0;
    registerAuthHandlers({
      refresh: async () => {
        refreshCount += 1;
        setAccessToken("rotated-access-token");
        return true;
      },
      expired: () => {
        expiredCount += 1;
      },
    });
    const seenTokens: (string | null)[] = [];
    const fetchMock = vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
      seenTokens.push(new Headers(init?.headers).get("Authorization"));
      return seenTokens.length === 1
        ? jsonResponse({ detail: "expired" }, 401)
        : jsonResponse(summaryFixture);
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.summary()).resolves.toEqual(summaryFixture);
    expect(refreshCount).toBe(1);
    expect(expiredCount).toBe(0);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(seenTokens).toEqual([
      "Bearer expired-access-token",
      "Bearer rotated-access-token",
    ]);
  });

  it("does not loop when refresh fails", async () => {
    setAccessToken("expired-access-token");
    const refresh = vi.fn(async () => false);
    const expired = vi.fn();
    registerAuthHandlers({ refresh, expired });
    const fetchMock = vi.fn(async () => jsonResponse({ detail: "expired" }, 401));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.summary()).rejects.toMatchObject({ code: "unauthenticated" });
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(expired).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("sends the CSRF token on logout without exposing a refresh token", async () => {
    document.cookie = "maintenance_csrf=csrf-test-value; Path=/";
    const fetchMock = vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      expect(headers.get("X-CSRF-Token")).toBe("csrf-test-value");
      expect(headers.get("Authorization")).toBeNull();
      expect(init?.credentials).toBe("include");
      return new Response(null, { status: 204 });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.logout()).resolves.toBeUndefined();
  });
});

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
