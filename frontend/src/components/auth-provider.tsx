"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Loader2, ShieldAlert } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { AppShell } from "@/components/app-shell";
import { CopilotStatusProvider } from "@/components/copilot-status-provider";
import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import { permissions, type Permission } from "@/lib/auth";
import { api } from "@/lib/api/endpoints";
import {
  clearAccessToken,
  registerAuthHandlers,
  setAccessToken,
} from "@/lib/api/auth-session";
import type { LoginRequest, UserResponse } from "@/lib/api/schemas";

type AuthStatus = "restoring" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: AuthStatus;
  user: UserResponse | null;
  login: (request: LoginRequest) => Promise<UserResponse>;
  logout: () => Promise<void>;
  can: (permission: Permission) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("restoring");
  const [user, setUser] = useState<UserResponse | null>(null);
  const queryClient = useQueryClient();
  const router = useRouter();

  const becomeAnonymous = useCallback(() => {
    clearAccessToken();
    setUser(null);
    setStatus("anonymous");
    queryClient.clear();
  }, [queryClient]);

  const restoreSession = useCallback(async () => {
    try {
      const result = await api.refreshSession();
      setAccessToken(result.access_token);
      setUser(result.user);
      setStatus("authenticated");
      return true;
    } catch {
      becomeAnonymous();
      return false;
    }
  }, [becomeAnonymous]);

  useEffect(() => {
    const unregister = registerAuthHandlers({
      refresh: restoreSession,
      expired: () => {
        becomeAnonymous();
        const currentPath = typeof window === "undefined" ? "" : window.location.pathname;
        const next =
          currentPath && currentPath !== "/login"
            ? `?next=${encodeURIComponent(currentPath)}`
            : "";
        router.replace(`/login${next}`);
      },
    });
    const timer = window.setTimeout(() => void restoreSession(), 0);
    return () => {
      window.clearTimeout(timer);
      unregister();
    };
  }, [becomeAnonymous, restoreSession, router]);

  const login = useCallback(async (request: LoginRequest) => {
    const result = await api.login(request);
    setAccessToken(result.access_token);
    setUser(result.user);
    setStatus("authenticated");
    return result.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      becomeAnonymous();
      router.replace("/login");
    }
  }, [becomeAnonymous, router]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      login,
      logout,
      can: (permission) => Boolean(user?.permissions.includes(permission)),
    }),
    [login, logout, status, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function AuthenticatedApplication({ children }: { children: React.ReactNode }) {
  const auth = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const requiredPermission = permissionForPath(pathname);
  const isLogin = pathname === "/login";
  const denied =
    auth.status === "authenticated" &&
    requiredPermission !== null &&
    !auth.can(requiredPermission);

  useEffect(() => {
    if (auth.status === "anonymous" && !isLogin) {
      const next = pathname ? `?next=${encodeURIComponent(pathname)}` : "";
      router.replace(`/login${next}`);
    }
  }, [auth.status, isLogin, pathname, router]);

  useEffect(() => {
    if (denied && pathname !== "/forbidden") router.replace("/forbidden");
  }, [denied, pathname, router]);

  if (auth.status === "restoring") return <SessionLoading />;
  if (isLogin) return <TooltipProvider>{children}</TooltipProvider>;
  if (auth.status === "anonymous") return <SessionLoading />;
  if (denied && pathname !== "/forbidden") return <SessionLoading />;

  return (
    <CopilotStatusProvider>
      <TooltipProvider>
        <AppShell>{children}</AppShell>
      </TooltipProvider>
    </CopilotStatusProvider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

export function AuthTestProvider({
  children,
  user,
}: {
  children: React.ReactNode;
  user: UserResponse;
}) {
  const value = useMemo<AuthContextValue>(
    () => ({
      status: "authenticated",
      user,
      login: async () => user,
      logout: async () => undefined,
      can: (permission) => user.permissions.includes(permission),
    }),
    [user],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function defaultRouteFor(user: UserResponse) {
  if (user.permissions.includes(permissions.analyticsRead)) return "/";
  if (user.permissions.includes(permissions.inventoryRead)) return "/inventory";
  if (user.permissions.includes(permissions.workOrdersRead)) return "/work-orders";
  if (user.permissions.includes(permissions.ticketsRead)) return "/tickets";
  if (user.permissions.includes(permissions.assetsRead)) return "/assets";
  if (user.permissions.includes(permissions.copilotUse)) return "/copilot";
  return "/forbidden";
}

function permissionForPath(pathname: string | null): Permission | null {
  if (!pathname || pathname === "/login" || pathname === "/forbidden") return null;
  if (pathname.startsWith("/admin/sla")) return permissions.slaPoliciesRead;
  if (pathname.startsWith("/admin/escalations")) return permissions.escalationsEvaluate;
  if (pathname.startsWith("/admin/users")) return permissions.usersRead;
  if (pathname.startsWith("/admin/audit")) return permissions.auditLogsRead;
  if (pathname.startsWith("/scan/assets")) return permissions.assetsRead;
  if (pathname.startsWith("/assets")) return permissions.assetsRead;
  if (pathname.startsWith("/tickets")) return permissions.ticketsRead;
  if (pathname.startsWith("/maintenance/plans")) return permissions.maintenancePlansRead;
  if (pathname.startsWith("/maintenance/checklists")) return permissions.checklistTemplatesRead;
  if (pathname.startsWith("/work-orders")) return permissions.workOrdersRead;
  if (pathname.startsWith("/inventory")) return permissions.inventoryRead;
  if (pathname.startsWith("/anomalies") || pathname === "/") {
    return permissions.analyticsRead;
  }
  if (pathname.startsWith("/copilot")) return permissions.copilotUse;
  return null;
}

function SessionLoading() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="text-center text-sm text-muted-foreground">
        <Loader2 className="mx-auto mb-3 size-6 animate-spin" aria-hidden="true" />
        Đang kiểm tra phiên đăng nhập
      </div>
    </main>
  );
}

export function PermissionDeniedNotice({ message }: { message: string }) {
  return (
    <div className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">
      <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}

export function LogoutButton() {
  const { logout } = useAuth();
  return (
    <Button type="button" variant="ghost" size="sm" onClick={() => void logout()}>
      Đăng xuất
    </Button>
  );
}
