"use client";

import { useRef, useState } from "react";

import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useTransferStockMutation } from "@/hooks/use-inventory";
import type { InventoryMovement } from "@/lib/api/inventory-schemas";
import { createInventoryIdempotencyKey } from "@/lib/inventory";
import { ActionShell, EvidenceUpload, Field, LocationSelect, MutationFooter, PartSelect, type LocationOption, type PartOption } from "@/components/inventory/actions/shared";

export type { LocationOption, PartOption };

export function TransferForm({
  parts,
  locations,
}: {
  parts: PartOption[];
  locations: LocationOption[];
}) {
  const mutation = useTransferStockMutation();
  const key = useRef(createInventoryIdempotencyKey("transfer"));
  const [movement, setMovement] = useState<InventoryMovement | null>(null);
  const [form, setForm] = useState({
    part_id: "",
    source_stock_location_id: "",
    destination_stock_location_id: "",
    quantity: "",
    business_reference: "",
    reason: "",
  });
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      const result = await mutation.mutateAsync({
        request: {
          ...form,
          quantity: Number(form.quantity),
          occurred_at: null,
        },
        idempotencyKey: key.current,
      });
      setMovement(result.transfer_in);
      key.current = createInventoryIdempotencyKey("transfer");
    } catch {
      // Normalized mutation error is rendered below.
    }
  }
  return (
    <ActionShell
      title="Điều chuyển phụ tùng"
      notice="Kiểm tra kho nguồn, kho đích và số lượng trước khi xác nhận."
      movement={movement}
    >
      <form onSubmit={submit}>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <PartSelect
            id="transfer-part"
            value={form.part_id}
            onChange={(value) => setForm({ ...form, part_id: value })}
            parts={parts}
          />
          <LocationSelect
            id="transfer-source"
            label="Kho nguồn"
            value={form.source_stock_location_id}
            onChange={(value) =>
              setForm({ ...form, source_stock_location_id: value })
            }
            locations={locations}
          />
          <LocationSelect
            id="transfer-destination"
            label="Kho đích"
            value={form.destination_stock_location_id}
            onChange={(value) =>
              setForm({ ...form, destination_stock_location_id: value })
            }
            locations={locations.filter(
              (location) => location.id !== form.source_stock_location_id,
            )}
          />
          <Field id="transfer-quantity" label="Số lượng">
            <Input
              id="transfer-quantity"
              type="number"
              min={0.001}
              step="0.001"
              required
              value={form.quantity}
              onChange={(event) => setForm({ ...form, quantity: event.target.value })}
            />
          </Field>
          <Field id="transfer-reference" label="Mã chứng từ">
            <Input
              id="transfer-reference"
              required
              value={form.business_reference}
              onChange={(event) =>
                setForm({ ...form, business_reference: event.target.value })
              }
            />
          </Field>
          <div className="sm:col-span-2 xl:col-span-3">
            <Field id="transfer-reason" label="Lý do chuyển">
              <Textarea
                id="transfer-reason"
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
          disabled={
            !form.part_id ||
            !form.source_stock_location_id ||
            !form.destination_stock_location_id
          }
          label="Xác nhận điều chuyển"
        />
      </form>
      {movement && <EvidenceUpload movement={movement} defaultCategory="transfer_evidence" />}
    </ActionShell>
  );
}
