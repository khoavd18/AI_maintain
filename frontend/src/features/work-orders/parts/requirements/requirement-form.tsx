"use client";

import { useState } from "react";

import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useCreateRequirementMutation } from "@/hooks/use-inventory";
import { getApiErrorMessage } from "@/lib/api/errors";

import { ActionCard, Field, SubmitFooter } from "../components/section-state";
import { LocationSelect } from "../selectors/warehouse-selector";
import { PartSelect } from "../selectors/inventory-item-selector";
import type { LocationOption, PartOption } from "../types";

export function RequirementForm({
  workOrderId,
  parts,
  locations,
}: {
  workOrderId: string;
  parts: PartOption[];
  locations: LocationOption[];
}) {
  const mutation = useCreateRequirementMutation(workOrderId);
  const [form, setForm] = useState({
    part_id: "",
    source_stock_location_id: "",
    planned_quantity: "",
    required_by_date: "",
    notes: "",
  });
  const [message, setMessage] = useState<string | null>(null);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      await mutation.mutateAsync({
        part_id: form.part_id,
        source_stock_location_id: form.source_stock_location_id,
        planned_quantity: Number(form.planned_quantity),
        required_by_date: form.required_by_date || null,
        notes: form.notes.trim() || null,
      });
      setForm({
        part_id: "",
        source_stock_location_id: "",
        planned_quantity: "",
        required_by_date: "",
        notes: "",
      });
      setMessage("Đã thêm nhu cầu phụ tùng.");
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    }
  }
  return (
    <ActionCard title="Thêm nhu cầu" description="Không làm thay đổi tồn kho.">
      <form onSubmit={submit} className="space-y-3">
        <PartSelect
          id="requirement-part"
          value={form.part_id}
          onChange={(value) => setForm({ ...form, part_id: value })}
          parts={parts}
        />
        <LocationSelect
          id="requirement-location"
          value={form.source_stock_location_id}
          onChange={(value) =>
            setForm({ ...form, source_stock_location_id: value })
          }
          locations={locations}
        />
        <Field id="requirement-quantity" label="Số lượng dự kiến">
          <Input
            id="requirement-quantity"
            required
            type="number"
            min={0.001}
            step="0.001"
            value={form.planned_quantity}
            onChange={(event) =>
              setForm({ ...form, planned_quantity: event.target.value })
            }
          />
        </Field>
        <Field id="requirement-date" label="Cần trước ngày">
          <Input
            id="requirement-date"
            type="date"
            value={form.required_by_date}
            onChange={(event) =>
              setForm({ ...form, required_by_date: event.target.value })
            }
          />
        </Field>
        <Field id="requirement-notes" label="Ghi chú">
          <Textarea
            id="requirement-notes"
            value={form.notes}
            onChange={(event) => setForm({ ...form, notes: event.target.value })}
          />
        </Field>
        <SubmitFooter
          mutationError={mutation.error}
          message={message}
          pending={mutation.isPending}
          disabled={!form.part_id || !form.source_stock_location_id}
          label="Thêm nhu cầu"
        />
      </form>
    </ActionCard>
  );
}
