"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  Bot,
  CalendarClock,
  ChevronDown,
  ClipboardList,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  PackageOpen,
  Plus,
  ScrollText,
  Search,
  ServerCog,
  ShieldAlert,
  TicketCheck,
  UserRound,
  Users,
  Wrench,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { defaultRouteFor, useAuth } from "@/components/auth-provider";
import { NotificationCenter } from "@/components/notification-center";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import type { UserResponse } from "@/lib/api/schemas";
import { permissions, type Permission } from "@/lib/auth";
import { cn } from "@/lib/utils";

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  permission: Permission;
}

interface NavSection {
  label: string;
  items: NavItem[];
  collapsible?: boolean;
}

interface QuickAction {
  label: string;
  href: string;
  permission: Permission;
}

const primaryNavigation: NavItem[] = [
  { label: "Tổng quan", href: "/", icon: LayoutDashboard, permission: permissions.analyticsRead },
  { label: "Thiết bị", href: "/assets", icon: Wrench, permission: permissions.assetsRead },
  { label: "Sự cố", href: "/tickets", icon: TicketCheck, permission: permissions.ticketsRead },
  { label: "Lệnh công việc", href: "/work-orders", icon: ClipboardList, permission: permissions.workOrdersRead },
  { label: "Bảo trì định kỳ", href: "/maintenance/plans", icon: CalendarClock, permission: permissions.maintenancePlansRead },
  { label: "Kho phụ tùng", href: "/inventory", icon: PackageOpen, permission: permissions.inventoryRead },
  { label: "Trợ lý bảo trì", href: "/copilot", icon: Bot, permission: permissions.copilotUse },
  { label: "Bất thường", href: "/anomalies", icon: Activity, permission: permissions.analyticsRead },
];

const administrationNavigation: NavItem[] = [
  { label: "Mẫu kiểm tra", href: "/maintenance/checklists", icon: ListChecks, permission: permissions.checklistTemplatesRead },
  { label: "Thiết lập SLA", href: "/admin/sla", icon: CalendarClock, permission: permissions.slaPoliciesRead },
  { label: "Cảnh báo SLA", href: "/admin/escalations", icon: ShieldAlert, permission: permissions.escalationsEvaluate },
  { label: "Người dùng & quyền", href: "/admin/users", icon: Users, permission: permissions.usersRead },
  { label: "Nhật ký hệ thống", href: "/admin/audit", icon: ScrollText, permission: permissions.auditLogsRead },
  { label: "Tác vụ hệ thống", href: "/admin/jobs", icon: ServerCog, permission: permissions.jobOperationsRead },
];

const quickActionNavigation: QuickAction[] = [
  { label: "Báo sự cố", href: "/tickets/new", permission: permissions.ticketsCreate },
  { label: "Tạo kế hoạch bảo trì", href: "/maintenance/plans/new", permission: permissions.maintenancePlansCreate },
  { label: "Ghi nhận nhập kho", href: "/inventory/receiving", permission: permissions.inventoryReceive },
];

const roleRouteOrder: Partial<Record<UserResponse["role"], readonly string[]>> = {
  technician: ["/work-orders", "/assets", "/tickets", "/copilot", "/maintenance/checklists"],
  storekeeper: ["/inventory", "/work-orders", "/assets", "/tickets"],
  helpdesk: ["/tickets", "/assets", "/work-orders"],
};

export function isActivePath(pathname: string | null, href: string) {
  if (!pathname) return href === "/";
  return href === "/"
    ? pathname === "/"
    : pathname === href || pathname.startsWith(`${href}/`);
}

export function quickActionsForPermissions(
  currentPermissions: readonly string[],
): Array<{ label: string; href: string }> {
  const allowed = new Set(currentPermissions);
  return quickActionNavigation
    .filter((action) => allowed.has(action.permission))
    .map(({ label, href }) => ({ label, href }));
}

