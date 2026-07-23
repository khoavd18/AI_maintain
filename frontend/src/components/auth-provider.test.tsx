import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  AuthenticatedApplication,
  AuthProvider,
  useAuth,
} from "@/components/auth-provider";
import { permissions } from "@/lib/auth";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { UserResponse } from "@/lib/api/schemas";
import { mockApi } from "@/test/test-utils";

const navigation = vi.hoisted(() => ({
  pathname: "/login",
  replace: vi.fn(),
  router: { replace: vi.fn() },
}));

navigation.router.replace = navigation.replace;

vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
  useRouter: () => navigation.router,
  useSearchParams: () => new URLSearchParams(),
}));

const user: UserResponse = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  username: "manager.test",
  email: null,
  display_name: "Quản lý test",
  role: "property_manager",
  role_display_name: "Quản lý cơ sở",
  permissions: [
    permissions.assetsRead,
    permissions.analyticsRead,
    permissions.ticketsRead,
    permissions.ticketsCreate,
  ],
  technician_id: null,
  is_active: true,
  created_at: "2026-07-18T00:00:00Z",
  updated_at: "2026-07-18T00:00:00Z",
  last_login_at: "2026-07-18T00:00:00Z",
  version: 1,
};

const authResponse = {
  access_token: "short-lived-access-token",
  token_type: "bearer",
  expires_at: "2026-07-18T00:15:00Z",
  user,
};

describe("AuthProvider", () => {
  it("restores an authenticated session through the refresh endpoint", async () => {
    mockApi({ "POST /auth/refresh": authResponse });
    renderAuth(<AuthProbe />);

    expect(await screen.findByText("Quản lý test")).toBeInTheDocument();
    expect(screen.getByText("authenticated")).toBeInTheDocument();
  });

  it("supports login success and uses a generic login failure", async () => {
    const fetchMock = mockApi({
      "POST /auth/refresh": { body: { detail: "expired" }, status: 401 },
      "POST /auth/login": authResponse,
    });
    renderAuth(<LoginProbe />);
    await screen.findByText("anonymous");
    fireEvent.click(screen.getByRole("button", { name: "Đăng nhập test" }));
    expect(await screen.findByText("Quản lý test")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);

    mockApi({
      "POST /auth/refresh": { body: { detail: "expired" }, status: 401 },
      "POST /auth/login": {
        body: { detail: "Thông tin đăng nhập không hợp lệ." },
        status: 401,
      },
    });
    renderAuth(<LoginProbe />);
    await screen.findByText("anonymous");
    fireEvent.click(screen.getAllByRole("button", { name: "Đăng nhập test" }).at(-1)!);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Thông tin đăng nhập không hợp lệ",
    );
  });

  it("clears the session after logout", async () => {
    mockApi({
      "POST /auth/refresh": authResponse,
      "POST /auth/logout": { body: null, status: 204 },
    });
    renderAuth(<AuthProbe />);
    expect(await screen.findByText("Quản lý test")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Đăng xuất test" }));
    expect(await screen.findByText("anonymous")).toBeInTheDocument();
  });

  it("redirects a revoked anonymous session to login without rendering protected content", async () => {
    navigation.pathname = "/tickets";
    navigation.replace.mockClear();
    mockApi({ "POST /auth/refresh": { body: { detail: "revoked" }, status: 401 } });
    renderAuth(
      <AuthenticatedApplication>
        <p>Nội dung bảo vệ</p>
      </AuthenticatedApplication>,
    );

    await waitFor(() =>
      expect(navigation.replace).toHaveBeenCalledWith("/login?next=%2Ftickets"),
    );
    expect(screen.queryByText("Nội dung bảo vệ")).not.toBeInTheDocument();
    navigation.pathname = "/login";
  });
});

function AuthProbe() {
  const auth = useAuth();
  return (
    <div>
      <span>{auth.status}</span>
      <span>{auth.user?.display_name}</span>
      <button type="button" onClick={() => void auth.logout()}>Đăng xuất test</button>
    </div>
  );
}

function LoginProbe() {
  const auth = useAuth();
  const [error, setError] = useState<string | null>(null);
  return (
    <div>
      <span>{auth.status}</span>
      <span>{auth.user?.display_name}</span>
      <button
        type="button"
        onClick={() =>
          void auth
            .login({ identifier: "manager.test", password: "test-password" })
            .catch((cause) => setError(getApiErrorMessage(cause)))
        }
      >
        Đăng nhập test
      </button>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}

function renderAuth(children: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>,
  );
}
