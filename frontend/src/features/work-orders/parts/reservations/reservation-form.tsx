"use client";

import { useRef, useState } from "react";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useReserveStockMutation } from "@/hooks/use-inventory";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { Requirement } from "@/lib/api/inventory-schemas";
import { createInventoryIdempotencyKey } from "@/lib/inventory";

import { ActionCard, Field, SubmitFooter } from "../components/section-state";

export function ReservationForm({
  workOrderId,
  requirements,
}: {
  workOrderId: string;
  requirements: Requirement[];
}) {
  const eligible = requirements.filter(
    (item) =>
      item.shortage_quantity > 0 &&
      !["fulfilled", "cancelled"].includes(item.status),
  );
  const mutation = useReserveStockMutation(workOrderId);
  const key = useRef(createInventoryIdempotencyKey("reserve"));
  const [requirementId, setRequirementId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const selected = eligible.find((item) => item.id === requirementId);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!selected) return;
    try {
      await mutation.mutateAsync({
        requirementId: selected.id,
        request: {
          quantity: Number(quantity),
          expected_requirement_version: selected.version,
          expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
          reason: "Giữ vật tư cho work order",
        },
        idempotencyKey: key.current,
      });
      key.current = createInventoryIdempotencyKey("reserve");
      setRequirementId("");
      setQuantity("");
      setExpiresAt("");
      setMessage("Đã giữ vật tư; available giảm, on-hand không đổi.");
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    }
  }
  return (
    <ActionCard title="Giữ vật tư" description="Reserve theo nhu cầu đã lập.">
      {!eligible.length ? (
        <p className="text-sm text-muted-foreground">
          Không có nhu cầu phụ tùng còn thiếu để đặt trước.
        </p>
      ) : (
        <form onSubmit={submit} className="space-y-3">
          <Field id="reservation-requirement" label="Nhu cầu">
            <Select value={requirementId} onValueChange={setRequirementId}>
              <SelectTrigger id="reservation-requirement" className="w-full">
                <SelectValue placeholder="Chọn vật tư" />
              </SelectTrigger>
              <SelectContent>
                {eligible.map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    {item.part_number} · thiếu {item.shortage_quantity}{" "}
                    {item.unit_symbol}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field id="reservation-quantity" label="Số lượng giữ">
            <Input
              id="reservation-quantity"
              required
              type="number"
              min={0.001}
              max={selected?.shortage_quantity}
              step="0.001"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
            />
          </Field>
          <Field id="reservation-expiry" label="Hết hạn (tùy chọn)">
            <Input
              id="reservation-expiry"
              type="datetime-local"
              value={expiresAt}
              onChange={(event) => setExpiresAt(event.target.value)}
            />
          </Field>
          <SubmitFooter
            mutationError={mutation.error}
            message={message}
            pending={mutation.isPending}
            disabled={!selected}
            label="Giữ vật tư"
          />
        </form>
      )}
    </ActionCard>
  );
}