export function navigationForRole(
  role: UserResponse["role"],
  currentPermissions: readonly string[],
): Array<{ label: string; items: Array<{ label: string; href: string }> }> {
  const allowed = new Set(currentPermissions);
  return navigationSections(role, (permission) => allowed.has(permission)).map((section) => ({
    label: section.label,
    items: section.items.map(({ label, href }) => ({ label, href })),
  }));
}

function navigationSections(
  role: UserResponse["role"],
  can: (permission: Permission) => boolean,
): NavSection[] {
  const sections = [
    { label: "Công việc", items: orderForRole(primaryNavigation.filter((item) => can(item.permission)), role) },
    {
      label: "Thiết lập & quản trị",
      items: administrationNavigation.filter((item) => can(item.permission)),
      collapsible: true,
    },
  ];
  return sections.filter((section) => section.items.length > 0);
}

function orderForRole(items: NavItem[], role: UserResponse["role"]): NavItem[] {
  const preferred = roleRouteOrder[role];
  if (!preferred) return items;
  const rank = new Map(preferred.map((href, index) => [href, index]));
  return items.toSorted(
    (left, right) =>
      (rank.get(left.href) ?? Number.MAX_SAFE_INTEGER) -
      (rank.get(right.href) ?? Number.MAX_SAFE_INTEGER),
  );
}

function Brand({ mobile = false }: { mobile?: boolean }) {
  const { user } = useAuth();
  const link = (
    <Link
      href={user ? defaultRouteFor(user) : "/"}
      className="flex items-center gap-3 rounded-lg text-sidebar-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
    >
      <span className="flex size-10 items-center justify-center rounded-lg bg-blue-500 text-white shadow-sm shadow-blue-950/20">
        <Wrench className="size-5" aria-hidden="true" />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold tracking-tight text-white">Bảo trì thiết bị</span>
        <span className="block truncate text-xs text-sidebar-foreground/65">Maintenance Copilot</span>
      </span>
    </Link>
  );
  return mobile ? <SheetClose asChild>{link}</SheetClose> : link;
}

function QuickActions({ mobile = false }: { mobile?: boolean }) {
  const { user } = useAuth();
  const actions = quickActionsForPermissions(user?.permissions ?? []);
  if (!actions.length) return null;

  return (
    <details className="group relative">
      <summary className="flex min-h-10 cursor-pointer list-none items-center justify-between rounded-lg bg-blue-500 px-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-blue-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring [&::-webkit-details-marker]:hidden">
        <span className="flex items-center gap-2">
          <Plus className="size-4" aria-hidden="true" />
          Thêm nhanh
        </span>
        <ChevronDown className="size-4 transition-transform group-open:rotate-180" aria-hidden="true" />
      </summary>
      <div
        className={cn(
          "z-50 mt-2 space-y-1 rounded-lg border border-sidebar-border bg-sidebar p-1.5 shadow-xl shadow-slate-950/25",
          !mobile && "absolute left-0 right-0 top-full",
        )}
      >
        {actions.map((action) => {
          const link = (
            <Link
              href={action.href}
              className="flex min-h-9 items-center rounded-md px-2.5 text-sm text-sidebar-foreground/80 transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
            >
              {action.label}
            </Link>
          );
          return mobile ? (
            <SheetClose asChild key={action.href}>{link}</SheetClose>
          ) : (
            <div key={action.href}>{link}</div>
          );
        })}
      </div>
    </details>
  );
}

