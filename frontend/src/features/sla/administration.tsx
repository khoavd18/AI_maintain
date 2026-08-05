"use client";

import {
  CalendarDays,
  Clock3,
  Loader2,
  Pencil,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import { type FormEvent, useState } from "react";

import { useAuth } from "@/components/auth-provider";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import {
  useBusinessCalendarsQuery,
  useCreateBusinessCalendarMutation,
  useCreateSlaPolicyMutation,
  useSlaPoliciesQuery,
  useTicketingOptionsQuery,
  useUpdateBusinessCalendarMutation,
  useUpdateSlaPolicyMutation,
} from "@/hooks/use-ticketing";
import { getApiErrorMessage } from "@/lib/api/errors";
import {
  businessCalendarRequestSchema,
  slaPolicyRequestSchema,
  type BusinessCalendar,
  type BusinessCalendarRequest,
  type SlaPolicy,
  type SlaPolicyRequest,
  type TicketPriorityCode,
} from "@/lib/api/ticketing-schemas";
import { permissions } from "@/lib/auth";
import { formatDate } from "@/lib/formatters";
import { zodFieldErrors } from "@/lib/workflow";

const weekdayLabels = [
  "Thứ Hai",
  "Thứ Ba",
  "Thứ Tư",
  "Thứ Năm",
  "Thứ Sáu",
  "Thứ Bảy",
  "Chủ Nhật",
];

const priorityOrder: TicketPriorityCode[] = [
  "low",
  "medium",
  "high",
  "critical",
];

export function SlaAdministration() {
  const auth = useAuth();
  const canManage = auth.can(permissions.slaPoliciesManage);
  const calendars = useBusinessCalendarsQuery();
  const policies = useSlaPoliciesQuery();
  const options = useTicketingOptionsQuery();
  const [calendarEdit, setCalendarEdit] = useState<BusinessCalendar | null>(null);
  const [policyEdit, setPolicyEdit] = useState<SlaPolicy | null>(null);

  if (calendars.isPending || policies.isPending || options.isPending) {
    return <LoadingSkeleton />;
  }
  if (calendars.isError || policies.isError || options.isError) {
    return (
      <ErrorState
        title="Chưa tải được cấu hình SLA"
        description={getApiErrorMessage(
          calendars.error ?? policies.error ?? options.error,
        )}
        action={
          <RetryButton
            onClick={() => {
              void calendars.refetch();
              void policies.refetch();
              void options.refetch();
            }}
          />
        }
      />
    );
  }

  return (
    <Tabs defaultValue="policies">
      <TabsList>
        <TabsTrigger value="policies">SLA policies</TabsTrigger>
        <TabsTrigger value="calendars">Business calendars</TabsTrigger>
      </TabsList>

      <TabsContent value="policies" className="mt-4">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_460px]">
          <section className="overflow-hidden rounded-lg border bg-white">
            <header className="flex items-center justify-between gap-3 border-b p-4">
              <div>
                <h2 className="text-sm font-semibold">Policy đang cấu hình</h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  Ticket giữ snapshot; chỉnh policy không viết lại lịch sử.
                </p>
              </div>
              {canManage && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setPolicyEdit(null)}
                >
                  <Plus aria-hidden="true" />
                  Policy mới
                </Button>
              )}
            </header>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Policy</TableHead>
                    <TableHead>Calendar</TableHead>
                    <TableHead>Hiệu lực</TableHead>
                    <TableHead>Due soon</TableHead>
                    <TableHead>Trạng thái</TableHead>
                    {canManage && <TableHead />}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {policies.data.map((policy) => (
                    <TableRow key={policy.id}>
                      <TableCell>
                        <p className="font-mono text-xs font-semibold text-primary">
                          {policy.code}
                        </p>
                        <p className="mt-1 text-sm">{policy.name}</p>
                      </TableCell>
                      <TableCell>{policy.calendar_code}</TableCell>
                      <TableCell className="text-xs">
                        {formatDate(policy.effective_from)}
                        {policy.effective_to
                          ? ` – ${formatDate(policy.effective_to)}`
                          : " – không giới hạn"}
                      </TableCell>
                      <TableCell>{policy.due_soon_percent}%</TableCell>
                      <TableCell>
                        <span
                          className={`rounded px-2 py-1 text-xs ${
                            policy.is_active
                              ? "bg-green-50 text-green-700"
                              : "bg-neutral-100 text-neutral-600"
                          }`}
                        >
                          {policy.is_active ? "Đang dùng" : "Ngừng dùng"}
                        </span>
                      </TableCell>
                      {canManage && (
                        <TableCell className="text-right">
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => setPolicyEdit(policy)}
                          >
                            <Pencil aria-hidden="true" />
                            Sửa
                          </Button>
                        </TableCell>
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </section>
          {canManage ? (
            <SlaPolicyForm
              key={policyEdit?.id ?? "new-policy"}
              initial={policyEdit}
              calendars={calendars.data}
              categories={options.data.categories}
              onSaved={() => setPolicyEdit(null)}
            />
          ) : (
            <ReadOnlyNotice />
          )}
        </div>
      </TabsContent>

      <TabsContent value="calendars" className="mt-4">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_460px]">
          <section className="rounded-lg border bg-white">
            <header className="flex items-center justify-between gap-3 border-b p-4">
              <div>
                <h2 className="text-sm font-semibold">Business calendars</h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  Giờ làm việc theo timezone IANA và ngày nghỉ địa phương.
                </p>
              </div>
              {canManage && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setCalendarEdit(null)}
                >
                  <Plus aria-hidden="true" />
                  Calendar mới
                </Button>
              )}
            </header>
            <div className="divide-y">
              {calendars.data.map((calendar) => (
                <article
                  key={calendar.id}
                  className="flex flex-col justify-between gap-3 p-4 sm:flex-row sm:items-start"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <CalendarDays className="size-4 text-primary" aria-hidden="true" />
                      <p className="font-mono text-xs font-semibold text-primary">
                        {calendar.code}
                      </p>
                    </div>
                    <p className="mt-2 text-sm font-semibold">{calendar.name}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {calendar.timezone} · {calendar.periods.length} khung giờ ·{" "}
                      {calendar.holidays.length} ngày nghỉ
                    </p>
                  </div>
                  {canManage && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setCalendarEdit(calendar)}
                    >
                      <Pencil aria-hidden="true" />
                      Sửa
                    </Button>
                  )}
                </article>
              ))}
            </div>
          </section>
          {canManage ? (
            <BusinessCalendarForm
              key={calendarEdit?.id ?? "new-calendar"}
              initial={calendarEdit}
              onSaved={() => setCalendarEdit(null)}
            />
          ) : (
            <ReadOnlyNotice />
          )}
        </div>
      </TabsContent>
    </Tabs>
  );
}

