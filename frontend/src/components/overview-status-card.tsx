import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

export interface OverviewStatusSegment {
  label: string;
  value: number;
  color: string;
}

interface OverviewStatusCardProps {
  title: string;
  description: string;
  href: string;
  segments: OverviewStatusSegment[];
}

export function OverviewStatusCard({
  title,
  description,
  href,
  segments,
}: OverviewStatusCardProps) {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0);
  const chartLabel = segments
    .map((segment) => `${segment.label}: ${segment.value}`)
    .join(", ");

  return (
    <section className="rounded-xl border bg-white p-4 shadow-[0_4px_16px_rgba(15,23,42,0.04)]">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
        </div>
        <Link
          href={href}
          className="flex size-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-blue-50 hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={`Mở ${title.toLocaleLowerCase("vi")}`}
        >
          <ArrowUpRight className="size-4" aria-hidden="true" />
        </Link>
      </header>

      <div className="mt-4 flex items-center gap-5">
        <div
          className="relative flex size-24 shrink-0 items-center justify-center rounded-full"
          style={{ background: donutBackground(segments) }}
          role="img"
          aria-label={`${title}. Tổng ${total}. ${chartLabel}`}
        >
          <span className="flex size-16 flex-col items-center justify-center rounded-full bg-white shadow-[inset_0_0_0_1px_rgba(148,163,184,0.18)]">
            <span className="text-xl font-semibold tabular-nums text-slate-900">{total}</span>
            <span className="text-[10px] uppercase tracking-wide text-slate-400">Tổng</span>
          </span>
        </div>

        <ul className="min-w-0 flex-1 space-y-2">
          {segments.map((segment) => (
            <li key={segment.label} className="flex items-center justify-between gap-3 text-xs">
              <span className="flex min-w-0 items-center gap-2 text-slate-600">
                <span
                  className="size-2 shrink-0 rounded-full"
                  style={{ backgroundColor: segment.color }}
                  aria-hidden="true"
                />
                <span className="truncate">{segment.label}</span>
              </span>
              <span className="font-semibold tabular-nums text-slate-900">{segment.value}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function donutBackground(segments: OverviewStatusSegment[]) {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0);
  if (total === 0) return "conic-gradient(#e2e8f0 0 100%)";

  let cursor = 0;
  const stops = segments.map((segment) => {
    const start = cursor;
    cursor += (segment.value / total) * 100;
    return `${segment.color} ${start}% ${cursor}%`;
  });
  return `conic-gradient(${stops.join(", ")})`;
}
