import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { vi } from "vitest";

import { AuthTestProvider } from "@/components/auth-provider";
import { CopilotStatusProvider } from "@/components/copilot-status-provider";
import { permissions } from "@/lib/auth";
import type { UserResponse } from "@/lib/api/schemas";

export const administratorTestUser: UserResponse = {
  id: "11111111-1111-4111-8111-111111111111",
  username: "admin.test",
  email: null,
  display_name: "Quản trị viên test",
  role: "administrator",
  role_display_name: "Quản trị viên",
  permissions: Object.values(permissions),
  technician_id: null,
  is_active: true,
  created_at: "2026-07-18T00:00:00Z",
  updated_at: "2026-07-18T00:00:00Z",
  last_login_at: "2026-07-18T00:00:00Z",
  version: 1,
};

export function renderWithQuery(
  ui: React.ReactElement,
  user: UserResponse = administratorTestUser,
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthTestProvider user={user}>
        <CopilotStatusProvider>{ui}</CopilotStatusProvider>
      </AuthTestProvider>
    </QueryClientProvider>,
  );
}

export function mockApi(responses: Record<string, MockRoute>) {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
  const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const rawUrl = input instanceof Request ? input.url : String(input);
    const url = new URL(rawUrl);
    const key = `${url.pathname}${url.search}`;
    const method = (input instanceof Request ? input.method : init?.method) ?? "GET";
    const configured =
      responses[`${method} ${key}`] ??
      responses[`${method} ${url.pathname}`] ??
      responses[key] ??
      responses[url.pathname];
    if (configured === undefined) {
      throw new Error(`Unexpected request: ${key}`);
    }
    const resolved = typeof configured === "function" ? await configured(input, init) : configured;
    const response = isMockResponse(resolved) ? resolved : { body: resolved, status: 200 };
    return new Response(response.status === 204 ? null : JSON.stringify(response.body), {
      status: response.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

interface MockResponse {
  body: unknown;
  status?: number;
}

type MockRoute =
  | unknown
  | MockResponse
  | ((input: string | URL | Request, init?: RequestInit) => unknown | Promise<unknown>);

function isMockResponse(value: unknown): value is MockResponse {
  return typeof value === "object" && value !== null && "body" in value;
}