function BusinessCalendarForm({
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
        await update.mutateAsync({
          ...parsed.data,
          expected_version: initial.version,
        });
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
      <h2 className="text-sm font-semibold">
        {initial ? `Sửa ${initial.code}` : "Tạo business calendar"}
      </h2>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <FormInput
          id="calendar-code"
          label="Code"
          value={form.code}
          disabled={Boolean(initial)}
          error={errors.code}
          onChange={(code) => setForm({ ...form, code: code.toUpperCase() })}
        />
        <FormInput
          id="calendar-name"
          label="Tên"
          value={form.name}
          error={errors.name}
          onChange={(name) => setForm({ ...form, name })}
        />
      </div>
      <div className="mt-3">
        <FormInput
          id="calendar-timezone"
          label="IANA timezone"
          value={form.timezone}
          error={errors.timezone}
          onChange={(timezone) => setForm({ ...form, timezone })}
        />
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
                periods: [
                  ...form.periods,
                  { weekday: 0, start_time: "08:00:00", end_time: "17:00:00" },
                ],
              })
            }
          >
            <Plus aria-hidden="true" />
            Thêm
          </Button>
        </div>
        <div className="mt-2 space-y-2">
          {form.periods.map((period, index) => (
            <div
              key={`${period.weekday}-${index}`}
              className="grid grid-cols-[minmax(0,1fr)_105px_105px_36px] gap-2"
            >
              <Select
                value={String(period.weekday)}
                onValueChange={(weekday) =>
                  setForm({
                    ...form,
                    periods: form.periods.map((item, itemIndex) =>
                      itemIndex === index
                        ? { ...item, weekday: Number(weekday) }
                        : item,
                    ),
                  })
                }
              >
                <SelectTrigger aria-label={`Ngày làm việc ${index + 1}`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {weekdayLabels.map((label, weekday) => (
                    <SelectItem key={label} value={String(weekday)}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                type="time"
                aria-label={`Bắt đầu ${index + 1}`}
                value={period.start_time.slice(0, 5)}
                onChange={(event) =>
                  setForm({
                    ...form,
                    periods: form.periods.map((item, itemIndex) =>
                      itemIndex === index
                        ? { ...item, start_time: `${event.target.value}:00` }
                        : item,
                    ),
                  })
                }
              />
              <Input
                type="time"
                aria-label={`Kết thúc ${index + 1}`}
                value={period.end_time.slice(0, 5)}
                onChange={(event) =>
                  setForm({
                    ...form,
                    periods: form.periods.map((item, itemIndex) =>
                      itemIndex === index
                        ? { ...item, end_time: `${event.target.value}:00` }
                        : item,
                    ),
                  })
                }
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={`Xóa khung giờ ${index + 1}`}
                onClick={() =>
                  setForm({
                    ...form,
                    periods: form.periods.filter(
                      (_, itemIndex) => itemIndex !== index,
                    ),
                  })
                }
              >
                <Trash2 aria-hidden="true" />
              </Button>
            </div>
          ))}
        </div>
        {errors.periods && (
          <p role="alert" className="mt-1 text-xs text-destructive">
            {errors.periods}
          </p>
        )}
      </div>

      <div className="mt-4">
        <div className="flex items-center justify-between gap-2">
          <Label>Ngày nghỉ</Label>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() =>
              setForm({
                ...form,
                holidays: [
                  ...form.holidays,
                  { holiday_date: "", name: "" },
                ],
              })
            }
          >
            <Plus aria-hidden="true" />
            Thêm
          </Button>
        </div>
        <div className="mt-2 space-y-2">
          {form.holidays.map((holiday, index) => (
            <div
              key={`${holiday.holiday_date}-${index}`}
              className="grid grid-cols-[150px_minmax(0,1fr)_36px] gap-2"
            >
              <Input
                type="date"
                aria-label={`Ngày nghỉ ${index + 1}`}
                value={holiday.holiday_date}
                onChange={(event) =>
                  setForm({
                    ...form,
                    holidays: form.holidays.map((item, itemIndex) =>
                      itemIndex === index
                        ? { ...item, holiday_date: event.target.value }
                        : item,
                    ),
                  })
                }
              />
              <Input
                aria-label={`Tên ngày nghỉ ${index + 1}`}
                value={holiday.name}
                onChange={(event) =>
                  setForm({
                    ...form,
                    holidays: form.holidays.map((item, itemIndex) =>
                      itemIndex === index
                        ? { ...item, name: event.target.value }
                        : item,
                    ),
                  })
                }
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={`Xóa ngày nghỉ ${index + 1}`}
                onClick={() =>
                  setForm({
                    ...form,
                    holidays: form.holidays.filter(
                      (_, itemIndex) => itemIndex !== index,
                    ),
                  })
                }
              >
                <Trash2 aria-hidden="true" />
              </Button>
            </div>
          ))}
        </div>
      </div>

      <CheckboxField
        className="mt-4"
        label="Calendar đang hoạt động"
        checked={form.is_active}
        onChange={(is_active) => setForm({ ...form, is_active })}
      />
      {mutation.isError && <MutationError error={mutation.error} />}
      <Button type="submit" className="mt-4" disabled={mutation.isPending}>
        {mutation.isPending ? (
          <Loader2 className="animate-spin" aria-hidden="true" />
        ) : (
          <Save aria-hidden="true" />
        )}
        Lưu calendar
      </Button>
    </form>
  );
}

function SlaPolicyForm({
  initial,
  calendars,
  categories,
  onSaved,
}: {
  initial: SlaPolicy | null;
  calendars: BusinessCalendar[];
  categories: { id: string; name: string }[];
  onSaved: () => void;
}) {
  const create = useCreateSlaPolicyMutation();
  const update = useUpdateSlaPolicyMutation(initial?.id ?? "");
  const mutation = initial ? update : create;
  const defaultCalendar = calendars[0];
  const [form, setForm] = useState<SlaPolicyRequest>(
    initial
      ? {
          code: initial.code,
          name: initial.name,
          calendar_id: initial.calendar_id,
          category_id: initial.category_id,
          timezone: initial.timezone,
          pause_on_waiting: initial.pause_on_waiting,
          due_soon_percent: initial.due_soon_percent,
          effective_from: initial.effective_from,
          effective_to: initial.effective_to,
          is_active: initial.is_active,
          targets: initial.targets,
        }
      : {
          code: "",
          name: "",
          calendar_id:
            defaultCalendar?.id ?? "00000000-0000-0000-0000-000000000000",
          category_id: null,
          timezone: defaultCalendar?.timezone ?? "Asia/Ho_Chi_Minh",
          pause_on_waiting: true,
          due_soon_percent: 20,
          effective_from: new Date().toISOString().slice(0, 10),
          effective_to: null,
          is_active: true,
          targets: [
            { priority: "low", first_response_minutes: 240, resolution_minutes: 1440 },
            { priority: "medium", first_response_minutes: 120, resolution_minutes: 720 },
            { priority: "high", first_response_minutes: 60, resolution_minutes: 240 },
            { priority: "critical", first_response_minutes: 15, resolution_minutes: 120 },
          ],
        },
  );
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = slaPolicyRequestSchema.safeParse(form);
    if (!parsed.success) {
      setErrors(zodFieldErrors(parsed.error.issues));
      return;
    }
    setErrors({});
    try {
      if (initial) {
        await update.mutateAsync({
          ...parsed.data,
          expected_version: initial.version,
        });
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
      <h2 className="text-sm font-semibold">
        {initial ? `Sửa ${initial.code}` : "Tạo SLA policy"}
      </h2>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <FormInput
          id="policy-code"
          label="Code"
          value={form.code}
          disabled={Boolean(initial)}
          error={errors.code}
          onChange={(code) => setForm({ ...form, code: code.toUpperCase() })}
        />
        <FormInput
          id="policy-name"
          label="Tên policy"
          value={form.name}
          error={errors.name}
          onChange={(name) => setForm({ ...form, name })}
        />
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="policy-calendar">Business calendar</Label>
          <Select
            value={form.calendar_id}
            onValueChange={(calendar_id) => {
              const calendar = calendars.find((item) => item.id === calendar_id);
              setForm({
                ...form,
                calendar_id,
                timezone: calendar?.timezone ?? form.timezone,
              });
            }}
          >
            <SelectTrigger id="policy-calendar" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {calendars.map((calendar) => (
                <SelectItem key={calendar.id} value={calendar.id}>
                  {calendar.code}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="policy-category">Category</Label>
          <Select
            value={form.category_id ?? "none"}
            onValueChange={(category_id) =>
              setForm({
                ...form,
                category_id: category_id === "none" ? null : category_id,
              })
            }
          >
            <SelectTrigger id="policy-category" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">Policy mặc định</SelectItem>
              {categories.map((category) => (
                <SelectItem key={category.id} value={category.id}>
                  {category.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <FormInput
          id="policy-effective-from"
          type="date"
          label="Hiệu lực từ"
          value={form.effective_from}
          onChange={(effective_from) => setForm({ ...form, effective_from })}
        />
        <FormInput
          id="policy-effective-to"
          type="date"
          label="Hiệu lực đến"
          value={form.effective_to ?? ""}
          error={errors.effective_to}
          onChange={(effective_to) =>
            setForm({ ...form, effective_to: effective_to || null })
          }
        />
        <FormInput
          id="policy-due-soon"
          type="number"
          label="Due soon %"
          value={String(form.due_soon_percent)}
          onChange={(value) =>
            setForm({ ...form, due_soon_percent: Number(value) })
          }
        />
      </div>

      <div className="mt-4">
        <Label>SLA targets (business minutes)</Label>
        <div className="mt-2 overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Priority</TableHead>
                <TableHead>First response</TableHead>
                <TableHead>Resolution</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {priorityOrder.map((priority) => {
                const index = form.targets.findIndex(
                  (target) => target.priority === priority,
                );
                const target = form.targets[index];
                return (
                  <TableRow key={priority}>
                    <TableCell className="capitalize">{priority}</TableCell>
                    <TableCell>
                      <Input
                        aria-label={`First response ${priority}`}
                        type="number"
                        min={1}
                        value={target.first_response_minutes}
                        onChange={(event) =>
                          setForm({
                            ...form,
                            targets: form.targets.map((item, itemIndex) =>
                              itemIndex === index
                                ? {
                                    ...item,
                                    first_response_minutes: Number(
                                      event.target.value,
                                    ),
                                  }
                                : item,
                            ),
                          })
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        aria-label={`Resolution ${priority}`}
                        type="number"
                        min={1}
                        value={target.resolution_minutes}
                        onChange={(event) =>
                          setForm({
                            ...form,
                            targets: form.targets.map((item, itemIndex) =>
                              itemIndex === index
                                ? {
                                    ...item,
                                    resolution_minutes: Number(event.target.value),
                                  }
                                : item,
                            ),
                          })
                        }
                      />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-5">
        <CheckboxField
          label="Pause resolution SLA khi waiting"
          checked={form.pause_on_waiting}
          onChange={(pause_on_waiting) =>
            setForm({ ...form, pause_on_waiting })
          }
        />
        <CheckboxField
          label="Policy đang hoạt động"
          checked={form.is_active}
          onChange={(is_active) => setForm({ ...form, is_active })}
        />
      </div>
      {mutation.isError && <MutationError error={mutation.error} />}
      <Button type="submit" className="mt-4" disabled={mutation.isPending}>
        {mutation.isPending ? (
          <Loader2 className="animate-spin" aria-hidden="true" />
        ) : (
          <Clock3 aria-hidden="true" />
        )}
        Lưu policy
      </Button>
    </form>
  );
}

function FormInput({
  id,
  label,
  value,
  onChange,
  error,
  type = "text",
  disabled = false,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  type?: string;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type={type}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

function CheckboxField({
  label,
  checked,
  onChange,
  className = "",
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  className?: string;
}) {
  return (
    <label className={`flex items-center gap-2 text-sm ${className}`}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="size-4 rounded border-input"
      />
      {label}
    </label>
  );
}

function MutationError({ error }: { error: unknown }) {
  return (
    <p
      role="alert"
      className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900"
    >
      {getApiErrorMessage(error)}
    </p>
  );
}

function ReadOnlyNotice() {
  return (
    <section className="h-fit rounded-lg border bg-white p-4 text-sm text-muted-foreground">
      Vai trò hiện tại có thể xem cấu hình SLA nhưng không có permission chỉnh sửa.
    </section>
  );
}
