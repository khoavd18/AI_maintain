"use client";

import { useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import {
  useConsumeStockMutation,
  useInventoryBalancesQuery,
  useIssueStockMutation,
  useReturnStockMutation,
} from "@/hooks/use-inventory";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { PartIssue } from "@/lib/api/inventory-schemas";
import { permissions } from "@/lib/auth";
import { formatTimestamp } from "@/lib/formatters";
import {
  createInventoryIdempotencyKey,
  formatQuantity,
} from "@/lib/inventory";

import { Field, SubmitFooter } from "../components/section-state";
import { SummaryFact } from "../components/quantity-display";
import { PartSelect } from "../selectors/inventory-item-selector";
import { LocationSelect } from "../selectors/warehouse-selector";
import type { LocationOption, PartOption } from "../types";

export function IssueCard({
  workOrderId,
  issue,
  locations,
}: {
  workOrderId: string;
  issue: PartIssue;
  locations: LocationOption[];
}) {
  const auth = useAuth();
  const consume = useConsumeStockMutation(workOrderId);
  const returnPart = useReturnStockMutation(workOrderId);
  const consumeKey = useRef(createInventoryIdempotencyKey("consume"));
  const returnKey = useRef(createInventoryIdempotencyKey("return"));
  const [consumeQuantity, setConsumeQuantity] = useState("");
  const [returnQuantity, setReturnQuantity] = useState("");
  const [returnLocation, setReturnLocation] = useState(issue.stock_location_id);
  const [message, setMessage] = useState<string | null>(null);

  async function recordConsumption() {
    try {
      await consume.mutateAsync({
        issueId: issue.id,
        request: {
          quantity: Number(consumeQuantity),
          consumed_at: null,
          note: "Kỹ thuật viên xác nhận sử dụng tại work order",
        },
        idempotencyKey: consumeKey.current,
      });
      consumeKey.current = createInventoryIdempotencyKey("consume");
      setConsumeQuantity("");
      setMessage("Đã ghi nhận consumption; tồn kho không bị trừ lần thứ hai.");
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    }
  }

  async function recordReturn() {
    try {
      await returnPart.mutateAsync({
        issueId: issue.id,
        request: {
          stock_location_id: returnLocation,
          quantity: Number(returnQuantity),
          returned_at: null,
          reason: "Hoàn trả vật tư chưa sử dụng từ work order",
        },
        idempotencyKey: returnKey.current,
      });
      returnKey.current = createInventoryIdempotencyKey("return");
      setReturnQuantity("");
      setMessage("Đã hoàn trả vật tư và ghi movement append-only.");
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    }
  }

  return (
    <article className="rounded-md border p-3">
      <div className="flex flex-col justify-between gap-3 lg:flex-row">
        <div>
          <p className="font-medium">{issue.part_name_vi}</p>
          <p className="mt-0.5 font-mono text-xs text-muted-foreground">
            {issue.issue_number} · {issue.part_number}
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            Xuất {formatQuantity(issue.quantity, issue.unit_symbol)} · đã dùng{" "}
            {formatQuantity(issue.consumed_quantity, issue.unit_symbol)} · hoàn{" "}
            {formatQuantity(issue.returned_quantity, issue.unit_symbol)}
          </p>
        </div>
        <div className="text-left text-xs lg:text-right">
          <p className="font-medium">
            Chưa quyết toán{" "}
            {formatQuantity(issue.outstanding_quantity, issue.unit_symbol)}
          </p>
          <p className="mt-1 text-muted-foreground">
            {issue.stock_location_name} · {formatTimestamp(issue.issued_at)}
          </p>
        </div>
      </div>

      {issue.outstanding_quantity > 0 && (
        <div className="mt-3 grid gap-3 border-t pt-3 lg:grid-cols-2">
          {auth.can(permissions.inventoryConsume) && (
            <div className="rounded-md bg-neutral-50 p-3">
              <Label htmlFor={`consume-${issue.id}`}>
                Xác nhận đã sử dụng ({issue.unit_symbol})
              </Label>
              <div className="mt-2 flex gap-2">
                <Input
                  id={`consume-${issue.id}`}
                  type="number"
                  min={0.001}
                  max={issue.outstanding_quantity}
                  step="0.001"
                  value={consumeQuantity}
                  onChange={(event) => setConsumeQuantity(event.target.value)}
                />
                <Button
                  type="button"
                  size="sm"
                  disabled={
                    consume.isPending ||
                    !consumeQuantity ||
                    Number(consumeQuantity) <= 0
                  }
                  onClick={() => void recordConsumption()}
                >
                  Ghi dùng
                </Button>
              </div>
            </div>
          )}
          {auth.can(permissions.inventoryReturn) && (
            <div className="rounded-md bg-neutral-50 p-3">
              <Label htmlFor={`return-${issue.id}`}>
                Hoàn vật tư ({issue.unit_symbol})
              </Label>
              <div className="mt-2 grid gap-2 sm:grid-cols-[1fr_1.4fr_auto]">
                <Input
                  id={`return-${issue.id}`}
                  type="number"
                  min={0.001}
                  max={issue.outstanding_quantity}
                  step="0.001"
                  value={returnQuantity}
                  onChange={(event) => setReturnQuantity(event.target.value)}
                />
                <Select
                  value={returnLocation}
                  onValueChange={setReturnLocation}
                >
                  <SelectTrigger aria-label="Kho nhận vật tư hoàn">
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
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={
                    returnPart.isPending ||
                    !returnQuantity ||
                    !returnLocation ||
                    Number(returnQuantity) <= 0
                  }
                  onClick={() => void recordReturn()}
                >
                  Hoàn kho
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {message && (
        <p
          role="status"
          className="mt-3 rounded-md bg-blue-50 p-2 text-xs text-blue-800"
        >
          {message}
        </p>
      )}
    </article>
  );
}

export function IssueForm({
  workOrderId,
  assignedToUserId,
  parts,
  locations,
  reservations,
}: {
  workOrderId: string;
  assignedToUserId: string | null;
  parts: PartOption[];
  locations: LocationOption[];
  reservations: import("@/lib/api/inventory-schemas").Reservation[];
}) {
  const auth = useAuth();
  const eligibleReservations = reservations.filter((item) =>
    ["active", "partially_issued"].includes(item.status),
  );
  const mutation = useIssueStockMutation(workOrderId);
  const key = useRef(createInventoryIdempotencyKey("issue"));
  const [reservationId, setReservationId] = useState("none");
  const [partId, setPartId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const selectedReservation = eligibleReservations.find(
    (item) => item.id === reservationId,
  );
  const effectivePartId = selectedReservation?.part_id ?? partId;
  const effectiveLocationId =
    selectedReservation?.stock_location_id ?? locationId;
  const selectedPart = parts.find((item) => item.id === effectivePartId);
  const balances = useInventoryBalancesQuery(
    {
      search: selectedPart?.part_number,
      stock_location_id: effectiveLocationId || undefined,
      page: 1,
      page_size: 20,
    },
    Boolean(selectedPart && effectiveLocationId),
  );
  const currentBalance = balances.data?.items.find(
    (item) =>
      item.part_id === effectivePartId &&
      item.stock_location_id === effectiveLocationId,
  );
  const requestedQuantity = Number(quantity) || 0;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      await mutation.mutateAsync({
        request: {
          part_id: effectivePartId,
          stock_location_id: effectiveLocationId,
          quantity: Number(quantity),
          requirement_id: selectedReservation?.requirement_id ?? null,
          reservation_id: selectedReservation?.id ?? null,
          issued_to_user_id: assignedToUserId,
          issued_at: null,
          reason: reason.trim(),
        },
        idempotencyKey: key.current,
      });
      key.current = createInventoryIdempotencyKey("issue");
      setReservationId("none");
      setPartId("");
      setLocationId("");
      setQuantity("");
      setReason("");
      setMessage(
        "Đã xuất kho. Kỹ thuật viên cần xác nhận số lượng thực tế đã sử dụng.",
      );
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    }
  }
  return (
    <div className="rounded-md border p-4">
      <h3 className="font-medium">Xuất phụ tùng</h3>
      <p className="mb-4 mt-1 text-xs text-muted-foreground">
        Kiểm tra số lượng và người nhận trước khi xác nhận.
      </p>
      <form onSubmit={submit} className="space-y-3">
        <Field
          id="issue-reservation"
          label="Đặt trước liên quan (tùy chọn)"
        >
          <Select value={reservationId} onValueChange={setReservationId}>
            <SelectTrigger id="issue-reservation" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">Xuất trực tiếp</SelectItem>
              {eligibleReservations.map((item) => (
                <SelectItem key={item.id} value={item.id}>
                  {item.reservation_number} · {item.part_number} · còn{" "}
                  {item.remaining_quantity}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        {!selectedReservation && (
          <>
            <PartSelect
              id="issue-part"
              value={partId}
              onChange={setPartId}
              parts={parts}
            />
            <LocationSelect
              id="issue-location"
              value={locationId}
              onChange={setLocationId}
              locations={locations}
            />
          </>
        )}
        <Field id="issue-quantity" label="Số lượng xuất">
          <Input
            id="issue-quantity"
            required
            type="number"
            min={0.001}
            max={selectedReservation?.remaining_quantity}
            step="0.001"
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
          />
        </Field>
        <Field id="issue-reason" label="Lý do xuất">
          <Textarea
            id="issue-reason"
            required
            minLength={3}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </Field>
        {!assignedToUserId && (
          <p className="rounded-md bg-amber-50 p-2 text-xs text-amber-900">
            Lệnh công việc chưa được phân công nên chưa thể xác định người nhận.
          </p>
        )}
        {currentBalance && requestedQuantity > 0 && (
          <section
            aria-label="Tóm tắt xuất kho"
            className="rounded-lg border bg-muted/30 p-3"
          >
            <h3 className="text-sm font-semibold">Kiểm tra trước khi xuất</h3>
            <dl className="mt-3 grid gap-3 sm:grid-cols-2">
              <SummaryFact
                label="Tồn hiện tại"
                value={formatQuantity(
                  currentBalance.on_hand_quantity,
                  currentBalance.unit_symbol,
                )}
              />
              <SummaryFact
                label="Số lượng xuất"
                value={formatQuantity(
                  requestedQuantity,
                  currentBalance.unit_symbol,
                )}
              />
              <SummaryFact
                label="Tồn sau khi xuất"
                value={formatQuantity(
                  currentBalance.on_hand_quantity - requestedQuantity,
                  currentBalance.unit_symbol,
                )}
              />
              <SummaryFact label="Lệnh công việc" value="Lệnh hiện tại" />
              <SummaryFact
                label="Người thực hiện"
                value={auth.user?.display_name ?? "Người dùng hiện tại"}
              />
            </dl>
            <p className="mt-3 text-xs text-muted-foreground">
              Hệ thống sẽ kiểm tra lại tồn kho và số đã đặt trước khi ghi giao
              dịch.
            </p>
          </section>
        )}
        <SubmitFooter
          mutationError={mutation.error}
          message={message}
          pending={mutation.isPending}
          disabled={!effectivePartId || !effectiveLocationId || !reason.trim()}
          label="Xác nhận xuất kho"
        />
      </form>
    </div>
  );
}
