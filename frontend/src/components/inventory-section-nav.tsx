"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const sections = [
  { href: "/inventory", label: "Tổng quan", exact: true },
  { href: "/inventory/parts", label: "Danh mục vật tư" },
  { href: "/inventory/stock", label: "Tồn theo kho" },
  { href: "/inventory/low-stock", label: "Tồn thấp" },
  { href: "/inventory/movements", label: "Biến động kho" },
  { href: "/inventory/reservations", label: "Giữ vật tư" },
  { href: "/inventory/receiving", label: "Nhập kho" },
  { href: "/inventory/transfers", label: "Chuyển kho" },
  { href: "/inventory/adjustments", label: "Điều chỉnh" },
  { href: "/inventory/settings", label: "Thiết lập" },
];

export function InventorySectionNav() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Điều hướng kho vật tư"
      className="mb-5 overflow-x-auto border-b"
    >
      <div className="flex min-w-max gap-1">
        {sections.map((section) => {
          const active = section.exact
            ? pathname === section.href
            : pathname?.startsWith(section.href);
          return (
            <Link
              key={section.href}
              href={section.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "border-b-2 px-3 py-2.5 text-sm font-medium transition-colors",
                active
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {section.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
