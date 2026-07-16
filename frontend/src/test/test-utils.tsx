import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { vi } from "vitest";

export function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
    },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

export function mockApi(responses: Record<string, unknown | MockResponse>) {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
  const fetchMock = vi.fn(async (input: string | URL | Request) => {
    const rawUrl = input instanceof Request ? input.url : String(input);
    const url = new URL(rawUrl);
    const key = `${url.pathname}${url.search}`;
    const configured = responses[key] ?? responses[url.pathname];
    if (configured === undefined) {
      throw new Error(`Unexpected request: ${key}`);
    }
    const response = isMockResponse(configured) ? configured : { body: configured, status: 200 };
    return new Response(JSON.stringify(response.body), {
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

function isMockResponse(value: unknown): value is MockResponse {
  return typeof value === "object" && value !== null && "body" in value;
}
