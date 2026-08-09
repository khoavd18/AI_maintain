"use client";

import { useRef, useState } from "react";

import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useReceiveStockMutation,  } from "@/hooks/use-inventory";
import type { InventoryMovement } from "@/lib/api/inventory-schemas";
import { createInventoryIdempotencyKey } from "@/lib/inventory";
import { ActionShell, EvidenceUpload, Field, LocationSelect, MutationFooter, PartSelect, type LocationOption, type PartOption } from "@/components/inventory/actions/shared";

export type { LocationOption, PartOption };

export function ReceivingForm({
  parts,
  locations,
}: {
  parts: PartOption[];
  locations: LocationOption[];
}) {
  const [operation, setOperation] = useState<"receipt" | "opening_balance">(
    "receipt",
  );
  const mutation = useReceiveStockMutation(operation);
  const keys = useRef({
    receipt: createInventoryIdempotencyKey("receipt"),
    opening_balance: createInventoryIdempotencyKey("opening-balance"),
  });
  const [movement, setMovement] = useState<InventoryMovement | null>(null);
  const [form, setForm] = useState({
    part_id: "",
    stock_location_id: "",
    quantity: "",
    business_reference: "",
    reason: "",
    unit_cost_snapshot: "",
  });
  const selectedPart = parts.find((part) => part.id === form.part_id);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      const result = await mutation.mutateAsync({
        request: {
          part_id: form.part_id,
          stock_location_id: form.stock_location_id,
          quantity: Number(form.quantity),
          business_reference: form.business_reference,
          occurred_at: null,
          reason: form.reason,
          unit_cost_snapshot: form.unit_cost_snapshot
            ? Number(form.unit_cost_snapshot)
            : null,
        },
        idempotencyKey: keys.current[operation],
      });
      setMovement(result);
      keys.current[operation] = createInventoryIdempotencyKey(
        operation === "receipt" ? "receipt" : "opening-balance",
      );
    } catch {
      // Normalized mutation error is rendered below.
    }
  }

  return (
    <ActionShell
      title={operation === "receipt" ? "Nhập kho" : "Số lượng đầu kỳ"}
      notice="Kiểm tra phụ tùng, vị trí và số lượng trước khi xác nhận."
      movement={movement}
    >
      <form onSubmit={submit}>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <Field id="receiving-operation" label="Loại nghiệp vụ">
            <Select
              value={operation}
              onValueChange={(value) =>
                setOperation(value as "receipt" | "opening_balance")
              }
            >
              <SelectTrigger id="receiving-operation" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="receipt">Nhập kho</SelectItem>
                <SelectItem value="opening_balance">Số dư đầu kỳ</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <PartSelect
            id="receiving-part"
            value={form.part_id}
            onChange={(value) => setForm({ ...form, part_id: value })}
            parts={parts}
          />
          <LocationSelect
            id="receiving-location"
            value={form.stock_location_id}
            onChange={(value) =>
              setForm({ ...form, stock_location_id: value })
            }
            locations={locations}
          />
          <Field id="receiving-quantity" label={`Số lượng ${selectedPart?.unit_symbol ?? ""}`}>
            <Input
              id="receiving-quantity"
              type="number"
              min={0.001}
              step="0.001"
              required
              value={form.quantity}
              onChange={(event) => setForm({ ...form, quantity: event.target.value })}
            />
          </Field>
          <Field id="receiving-reference" label="Mã chứng từ">
            <Input
              id="receiving-reference"
              required
              value={form.business_reference}
              onChange={(event) =>
                setForm({ ...form, business_reference: event.target.value })
              }
            />
          </Field>
          <Field id="receiving-cost" label="Đơn giá tại thời điểm nhập (tùy chọn)">
            <Input
              id="receiving-cost"
              type="number"
              min={0}
              step="0.01"
              value={form.unit_cost_snapshot}
              onChange={(event) =>
                setForm({ ...form, unit_cost_snapshot: event.target.value })
              }
            />
          </Field>
          <div className="sm:col-span-2 xl:col-span-3">
            <Field id="receiving-reason" label="Lý do">
              <Textarea
                id="receiving-reason"
                required
                value={form.reason}
                onChange={(event) => setForm({ ...form, reason: event.target.value })}
              />
            </Field>
          </div>
        </div>
        <MutationFooter
          error={mutation.error}
          pending={mutation.isPending}
          disabled={!form.part_id || !form.stock_location_id}
          label={operation === "receipt" ? "Xác nhận nhập kho" : "Ghi số lượng đầu kỳ"}
        />
      </form>
      {movement && <EvidenceUpload movement={movement} defaultCategory="receipt_evidence" />}
    </ActionShell>
  );
}
