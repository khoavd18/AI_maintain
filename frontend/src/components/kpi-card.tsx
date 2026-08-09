import type { LucideIcon } from "lucide-react";
import Link from "next/link";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const toneClasses = {
  blue: "bg-blue-50 text-blue-700",
  green: "bg-green-50 text-green-700",
  amber: "bg-amber-50 text-amber-700",
  orange: "bg-orange-50 text-orange-700",
  red: "bg-red-50 text-red-700",
  neutral: "bg-neutral-100 text-neutral-700",
};

const toneBorderClasses = {
  blue: "border-t-blue-500",
  green: "border-t-green-500",
  amber: "border-t-amber-500",
  orange: "border-t-orange-500",
  red: "border-t-red-500",
  neutral: "border-t-slate-300",
};

interface KpiCardProps {
  label: string;
  value: string;
  detail: string;
  icon: LucideIcon;
  tone?: keyof typeof toneClasses;
  href?: string;
}

export function KpiCard({ label, value, detail, icon: Icon, tone = "neutral", href }: KpiCardProps) {
  const card = (
    <Card
      size="sm"
      className={cn(
        "h-full border-t-2 shadow-[0_3px_12px_rgba(15,23,42,0.04)] transition-shadow group-hover/card:shadow-[0_6px_18px_rgba(15,23,42,0.08)]",
        toneBorderClasses[tone],
      )}
    >
      <CardContent className="flex min-h-28 items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="line-clamp-2 min-h-8 text-xs font-medium leading-4 text-muted-foreground">{label}</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums text-foreground">{value}</p>
          <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{detail}</p>
        </div>
        <span className={cn("flex size-9 shrink-0 items-center justify-center rounded-lg", toneClasses[tone])}>
          <Icon className="size-4" aria-hidden="true" />
        </span>
      </CardContent>
    </Card>
  );
  return href ? (
    <Link
      href={href}
      aria-label={`${label}: ${value}. ${detail}`}
      className="block rounded-xl transition-transform hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {card}
    </Link>
  ) : card;
}
