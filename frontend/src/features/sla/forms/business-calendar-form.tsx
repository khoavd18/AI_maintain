"use client";

import { type FormEvent, useState } from "react";

import { Loader2, Plus, Save, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useCreateBusinessCalendarMutation,
  useUpdateBusinessCalendarMutation,
} from "@/hooks/use-ticketing";
import {
  businessCalendarRequestSchema,
  type BusinessCalendar,
  type BusinessCalendarRequest,
} from "@/lib/api/ticketing-schemas";
import { zodFieldErrors } from "@/lib/workflow";

import { CheckboxField, FormInput, MutationError } from "../components/form-controls";

const weekdayLabels = [
  "Thứ Hai",
  "Thứ Ba",
  "Thứ Tư",
  "Thứ Năm",
  "Thứ Sáu",
  "Thứ Bảy",
  "Chủ Nhật",
];

export function BusinessCalendarForm({
  initial,
  onSaved,
}: {
  initial: BusinessCalendar | null;
  onSaved: () => void;
}) {
  const create = useCreateBusinessCalendarMutation();
  const update = useUpdateBusinessCalendarMutation(initial?.id ?? "");
  const mutation = initial ? update : create;
  const [form, setForm] = useState<BusinessCalendarRequest>(
    initial
      ? {
          code: initial.code,
          name: initial.name,
          timezone: initial.timezone,
          is_active: initial.is_active,
          periods: initial.periods,
          holidays: initial.holidays,
        }
      : {
          code: "",
          name: "",
          timezone: "Asia/Ho_Chi_Minh",
          is_active: true,
          periods: [0, 1, 2, 3, 4].map((weekday) => ({
            weekday,
            start_time: "08:00:00",
            end_time: "17:00:00",
          })),
          holidays: [],
        },
  );
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = businessCalendarRequestSchema.safeParse(form);
    if (!parsed.success) {
      setErrors(zodFieldErrors(parsed.error.issues));
      return;
    }
    setErrors({});
    try {
      if (initial) {
        await update.mutateAsync({ ...parsed.data, expected_version: initial.version });
      } else {
        await create.mutateAsync(parsed.data);
      }
      onSaved();
    } catch {
      // Safe mutation error rendered below.
    }
  }

  return (
    <form onSubmit={submit} className="h-fit rounded-lg border bg-white p-4">
      <h2 className="text-sm font-semibold">{initial ? `Sửa ${initial.code}` : "Tạo business calendar"}</h2>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <FormInput id="calendar-code" label="Code" value={form.code} disabled={Boolean(initial)} error={errors.code} onChange={(code) => setForm({ ...form, code: code.toUpperCase() })} />
        <FormInput id="calendar-name" label="Tên" value={form.name} error={errors.name} onChange={(name) => setForm({ ...form, name })} />
      </div>
      <div className="mt-3">
        <FormInput id="calendar-timezone" label="IANA timezone" value={form.timezone} error={errors.timezone} onChange={(timezone) => setForm({ ...form, timezone })} />
      </div>

      <div className="mt-4">
        <div className="flex items-center justify-between gap-2">
          <Label>Khung giờ làm việc</Label>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() =>
              setForm({
                ...form,
                periods: [...form.periods, { weekday: 0, start_time: "08:00:00", end_time: "17:00:00" }],
              })
            }
          >
            <Plus aria-hidden="true" />
            Thêm
          </Button>
        </div>
        <div className="mt-2 space-y-2">
          {form.periods.map((period, index) => (
            <div key={`${period.weekday}-${index}`} className="grid grid-cols-[minmax(0,1fr)_105px_105px_36px] gap-2">
              <Select
                value={String(period.weekday)}
                onValueChange={(weekday) =>
                  setForm({ ...form, periods: form.periods.map((item, itemIndex) => itemIndex === index ? { ...item, weekday: Number(weekday) } : item) })
                }
              >
                <SelectTrigger aria-label={`Ngày làm việc ${index + 1}`}><SelectValue /></SelectTrigger>
                <SelectContent>
                  {weekdayLabels.map((label, weekday) => <SelectItem key={label} value={String(weekday)}>{label}</SelectItem>)}
                </SelectContent>
              </Select>
              <Input type="time" aria-label={`Bắt đầu ${index + 1}`} value={period.start_time.slice(0, 5)} onChange={(event) => setForm({ ...form, periods: form.periods.map((item, itemIndex) => itemIndex === index ? { ...item, start_time: `${event.target.value}:00` } : item) })} />
              <Input type="time" aria-label={`Kết thúc ${index + 1}`} value={period.end_time.slice(0, 5)} onChange={(event) => setForm({ ...form, periods: form.periods.map((item, itemIndex) => itemIndex === index ? { ...item, end_time: `${event.target.value}:00` } : item) })} />
              <Button type="button" variant="ghost" size="icon" aria-label={`Xóa khung giờ ${index + 1}`} onClick={() => setForm({ ...form, periods: form.periods.filter((_, itemIndex) => itemIndex !== index) })}>
                <Trash2 aria-hidden="true" />
              </Button>
            </div>
          ))}
        </div>
        {errors.periods && <p role="alert" className="mt-1 text-xs text-destructive">{errors.periods}</p>}
      </div>

      <div className="mt-4">
        <div className="flex items-center justify-between gap-2">
          <Label>Ngày nghỉ</Label>
          <Button type="button" variant="ghost" size="sm" onClick={() => setForm({ ...form, holidays: [...form.holidays, { holiday_date: "", name: "" }] })}>
            <Plus aria-hidden="true" />
            Thêm
          </Button>
        </div>
        <div className="mt-2 space-y-2">
          {form.holidays.map((holiday, index) => (
            <div key={`${holiday.holiday_date}-${index}`} className="grid grid-cols-[150px_minmax(0,1fr)_36px] gap-2">
              <Input type="date" aria-label={`Ngày nghỉ ${index + 1}`} value={holiday.holiday_date} onChange={(event) => setForm({ ...form, holidays: form.holidays.map((item, itemIndex) => itemIndex === index ? { ...item, holiday_date: event.target.value } : item) })} />
              <Input aria-label={`Tên ngày nghỉ ${index + 1}`} value={holiday.name} onChange={(event) => setForm({ ...form, holidays: form.holidays.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item) })} />
              <Button type="button" variant="ghost" size="icon" aria-label={`Xóa ngày nghỉ ${index + 1}`} onClick={() => setForm({ ...form, holidays: form.holidays.filter((_, itemIndex) => itemIndex !== index) })}>
                <Trash2 aria-hidden="true" />
              </Button>
            </div>
          ))}
        </div>
      </div>

      <CheckboxField className="mt-4" label="Calendar đang hoạt động" checked={form.is_active} onChange={(is_active) => setForm({ ...form, is_active })} />
      {mutation.isError && <MutationError error={mutation.error} />}
      <Button type="submit" className="mt-4" disabled={mutation.isPending}>
        {mutation.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
        Lưu calendar
      </Button>
    </form>
  );
}
