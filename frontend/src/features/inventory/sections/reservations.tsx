"use client";

import Link from "next/link";
import { useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { InventoryStatusBadge } from "@/components/inventory-badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ErrorState,
  EmptyState,
  LoadingSkeleton,
  RetryButton,
} from "@/components/ui-states";
import {
  useInventoryOptionsQuery,
  useInventoryReservationsQuery,
  useReservationActionMutation,
} from "@/hooks/use-inventory";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { Reservation } from "@/lib/api/inventory-schemas";
import { permissions } from "@/lib/auth";
import {
  inventoryStatusCatalog,
  resolveStatusPresentation,
} from "@/lib/status-terminology";
import { createInventoryIdempotencyKey } from "@/lib/inventory";

import { FilterSelect, Pagination, SectionHeading } from "../components/inventory-controls";

const all = "all";
const pageSize = 20;

export function ReservationWorkspace() {
  const auth = useAuth();
  const [status, setStatus] = useState(all);
  const [page, setPage] = useState(1);
  const [message, setMessage] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<{
    reservation: Reservation;
    target: "release" | "expire";
  } | null>(null);
  const [actionReason, setActionReason] = useState("");
  const options = useInventoryOptionsQuery();
  const query = useInventoryReservationsQuery({
    status: status === all ? undefined : status,
    page,
    page_size: pageSize,
  });
  const action = useReservationActionMutation();

  function requestCloseReservation(
    reservation: Reservation,
    target: "release" | "expire",
  ) {
    setPendingAction({ reservation, target });
    setActionReason("");
    setMessage(null);
  }

  async function closeReservation() {
    if (!pendingAction || actionReason.trim().length < 3) return;
    const { reservation, target } = pendingAction;
    try {
      await action.mutateAsync({
        reservationId: reservation.id,
        action: target,
        request: {
          expected_version: reservation.version,
          reason: actionReason.trim(),
        },
        idempotencyKey: createInventoryIdempotencyKey(target),
      });
      setMessage(
        target === "release"
          ? "Đã giải phóng số lượng đặt trước."
          : "Đã ghi nhận yêu cầu đặt trước hết hạn.",
      );
      setPendingAction(null);
      setActionReason("");
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    }
  }

  return (
    <div className="space-y-4">
      <section className="rounded-lg border bg-white p-3 sm:p-4">
        <FilterSelect
          label="Trạng thái đặt trước"
          value={status}
          onChange={(value) => {
            setStatus(value);
            setPage(1);
          }}
          options={(options.data?.reservation_statuses ?? []).map((item) => ({
            ...item,
            display_name: resolveStatusPresentation(
              inventoryStatusCatalog,
              item.code,
              item.display_name,
            ).label,
          }))}
        />
      </section>
      {message && (
        <p role="status" className="rounded-lg bg-blue-50 p-3 text-sm text-blue-900">
          {message}
        </p>
      )}
      {pendingAction && (
        <section
          aria-labelledby="reservation-action-title"
          className="rounded-lg border border-amber-200 bg-amber-50 p-4"
        >
          <h2 id="reservation-action-title" className="font-semibold text-amber-950">
            {pendingAction.target === "release"
              ? "Giải phóng phụ tùng đặt trước"
              : "Đánh dấu đặt trước đã hết hạn"}
          </h2>
          <p className="mt-1 text-sm text-amber-900/80">
            {pendingAction.reservation.reservation_number} · {pendingAction.reservation.part_number}
          </p>
          <div className="mt-3 max-w-xl space-y-1.5">
            <Label htmlFor="reservation-action-reason">Lý do</Label>
            <Input
              id="reservation-action-reason"
              value={actionReason}
              maxLength={1000}
              autoFocus
              onChange={(event) => setActionReason(event.target.value)}
              placeholder="Nhập ít nhất 3 ký tự"
            />
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setPendingAction(null);
                setActionReason("");
              }}
            >
              Hủy
            </Button>
            <Button
              type="button"
              disabled={action.isPending || actionReason.trim().length < 3}
              onClick={() => void closeReservation()}
            >
              {action.isPending ? "Đang xử lý…" : "Xác nhận"}
            </Button>
          </div>
        </section>
      )}
      <section className="rounded-lg border bg-white">
        <SectionHeading
          title="Danh sách đặt trước"
          description="Release và expire là named actions; không có hidden scheduler."
        />
        {query.isPending ? (
          <div className="p-4">
            <LoadingSkeleton />
          </div>
        ) : query.isError ? (
          <ErrorState
            title="Chưa tải được danh sách đặt trước"
            description={getApiErrorMessage(query.error)}
            action={<RetryButton onClick={() => void query.refetch()} />}
          />
        ) : !query.data?.items.length ? (
          <EmptyState
            title="Không có phụ tùng đặt trước"
            description="Chưa có yêu cầu phù hợp với bộ lọc."
          />
        ) : (
          <>
            <div className="grid gap-3 p-3 md:hidden">
              {query.data.items.map((item) => (
                <article key={item.id} className="rounded-lg border p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-mono text-xs font-semibold text-primary">
                        {item.reservation_number}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        Lần đặt trước {item.occurrence_number}
                      </p>
                    </div>
                    <InventoryStatusBadge
                      status={item.status}
                      label={item.status_display}
                    />
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <p className="text-xs text-muted-foreground">Phụ tùng / kho</p>
                      <p className="mt-1 font-medium">{item.part_number}</p>
                      <p className="text-xs text-muted-foreground">
                        {item.stock_location_code}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Còn đặt trước</p>
                      <p className="mt-1 font-semibold tabular-nums">
                        {item.remaining_quantity.toLocaleString("vi-VN")} /{" "}
                        {item.quantity.toLocaleString("vi-VN")}
                      </p>
                    </div>
                  </div>
                  <Link
                    href={`/work-orders/${item.work_order_id}`}
                    className="mt-3 block font-mono text-xs font-semibold text-primary hover:underline"
                  >
                    {item.work_order_number}
                  </Link>
                  {auth.can(permissions.inventoryReserve) &&
                    ["active", "partially_issued"].includes(item.status) && (
                      <div className="mt-3 grid grid-cols-2 gap-2 border-t pt-3">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={action.isPending}
                          onClick={() => requestCloseReservation(item, "release")}
                        >
                          Giải phóng
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          disabled={action.isPending}
                          onClick={() => requestCloseReservation(item, "expire")}
                        >
                          Hết hạn
                        </Button>
                      </div>
                    )}
                </article>
              ))}
            </div>
            <div className="hidden overflow-x-auto md:block">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Mã đặt trước</TableHead>
                    <TableHead>Lệnh công việc</TableHead>
                    <TableHead>Vật tư / kho</TableHead>
                    <TableHead>Số lượng</TableHead>
                    <TableHead>Trạng thái</TableHead>
                    <TableHead className="text-right">Thao tác</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {query.data.items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>
                        <p className="font-mono text-xs font-semibold">{item.reservation_number}</p>
                        <p className="mt-1 text-xs text-muted-foreground">Lần {item.occurrence_number}</p>
                      </TableCell>
                      <TableCell>
                        <Link
                          href={`/work-orders/${item.work_order_id}`}
                          className="font-mono text-xs font-semibold text-primary hover:underline"
                        >
                          {item.work_order_number}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <p className="text-sm font-medium">{item.part_number}</p>
                        <p className="text-xs text-muted-foreground">{item.stock_location_code}</p>
                      </TableCell>
                      <TableCell className="tabular-nums">
                        <p>{item.remaining_quantity.toLocaleString("vi-VN")}</p>
                        <p className="text-xs text-muted-foreground">/ {item.quantity.toLocaleString("vi-VN")}</p>
                      </TableCell>
                      <TableCell>
                        <InventoryStatusBadge status={item.status} label={item.status_display} />
                      </TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-1">
                          {auth.can(permissions.inventoryReserve) &&
                            ["active", "partially_issued"].includes(item.status) && (
                              <>
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  disabled={action.isPending}
                                  onClick={() => requestCloseReservation(item, "release")}
                                >
                                  Giải phóng
                                </Button>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="sm"
                                  disabled={action.isPending}
                                  onClick={() => requestCloseReservation(item, "expire")}
                                >
                                  Hết hạn
                                </Button>
                              </>
                            )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <Pagination
              page={page}
              totalPages={query.data.total_pages}
              onPage={setPage}
            />
          </>
        )}
      </section>
    </div>
  );
}
