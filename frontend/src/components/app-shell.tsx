"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  Bot,
  LayoutDashboard,
  Menu,
  PanelLeftClose,
  TicketCheck,
  Wrench,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { useHealthQuery, useSummaryQuery } from "@/hooks/use-api-queries";
import { formatDate } from "@/lib/formatters";
import { cn } from "@/lib/utils";

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

const navigation: NavItem[] = [
  { label: "Tổng quan", href: "/", icon: LayoutDashboard },
  { label: "Thiết bị", href: "/assets", icon: Wrench },
  { label: "Ticket", href: "/tickets", icon: TicketCheck },
  { label: "Bất thường", href: "/anomalies", icon: Activity },
  { label: "Trợ lý bảo trì", href: "/copilot", icon: Bot },
];

function isActivePath(pathname: string | null, href: string) {
  if (!pathname) return href === "/";
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

function Brand() {
  return (
    <Link
      href="/"
      className="flex items-center gap-3 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
        <PanelLeftClose className="size-4" aria-hidden="true" />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold">AI Maintenance</span>
        <span className="block truncate text-xs text-muted-foreground">Decision Support</span>
      </span>
    </Link>
  );
}

function Navigation({ mobile = false }: { mobile?: boolean }) {
  const pathname = usePathname();

  return (
    <nav aria-label="Điều hướng chính" className="space-y-1">
      {navigation.map((item) => {
        const Icon = item.icon;
        const active = isActivePath(pathname, item.href);
        const link = (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex min-h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            <Icon className="size-4" aria-hidden="true" />
            <span>{item.label}</span>
          </Link>
        );

        return mobile ? (
          <SheetClose asChild key={item.href}>
            {link}
          </SheetClose>
        ) : (
          link
        );
      })}
    </nav>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const health = useHealthQuery();
  const summary = useSummaryQuery();

  return (
    <div className="min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r bg-sidebar lg:flex lg:flex-col">
        <div className="border-b px-5 py-4">
          <Brand />
        </div>
        <div className="flex-1 px-3 py-5">
          <Navigation />
        </div>
        <div className="border-t p-4">
          <p className="text-xs font-medium text-foreground">MVP dữ liệu batch</p>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            Hỗ trợ ưu tiên, không thay thế quyết định kỹ thuật.
          </p>
        </div>
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b bg-white/95 px-4 backdrop-blur-sm sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="outline" size="icon" className="lg:hidden" aria-label="Mở menu">
                  <Menu aria-hidden="true" />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="w-[280px] p-0 sm:max-w-[280px]">
                <SheetHeader className="border-b px-5 py-4 text-left">
                  <SheetTitle className="sr-only">Điều hướng</SheetTitle>
                  <SheetDescription className="sr-only">
                    Chọn một trang trong ứng dụng.
                  </SheetDescription>
                  <Brand />
                </SheetHeader>
                <div className="p-3">
                  <Navigation mobile />
                </div>
              </SheetContent>
            </Sheet>
            <div>
              <p className="text-sm font-semibold text-foreground">Trung tâm vận hành</p>
              <p className="hidden text-xs text-muted-foreground sm:block">
                Cập nhật batch: {summary.data ? formatDate(summary.data.latest_date) : summary.isPending ? "đang tải" : "chưa khả dụng"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <ApiStatusBadge health={health} />
            <Badge
              variant="outline"
              className="hidden bg-white text-muted-foreground xl:inline-flex"
              title="Copilot chưa kết nối RAG trong frontend milestone này"
            >
              RAG: chưa kết nối
            </Badge>
            <Badge className="bg-blue-50 text-blue-700 ring-1 ring-blue-200 hover:bg-blue-50">
              Dữ liệu synthetic
            </Badge>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}

function ApiStatusBadge({ health }: { health: ReturnType<typeof useHealthQuery> }) {
  if (health.isPending) {
    return (
      <Badge variant="outline" className="hidden gap-1.5 bg-white text-muted-foreground sm:inline-flex">
        <span className="size-1.5 animate-pulse rounded-full bg-neutral-400" aria-hidden="true" />
        API: đang kết nối
      </Badge>
    );
  }

  if (health.isError) {
    return (
      <Badge
        variant="outline"
        className="hidden gap-1.5 border-red-200 bg-red-50 text-red-700 sm:inline-flex"
        title="Không thể kết nối tới FastAPI"
      >
        <span className="size-1.5 rounded-full bg-red-600" aria-hidden="true" />
        API: ngoại tuyến
      </Badge>
    );
  }

  const partial =
    health.data.status === "degraded" ||
    health.data.analytics_available === false ||
    health.data.raw_data_available === false;
  return (
    <Badge
      variant="outline"
      className={cn(
        "hidden gap-1.5 sm:inline-flex",
        partial
          ? "border-amber-200 bg-amber-50 text-amber-700"
          : "border-green-200 bg-green-50 text-green-700",
      )}
    >
      <span
        className={cn("size-1.5 rounded-full", partial ? "bg-amber-500" : "bg-green-600")}
        aria-hidden="true"
      />
      {partial ? "API: analytics chưa đủ" : "API: đã kết nối"}
    </Badge>
  );
}
