"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { permissions, type Permission } from "@/lib/auth";
import { cn } from "@/lib/utils";

const primarySections = [
  { href: "/inventory", label: "Tổng quan", exact: true },
  { href: "/inventory/parts", label: "Phụ tùng" },
  { href: "/inventory/stock", label: "Tồn kho" },
  { href: "/inventory/low-stock", label: "Sắp hết" },
  { href: "/inventory/reservations", label: "Đặt trước" },
  { href: "/inventory/movements", label: "Lịch sử" },
];

const operationSections: Array<{ href: string; label: string; permission: Permission }> = [
  { href: "/inventory/receiving", label: "Nhập kho", permission: permissions.inventoryReceive },
  { href: "/inventory/transfers", label: "Điều chuyển", permission: permissions.inventoryTransfer },
  { href: "/inventory/adjustments", label: "Điều chỉnh", permission: permissions.inventoryAdjust },
  { href: "/inventory/settings", label: "Thiết lập kho", permission: permissions.inventoryLocationsManage },
];

export function InventorySectionNav() {
  const pathname = usePathname();
  const auth = useAuth();
  const operations = operationSections.filter((section) => auth.can(section.permission));
  const operationActive = operations.some((section) => pathname?.startsWith(section.href));
  return (
    <nav
      aria-label="Điều hướng kho vật tư"
      className="mb-5 border-b"
    >
      <div className="flex flex-wrap items-center gap-1">
        {primarySections.map((section) => {
          const active = section.exact
            ? pathname === section.href
            : pathname?.startsWith(section.href);
          return (
            <Link
              key={section.href}
              href={section.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex min-h-11 items-center border-b-2 px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                active
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {section.label}
            </Link>
          );
        })}
        {operations.length > 0 && (
          <details className="group relative">
            <summary className={cn(
              "flex min-h-11 cursor-pointer list-none items-center border-b-2 px-3 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              operationActive ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground",
            )}>
              Nghiệp vụ kho
            </summary>
            <div className="absolute right-0 z-20 mt-1 grid min-w-48 gap-1 rounded-lg border bg-white p-2 shadow-lg">
              {operations.map((section) => (
                <Link
                  key={section.href}
                  href={section.href}
                  aria-current={pathname?.startsWith(section.href) ? "page" : undefined}
                  className="flex min-h-11 items-center rounded-md px-3 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {section.label}
                </Link>
              ))}
            </div>
          </details>
        )}
      </div>
    </nav>
  );
}
