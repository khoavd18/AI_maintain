"use client";

import { useRef, useState } from "react";

import { InventoryStatusBadge } from "@/components/inventory-badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EmptyState } from "@/components/ui-states";
import { useAuth } from "@/components/auth-provider";
import {
  useReplaceReservationMutation,
  useReservationActionMutation,
} from "@/hooks/use-inventory";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { Reservation } from "@/lib/api/inventory-schemas";
import { permissions } from "@/lib/auth";
import { formatTimestamp } from "@/lib/formatters";
import { createInventoryIdempotencyKey } from "@/lib/inventory";

import { Field } from "../components/section-state";
import type { LocationOption } from "../types";

export function ReservationsSection({
  workOrderId,
  reservations,
  locations,
}: {
  workOrderId: string;
  reservations: Reservation[];
  locations: LocationOption[];
}) {
  const auth = useAuth();
  const action = useReservationActionMutation(workOrderId);
  const keys = useRef(new Map<string, string>());
  const [message, setMessage] = useState<string | null>(null);
  const [replacementId, setReplacementId] = useState<string | null>(null);

  function keyFor(reservationId: string, actionName: string) {
    const mapKey = `${reservationId}:${actionName}`;
    const existing = keys.current.get(mapKey);
    if (existing) return existing;
    const next = createInventoryIdempotencyKey(actionName);
    keys.current.set(mapKey, next);
    return next;
  }

  async function close(
    reservation: Reservation,
    actionName: "release" | "expire",
  ) {
    const mapKey = `${reservation.id}:${actionName}`;
    try {
      await action.mutateAsync({
        reservationId: reservation.id,
        action: actionName,
        request: {
          expected_version: reservation.version,
          reason:
            actionName === "release"
              ? "Hủy đặt trước từ lệnh công việc"
              : "Xác nhận đặt trước đã hết hạn",
        },
        idempotencyKey: keyFor(reservation.id, actionName),
      });
      keys.current.delete(mapKey);
      setMessage(
        actionName === "release"
          ? "Đã hủy đặt trước."
          : "Đã đánh dấu đặt trước hết hạn.",
      );
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    }
  }

  if (!reservations.length) {
    return (
      <EmptyState
        title="Chưa có phụ tùng đặt trước"
        description="Reservation làm giảm available nhưng không giảm on-hand."
      />
    );
  }
  return (
    <div className="space-y-3">
      {reservations.map((item) => (
        <div key={item.id} className="rounded-md border p-3">
          <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-center">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs font-semibold">
                  {item.reservation_number}
                </span>
                <InventoryStatusBadge
                  status={item.status}
                  label={item.status_display}
                />
              </div>
              <p className="mt-1 text-sm font-medium">
                {item.part_name_vi} · {item.stock_location_name}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Còn {item.remaining_quantity} / {item.quantity} · hết hạn{" "}
                {formatTimestamp(item.expires_at)}
              </p>
            </div>
            {auth.can(permissions.inventoryReserve) &&
              ["active", "partially_issued"].includes(item.status) && (
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={action.isPending}
                    onClick={() => void close(item, "release")}
                  >
                    Giải phóng
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={action.isPending}
                    onClick={() => void close(item, "expire")}
                  >
                    Hết hạn
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={action.isPending}
                    onClick={() =>
                      setReplacementId((current) =>
                        current === item.id ? null : item.id,
                      )
                    }
                  >
                    Thay thế
                  </Button>
                </div>
              )}
          </div>
          {replacementId === item.id && (
            <ReplaceReservationForm
              workOrderId={workOrderId}
              reservation={item}
              locations={locations}
              onDone={() => setReplacementId(null)}
            />
          )}
        </div>
      ))}
      {message && (
        <p
          role="status"
          className="rounded-md bg-blue-50 p-3 text-sm text-blue-800"
        >
          {message}
        </p>
      )}
    </div>
  );
}

function ReplaceReservationForm({
  workOrderId,
  reservation,
  locations,
  onDone,
}: {
  workOrderId: string;
  reservation: Reservation;
  locations: LocationOption[];
  onDone: () => void;
}) {
  const mutation = useReplaceReservationMutation(workOrderId);
  const key = useRef(createInventoryIdempotencyKey("replace-reservation"));
  const [locationId, setLocationId] = useState(reservation.stock_location_id);
  const [quantity, setQuantity] = useState(
    String(reservation.remaining_quantity),
  );
  const [reason, setReason] = useState("Thay thế nguồn giữ vật tư cho work order");
  const [message, setMessage] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      await mutation.mutateAsync({
        reservationId: reservation.id,
        request: {
          quantity: Number(quantity),
          stock_location_id: locationId,
          expected_version: reservation.version,
          expires_at: reservation.expires_at,
          reason: reason.trim(),
        },
        idempotencyKey: key.current,
      });
      key.current = createInventoryIdempotencyKey("replace-reservation");
      setMessage("Đã thay đổi vị trí đặt trước.");
      onDone();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    }
  }

  return (
    <form
      onSubmit={submit}
      className="border-t pt-3 lg:col-span-2 lg:min-w-[520px]"
    >
      <div className="grid gap-2 sm:grid-cols-[1.2fr_0.7fr_1.5fr_auto] sm:items-end">
        <Field id={`replace-location-${reservation.id}`} label="Kho thay thế">
          <Select value={locationId} onValueChange={setLocationId}>
            <SelectTrigger
              id={`replace-location-${reservation.id}`}
              className="w-full"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {locations.map((location) => (
                <SelectItem key={location.id} value={location.id}>
                  {location.code} · {location.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field id={`replace-quantity-${reservation.id}`} label="Số lượng">
          <Input
            id={`replace-quantity-${reservation.id}`}
            required
            type="number"
            min={0.001}
            step="0.001"
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
          />
        </Field>
        <Field id={`replace-reason-${reservation.id}`} label="Lý do">
          <Input
            id={`replace-reason-${reservation.id}`}
            required
            minLength={3}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </Field>
        <Button
          type="submit"
          size="sm"
          disabled={
            mutation.isPending ||
            !locationId ||
            !quantity ||
            !reason.trim()
          }
        >
          Xác nhận
        </Button>
      </div>
      {message && (
        <p role="status" className="mt-2 text-xs text-blue-800">
          {message}
        </p>
      )}
    </form>
  );
}
