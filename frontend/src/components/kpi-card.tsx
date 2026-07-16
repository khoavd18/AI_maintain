import type { LucideIcon } from "lucide-react";

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

interface KpiCardProps {
  label: string;
  value: string;
  detail: string;
  icon: LucideIcon;
  tone?: keyof typeof toneClasses;
}

export function KpiCard({ label, value, detail, icon: Icon, tone = "neutral" }: KpiCardProps) {
  return (
    <Card size="sm" className="shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
      <CardContent className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-xs font-medium text-muted-foreground">{label}</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums text-foreground">{value}</p>
          <p className="mt-1 truncate text-xs text-muted-foreground">{detail}</p>
        </div>
        <span className={cn("flex size-9 shrink-0 items-center justify-center rounded-lg", toneClasses[tone])}>
          <Icon className="size-4" aria-hidden="true" />
        </span>
      </CardContent>
    </Card>
  );
}