function GlobalNavigationSearch() {
  const auth = useAuth();
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const destinations = auth.user
    ? navigationForRole(auth.user.role, auth.user.permissions).flatMap((section) =>
        section.items.map((item) => ({ ...item, section: section.label })),
      )
    : [];
  const normalizedQuery = normalizeSearchText(query.trim());
  const results = normalizedQuery
    ? destinations.filter((item) =>
        normalizeSearchText(`${item.label} ${item.section}`).includes(normalizedQuery),
      ).slice(0, 6)
    : [];

  useEffect(() => {
    function focusSearch(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, []);

  function openFirstResult(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const first = results[0];
    if (!first) return;
    setQuery("");
    router.push(first.href);
  }

  return (
    <form className="group relative w-full max-w-xl" onSubmit={openFirstResult} role="search">
      <Search className="pointer-events-none absolute left-3 top-1/2 z-10 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
      <Input
        ref={inputRef}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            setQuery("");
            event.currentTarget.blur();
          }
        }}
        aria-label="Tìm nhanh chức năng"
        autoComplete="off"
        placeholder="Tìm nhanh chức năng..."
        className="h-9 border-slate-200 bg-slate-50 pl-9 pr-14 shadow-none focus-visible:bg-white"
      />
      <kbd className="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded border bg-white px-1.5 py-0.5 font-sans text-[10px] text-slate-500 lg:block">
        Ctrl K
      </kbd>
      {query.trim() && (
        <div className="absolute left-0 right-0 top-full z-50 mt-2 overflow-hidden rounded-lg border bg-popover p-1.5 text-popover-foreground shadow-xl">
          {results.length ? results.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setQuery("")}
              className="flex min-h-10 items-center justify-between gap-3 rounded-md px-3 text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span className="font-medium">{item.label}</span>
              <span className="text-xs text-muted-foreground">{item.section}</span>
            </Link>
          )) : (
            <p className="px-3 py-4 text-sm text-muted-foreground">Không có chức năng phù hợp với quyền hiện tại.</p>
          )}
        </div>
      )}
    </form>
  );
}

function normalizeSearchText(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLocaleLowerCase("vi");
}

