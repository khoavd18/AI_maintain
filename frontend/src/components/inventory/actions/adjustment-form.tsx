"use client";

import { useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAdjustStockMutation, useInventoryBalancesQuery,  } from "@/hooks/use-inventory";
import type { InventoryMovement } from "@/lib/api/inventory-schemas";
import { createInventoryIdempotencyKey, formatQuantity } from "@/lib/inventory";
import { ActionShell, EvidenceUpload, Field, LocationSelect, MutationFooter, PartSelect, PreviewFact, type LocationOption, type PartOption } from "@/components/inventory/actions/shared";

export type { LocationOption, PartOption };

export function AdjustmentForm({
  parts,
  locations,
}: {
  parts: PartOption[];
  locations: LocationOption[];
}) {
  const auth = useAuth();
  const mutation = useAdjustStockMutation();
  const key = useRef(createInventoryIdempotencyKey("adjustment"));
  const [movement, setMovement] = useState<InventoryMovement | null>(null);
  const [form, setForm] = useState({
    part_id: "",
    stock_location_id: "",
    quantity: "",
    adjustment_type: "increase" as
      | "increase"
      | "decrease"
      | "damaged_scrapped",
    business_reference: "",
    reason: "",
    supporting_note: "",
  });
  const selectedPart = parts.find((part) => part.id === form.part_id);
  const balances = useInventoryBalancesQuery(
    {
      search: selectedPart?.part_number,
      stock_location_id: form.stock_location_id || undefined,
      page: 1,
      page_size: 20,
    },
    Boolean(selectedPart && form.stock_location_id),
  );
  const currentBalance = balances.data?.items.find(
    (item) => item.part_id === form.part_id && item.stock_location_id === form.stock_location_id,
  );
  const requestedQuantity = Number(form.quantity) || 0;
  const signedQuantity = form.adjustment_type === "increase" ? requestedQuantity : -requestedQuantity;
  const resultingOnHand = currentBalance ? currentBalance.on_hand_quantity + signedQuantity : null;
  const resultingAvailable = currentBalance && resultingOnHand !== null
    ? resultingOnHand - currentBalance.reserved_quantity
    : null;
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      const result = await mutation.mutateAsync({
        request: {
          ...form,
          quantity: Number(form.quantity),
          occurred_at: null,
          unit_cost_snapshot: null,
        },
        idempotencyKey: key.current,
      });
      setMovement(result);
      key.current = createInventoryIdempotencyKey("adjustment");
    } catch {
      // Normalized mutation error is rendered below.
    }
  }
  return (
    <ActionShell
      title="Điều chỉnh số lượng"
      notice="Số lượng sau điều chỉnh không được âm hoặc thấp hơn số đã đặt trước."
      movement={movement}
    >
      <form onSubmit={submit}>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <PartSelect
            id="adjustment-part"
            value={form.part_id}
            onChange={(value) => setForm({ ...form, part_id: value })}
            parts={parts}
          />
          <LocationSelect
            id="adjustment-location"
            value={form.stock_location_id}
            onChange={(value) =>
              setForm({ ...form, stock_location_id: value })
            }
            locations={locations}
          />
          <Field id="adjustment-type" label="Loại điều chỉnh">
            <Select
              value={form.adjustment_type}
              onValueChange={(value) =>
                setForm({
                  ...form,
                  adjustment_type: value as typeof form.adjustment_type,
                })
              }
            >
              <SelectTrigger id="adjustment-type" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="increase">Điều chỉnh tăng</SelectItem>
                <SelectItem value="decrease">Điều chỉnh giảm</SelectItem>
                <SelectItem value="damaged_scrapped">Hư hỏng / loại bỏ</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field id="adjustment-quantity" label="Số lượng">
            <Input
              id="adjustment-quantity"
              type="number"
              min={0.001}
              step="0.001"
              required
              value={form.quantity}
              onChange={(event) => setForm({ ...form, quantity: event.target.value })}
            />
          </Field>
          <Field id="adjustment-reference" label="Mã chứng từ">
            <Input
              id="adjustment-reference"
              required
              value={form.business_reference}
              onChange={(event) =>
                setForm({ ...form, business_reference: event.target.value })
              }
            />
          </Field>
          <Field id="adjustment-reason" label="Lý do">
            <Input
              id="adjustment-reason"
              required
              value={form.reason}
              onChange={(event) => setForm({ ...form, reason: event.target.value })}
            />
          </Field>
          <div className="sm:col-span-2 xl:col-span-3">
            <Field id="adjustment-note" label="Ghi chú chứng minh">
              <Textarea
                id="adjustment-note"
                required
                value={form.supporting_note}
                onChange={(event) =>
                  setForm({ ...form, supporting_note: event.target.value })
                }
              />
            </Field>
          </div>
        </div>
        {currentBalance && requestedQuantity > 0 && resultingOnHand !== null && resultingAvailable !== null && (
          <section aria-label="Tóm tắt điều chỉnh" className="mt-4 rounded-lg border bg-muted/30 p-4">
            <h3 className="text-sm font-semibold">Kiểm tra trước khi xác nhận</h3>
            <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <PreviewFact label="Tồn hiện tại" value={formatQuantity(currentBalance.on_hand_quantity, currentBalance.unit_symbol)} />
              <PreviewFact label="Số lượng điều chỉnh" value={`${form.adjustment_type === "increase" ? "+" : "−"}${formatQuantity(requestedQuantity, currentBalance.unit_symbol)}`} />
              <PreviewFact label="Tồn dự kiến" value={formatQuantity(resultingOnHand, currentBalance.unit_symbol)} />
              <PreviewFact label="Khả dụng dự kiến" value={formatQuantity(resultingAvailable, currentBalance.unit_symbol)} />
              <PreviewFact label="Người thực hiện" value={auth.user?.display_name ?? "Người dùng hiện tại"} />
            </dl>
            <p className="mt-3 text-xs text-muted-foreground">Hệ thống sẽ kiểm tra lại số lượng khi ghi giao dịch.</p>
          </section>
        )}
        <MutationFooter
          error={mutation.error}
          pending={mutation.isPending}
          disabled={!form.part_id || !form.stock_location_id}
          label="Xác nhận điều chỉnh"
        />
      </form>
      {movement && (
        <EvidenceUpload
          movement={movement}
          defaultCategory={
            form.adjustment_type === "damaged_scrapped"
              ? "damage_evidence"
              : "adjustment_evidence"
          }
        />
      )}
    </ActionShell>
  );
}
