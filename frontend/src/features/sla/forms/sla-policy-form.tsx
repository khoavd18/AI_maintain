"use client";

import { type FormEvent, useState } from "react";
import { Clock3, Loader2 } from "lucide-react";

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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useCreateSlaPolicyMutation,
  useUpdateSlaPolicyMutation,
} from "@/hooks/use-ticketing";
import {
  slaPolicyRequestSchema,
  type BusinessCalendar,
  type SlaPolicy,
  type SlaPolicyRequest,
  type TicketPriorityCode,
} from "@/lib/api/ticketing-schemas";
import { zodFieldErrors } from "@/lib/workflow";

import { CheckboxField, FormInput, MutationError } from "../components/form-controls";

const priorityOrder: TicketPriorityCode[] = ["low", "medium", "high", "critical"];

export function SlaPolicyForm({
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
          calendar_id: defaultCalendar?.id ?? "00000000-0000-0000-0000-000000000000",
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
      <h2 className="text-sm font-semibold">{initial ? `Sửa ${initial.code}` : "Tạo SLA policy"}</h2>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <FormInput id="policy-code" label="Code" value={form.code} disabled={Boolean(initial)} error={errors.code} onChange={(code) => setForm({ ...form, code: code.toUpperCase() })} />
        <FormInput id="policy-name" label="Tên policy" value={form.name} error={errors.name} onChange={(name) => setForm({ ...form, name })} />
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="policy-calendar">Business calendar</Label>
          <Select value={form.calendar_id} onValueChange={(calendar_id) => { const calendar = calendars.find((item) => item.id === calendar_id); setForm({ ...form, calendar_id, timezone: calendar?.timezone ?? form.timezone }); }}>
            <SelectTrigger id="policy-calendar" className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>{calendars.map((calendar) => <SelectItem key={calendar.id} value={calendar.id}>{calendar.code}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="policy-category">Category</Label>
          <Select value={form.category_id ?? "none"} onValueChange={(category_id) => setForm({ ...form, category_id: category_id === "none" ? null : category_id })}>
            <SelectTrigger id="policy-category" className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">Policy mặc định</SelectItem>
              {categories.map((category) => <SelectItem key={category.id} value={category.id}>{category.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <FormInput id="policy-effective-from" type="date" label="Hiệu lực từ" value={form.effective_from} onChange={(effective_from) => setForm({ ...form, effective_from })} />
        <FormInput id="policy-effective-to" type="date" label="Hiệu lực đến" value={form.effective_to ?? ""} error={errors.effective_to} onChange={(effective_to) => setForm({ ...form, effective_to: effective_to || null })} />
        <FormInput id="policy-due-soon" type="number" label="Due soon %" value={String(form.due_soon_percent)} onChange={(value) => setForm({ ...form, due_soon_percent: Number(value) })} />
      </div>

      <div className="mt-4">
        <Label>SLA targets (business minutes)</Label>
        <div className="mt-2 overflow-x-auto">
          <Table>
            <TableHeader><TableRow><TableHead>Priority</TableHead><TableHead>First response</TableHead><TableHead>Resolution</TableHead></TableRow></TableHeader>
            <TableBody>
              {priorityOrder.map((priority) => {
                const index = form.targets.findIndex((target) => target.priority === priority);
                const target = form.targets[index];
                return (
                  <TableRow key={priority}>
                    <TableCell className="capitalize">{priority}</TableCell>
                    <TableCell><Input aria-label={`First response ${priority}`} type="number" min={1} value={target.first_response_minutes} onChange={(event) => setForm({ ...form, targets: form.targets.map((item, itemIndex) => itemIndex === index ? { ...item, first_response_minutes: Number(event.target.value) } : item) })} /></TableCell>
                    <TableCell><Input aria-label={`Resolution ${priority}`} type="number" min={1} value={target.resolution_minutes} onChange={(event) => setForm({ ...form, targets: form.targets.map((item, itemIndex) => itemIndex === index ? { ...item, resolution_minutes: Number(event.target.value) } : item) })} /></TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-5">
        <CheckboxField label="Pause resolution SLA khi waiting" checked={form.pause_on_waiting} onChange={(pause_on_waiting) => setForm({ ...form, pause_on_waiting })} />
        <CheckboxField label="Policy đang hoạt động" checked={form.is_active} onChange={(is_active) => setForm({ ...form, is_active })} />
      </div>
      {mutation.isError && <MutationError error={mutation.error} />}
      <Button type="submit" className="mt-4" disabled={mutation.isPending}>
        {mutation.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Clock3 aria-hidden="true" />}
        Lưu policy
      </Button>
    </form>
  );
}