function Navigation({ mobile = false }: { mobile?: boolean }) {
  const pathname = usePathname();
  const { can, user } = useAuth();
  if (!user) return null;

  return (
    <nav aria-label="Điều hướng chính" className="space-y-5 text-sidebar-foreground">
      {navigationSections(user.role, can).map((section) => {
        const links = (
          <div className="space-y-1">
            {section.items.map((item) => {
              const Icon = item.icon;
              const active = isActivePath(pathname, item.href);
              const link = (
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex min-h-11 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring",
                    active
                      ? "bg-sidebar-accent font-semibold text-sidebar-accent-foreground shadow-sm"
                      : "text-sidebar-foreground/70 hover:bg-white/8 hover:text-white",
                  )}
                >
                  <Icon className="size-4 shrink-0" aria-hidden="true" />
                  <span>{item.label}</span>
                </Link>
              );

              return mobile ? (
                <SheetClose asChild key={item.href}>
                  {link}
                </SheetClose>
              ) : (
                <div key={item.href}>{link}</div>
              );
            })}
          </div>
        );
        if (section.collapsible) {
          const hasActiveItem = section.items.some((item) =>
            isActivePath(pathname, item.href),
          );
          return (
            <details
              key={section.label}
              className="group"
              open={hasActiveItem || undefined}
            >
              <summary className="flex min-h-10 cursor-pointer list-none items-center justify-between rounded-md px-3 text-[11px] font-semibold uppercase tracking-wider text-sidebar-foreground/55 hover:bg-white/8 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring [&::-webkit-details-marker]:hidden">
                {section.label}
                <ChevronDown
                  className="size-3.5 transition-transform group-open:rotate-180"
                  aria-hidden="true"
                />
              </summary>
              <div className="mt-1">{links}</div>
            </details>
          );
        }
        return (
          <div key={section.label} role="group" aria-label={section.label}>
            <p className="mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-wider text-sidebar-foreground/55">
              {section.label}
            </p>
            {links}
          </div>
        );
      })}
    </nav>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const auth = useAuth();

  return (
    <div className="min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 border-r border-sidebar-border bg-sidebar lg:flex lg:flex-col">
        <div className="border-b border-sidebar-border px-5 py-4">
          <Brand />
        </div>
        <div className="border-b border-sidebar-border px-3 py-3">
          <QuickActions />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-5">
          <Navigation />
        </div>
        <div className="border-t border-sidebar-border p-4 text-sidebar-foreground">
          <p className="text-xs font-semibold text-white">Hỗ trợ quyết định</p>
          <p className="mt-1 text-xs leading-5 text-sidebar-foreground/60">
            Hỗ trợ ưu tiên, không thay thế quyết định kỹ thuật.
          </p>
          {auth.user && (
            <div className="mt-4 border-t border-sidebar-border pt-3">
              <p className="truncate text-xs font-semibold text-white">{auth.user.display_name}</p>
              <p className="mt-0.5 truncate text-xs text-sidebar-foreground/60">
                {auth.user.role_display_name}
              </p>
            </div>
          )}
        </div>
      </aside>

      <div className="lg:pl-60">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-3 border-b bg-white/95 px-4 shadow-[0_1px_3px_rgba(15,23,42,0.04)] backdrop-blur-sm sm:px-6 lg:px-8">
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="outline" size="icon" className="lg:hidden" aria-label="Mở menu">
                  <Menu aria-hidden="true" />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="w-[288px] gap-0 border-sidebar-border bg-sidebar p-0 text-sidebar-foreground sm:max-w-[288px]">
                <SheetHeader className="border-b border-sidebar-border px-5 py-4 text-left">
                  <SheetTitle className="sr-only">Điều hướng chính</SheetTitle>
                  <SheetDescription className="sr-only">
                    Chọn khu vực công việc phù hợp với vai trò của bạn.
                  </SheetDescription>
                  <Brand mobile />
                </SheetHeader>
                <div className="border-b border-sidebar-border px-3 py-3">
                  <QuickActions mobile />
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
                  <Navigation mobile />
                </div>
                {auth.user && (
                  <div className="border-t border-sidebar-border p-4">
                    <p className="truncate text-sm font-semibold text-white">{auth.user.display_name}</p>
                    <p className="mt-0.5 truncate text-xs text-sidebar-foreground/60">
                      {auth.user.role_display_name}
                    </p>
                    <SheetClose asChild>
                      <Button
                        type="button"
                        variant="outline"
                        className="mt-3 w-full justify-start border-white/15 bg-white/5 text-white hover:bg-white/10 hover:text-white"
                        onClick={() => void auth.logout()}
                      >
                        <LogOut aria-hidden="true" />
                        Đăng xuất
                      </Button>
                    </SheetClose>
                  </div>
                )}
              </SheetContent>
            </Sheet>
            <div className="sm:hidden">
              <p className="text-sm font-semibold text-foreground">Công việc của bạn</p>
              {auth.user && (
                <p className="hidden text-xs text-muted-foreground sm:block">
                  {auth.user.role_display_name}
                </p>
              )}
            </div>
            <div className="hidden min-w-0 flex-1 sm:block">
              <GlobalNavigationSearch />
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
            <NotificationCenter />
            {auth.user && (
              <div className="hidden items-center gap-2 rounded-lg border bg-white px-2 py-1 text-sm shadow-sm md:flex">
                <span className="flex size-7 items-center justify-center rounded-full bg-blue-100 text-blue-700">
                  <UserRound className="size-3.5" aria-hidden="true" />
                </span>
                <span className="min-w-0">
                  <span className="block max-w-40 truncate text-xs font-semibold">{auth.user.display_name}</span>
                  <span className="block max-w-40 truncate text-[10px] text-muted-foreground">{auth.user.role_display_name}</span>
                </span>
              </div>
            )}
            <Button
              type="button"
              variant="ghost"
              size="icon"
              title="Đăng xuất"
              aria-label="Đăng xuất"
              onClick={() => void auth.logout()}
            >
              <LogOut aria-hidden="true" />
            </Button>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1600px] px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
          {children}
        </main>
      </div>
    </div>
  );
}
