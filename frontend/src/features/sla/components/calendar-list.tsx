"use client";

import { CalendarDays, Pencil, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { BusinessCalendar } from "@/lib/api/ticketing-schemas";

export function CalendarList({
  calendars,
  canManage,
  onNew,
  onEdit,
}: {
  calendars: BusinessCalendar[];
  canManage: boolean;
  onNew: () => void;
  onEdit: (calendar: BusinessCalendar) => void;
}) {
  return (
    <section className="rounded-lg border bg-white">
      <header className="flex items-center justify-between gap-3 border-b p-4">
        <div>
          <h2 className="text-sm font-semibold">Business calendars</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Giờ làm việc theo timezone IANA và ngày nghỉ địa phương.
          </p>
        </div>
        {canManage && (
          <Button type="button" variant="outline" size="sm" onClick={onNew}>
            <Plus aria-hidden="true" />
            Calendar mới
          </Button>
        )}
      </header>
      <div className="divide-y">
        {calendars.map((calendar) => (
          <article key={calendar.id} className="flex flex-col justify-between gap-3 p-4 sm:flex-row sm:items-start">
            <div>
              <div className="flex items-center gap-2">
                <CalendarDays className="size-4 text-primary" aria-hidden="true" />
                <p className="font-mono text-xs font-semibold text-primary">{calendar.code}</p>
              </div>
              <p className="mt-2 text-sm font-semibold">{calendar.name}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {calendar.timezone} · {calendar.periods.length} khung giờ · {calendar.holidays.length} ngày nghỉ
              </p>
            </div>
            {canManage && (
              <Button type="button" variant="ghost" size="sm" onClick={() => onEdit(calendar)}>
                <Pencil aria-hidden="true" />
                Sửa
              </Button>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
