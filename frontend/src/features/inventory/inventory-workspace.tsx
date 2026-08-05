"use client";

import Link from "next/link";
import {
  AlertTriangle,
  Boxes,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  PackageCheck,
  RefreshCw,
  RotateCcw,
  Search,
} from "lucide-react";
import { useDeferredValue, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import {
  InventoryStatusBadge,
  StockStateBadge,
} from "@/components/inventory-badges";
import { InventorySectionNav } from "@/components/inventory-section-nav";
import { KpiCard } from "@/components/kpi-card";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
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
  EmptyState,
  ErrorState,
  LoadingSkeleton,
  RetryButton,
} from "@/components/ui-states";
import {
  useInventoryBalancesQuery,
  useInventoryCategoriesQuery,
  useCreateLocationMutation,
  useInventoryLocationsQuery,
  useInventoryMetricsQuery,
  useInventoryMovementsQuery,
  useInventoryOptionsQuery,
  useInventoryReservationsQuery,
  useInventoryUnitsQuery,
  useLowStockQuery,
  useReservationActionMutation,
  useStockLocationLifecycleMutation,
} from "@/hooks/use-inventory";
import { getApiErrorMessage } from "@/lib/api/errors";
import type {
  InventoryBalance,
  InventoryMovement,
  Reservation,
  StockLocation,
} from "@/lib/api/inventory-schemas";
import { permissions } from "@/lib/auth";
import {
  inventoryStatusCatalog,
  resolveStatusPresentation,
  stockStateStatusCatalog,
} from "@/lib/status-terminology";
import { formatTimestamp } from "@/lib/formatters";
import {
  createInventoryIdempotencyKey,
  formatQuantity,
} from "@/lib/inventory";

export type InventoryWorkspaceView =
  | "overview"
  | "stock"
  | "low-stock"
  | "movements"
  | "reservations"
  | "settings";

const all = "all";
const pageSize = 20;
const movementTypeLabels: Record<string, string> = {
  opening_balance: "Số dư ban đầu",
  receipt: "Nhập kho",
  issue: "Xuất kho",
  return: "Trả kho",
  transfer_out: "Điều chuyển đi",
  transfer_in: "Điều chuyển đến",
  adjustment_increase: "Điều chỉnh tăng",
  adjustment_decrease: "Điều chỉnh giảm",
  damaged_scrapped: "Hư hỏng hoặc loại bỏ",
};

const titles: Record<
  InventoryWorkspaceView,
  { title: string; description: string }
> = {
  overview: {
    title: "Kho phụ tùng",
    description: "Theo dõi số lượng khả dụng, phụ tùng sắp hết và nhu cầu cho công việc.",
  },
  stock: {
    title: "Tồn kho",
    description: "Xem số lượng thực tế, đã đặt trước và còn có thể sử dụng tại từng kho.",
  },
  "low-stock": {
    title: "Phụ tùng sắp hết",
    description: "Ưu tiên các mã đã xuống dưới mức tồn tối thiểu hoặc đã hết hàng.",
  },
  movements: {
    title: "Lịch sử kho",
    description: "Tra cứu các lần nhập, xuất, trả, điều chuyển và điều chỉnh.",
  },
  reservations: {
    title: "Đặt trước phụ tùng",
    description: "Theo dõi phụ tùng đã dành cho lệnh công việc và xử lý yêu cầu còn mở.",
  },
  settings: {
    title: "Thiết lập kho",
    description: "Quản lý phân loại, đơn vị tính và các vị trí lưu kho.",
  },
};

export function InventoryWorkspace({
  view,
}: {
  view: InventoryWorkspaceView;
}) {
  const heading = titles[view];
  return (
    <div>
      <PageHeader
        title={heading.title}
        description={heading.description}
        breadcrumbs={[
          { label: "Tổng quan", href: "/" },
          { label: "Kho phụ tùng" },
        ]}
      />
      <InventorySectionNav />
      {view === "overview" && <InventoryOverview />}
      {view === "stock" && <BalanceWorkspace lowStockOnly={false} />}
      {view === "low-stock" && <BalanceWorkspace lowStockOnly />}
      {view === "movements" && <MovementWorkspace />}
      {view === "reservations" && <ReservationWorkspace />}
      {view === "settings" && <InventorySettings />}
    </div>
  );
}

function InventoryOverview() {
  const metrics = useInventoryMetricsQuery();
  const lowStock = useLowStockQuery({ page: 1, page_size: 6 });
  const movements = useInventoryMovementsQuery({ page: 1, page_size: 8 });
  const error = metrics.error ?? lowStock.error ?? movements.error;
  if (metrics.isPending || lowStock.isPending || movements.isPending) {
    return <LoadingSkeleton />;
  }
  if (error || !metrics.data) {
    return (
      <ErrorState
        title="Chưa tải được tổng quan kho"
        description={getApiErrorMessage(error)}
        action={
          <RetryButton
            onClick={() =>
              void Promise.all([
                metrics.refetch(),
                lowStock.refetch(),
                movements.refetch(),
              ])
            }
          />
        }
      />
    );
  }
  const data = metrics.data;
  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Mã phụ tùng đang dùng"
          value={String(data.total_active_parts)}
          detail="Trong danh mục hiện tại"
          icon={Boxes}
          tone="blue"
        />
        <KpiCard
          label="Đã đặt trước"
          value={data.total_reserved_units.toLocaleString("vi-VN")}
          detail="Dành cho lệnh công việc"
          icon={PackageCheck}
          tone="amber"
        />
        <KpiCard
          label="Sắp hết hoặc hết"
          value={String(data.low_stock_parts + data.out_of_stock_parts)}
          detail={`${data.out_of_stock_parts} mã hết hàng`}
          icon={AlertTriangle}
          tone="red"
        />
        <KpiCard
          label="Công việc chờ phụ tùng"
          value={String(data.work_orders_waiting_for_parts)}
          detail={`${data.open_shortages} nhu cầu còn thiếu`}
          icon={ClipboardList}
          tone="orange"
        />
      </div>

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(300px,0.65fr)]">
        <section className="rounded-lg border bg-white">
          <SectionHeading
            title="Cần chú ý"
            description="Các mã cần kiểm tra hoặc bổ sung trước."
            action={
              <Button asChild variant="outline" size="sm">
                <Link href="/inventory/low-stock">Mở hàng đợi</Link>
              </Button>
            }
          />
          <BalanceTable rows={lowStock.data?.items ?? []} />
        </section>
        <section className="rounded-lg border bg-white">
          <SectionHeading
            title="Loại biến động"
            description="Số lần nhập, xuất, trả và điều chuyển."
          />
          <MovementBars counts={data.movements_by_type} />
        </section>
      </div>

      <section className="rounded-lg border bg-white">
        <SectionHeading
          title="Biến động gần đây"
          description="Các thay đổi số lượng mới nhất trong kho."
          action={
            <Button asChild variant="outline" size="sm">
              <Link href="/inventory/movements">Xem toàn bộ</Link>
            </Button>
          }
        />
        <MovementTable rows={movements.data?.items ?? []} />
      </section>
      <p className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs text-blue-900">Số lượng khả dụng bằng tồn thực tế trừ số đã đặt trước.</p>
    </div>
  );
}

function BalanceWorkspace({ lowStockOnly }: { lowStockOnly: boolean }) {
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [locationId, setLocationId] = useState(all);
  const [state, setState] = useState(all);
  const [page, setPage] = useState(1);
  const locations = useInventoryLocationsQuery();
  const options = useInventoryOptionsQuery();
  const filters = {
    search: deferredSearch || undefined,
    stock_location_id: locationId === all ? undefined : locationId,
    stock_state: !lowStockOnly && state !== all ? state : undefined,
    page,
    page_size: pageSize,
  };
  const lowStockQuery = useLowStockQuery(filters, lowStockOnly);
  const balanceQuery = useInventoryBalancesQuery(filters, !lowStockOnly);
  const query = lowStockOnly ? lowStockQuery : balanceQuery;

  function reset() {
    setSearch("");
    setLocationId(all);
    setState(all);
    setPage(1);
  }

  return (
    <div className="space-y-4">
      <section className="rounded-lg border bg-white p-3 sm:p-4">
        <div className="grid gap-3 lg:grid-cols-[minmax(220px,1fr)_220px_200px_auto] lg:items-end">
          <div className="space-y-1.5">
            <Label htmlFor="inventory-balance-search">Tìm vật tư</Label>
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <Input
                id="inventory-balance-search"
                className="pl-8"
                value={search}
                placeholder="Mã hoặc tên vật tư"
                onChange={(event) => {
                  setSearch(event.target.value);
                  setPage(1);
                }}
              />
            </div>
          </div>
          <FilterSelect
            label="Vị trí kho"
            value={locationId}
            onChange={(value) => {
              setLocationId(value);
              setPage(1);
            }}
            options={(locations.data ?? []).map((item) => ({
              code: item.id,
              display_name: `${item.code} · ${item.name}`,
            }))}
          />
          {!lowStockOnly && (
            <FilterSelect
              label="Trạng thái tồn"
              value={state}
              onChange={(value) => {
                setState(value);
                setPage(1);
              }}
              options={(options.data?.stock_states ?? []).map((item) => ({
                ...item,
                display_name: resolveStatusPresentation(
                  stockStateStatusCatalog,
                  item.code,
                  item.display_name,
                ).label,
              }))}
            />
          )}
          <Button type="button" variant="outline" onClick={reset}>
            <RotateCcw aria-hidden="true" />
            Đặt lại
          </Button>
        </div>
      </section>
      <section className="rounded-lg border bg-white">
        <SectionHeading
          title={lowStockOnly ? "Mã cần bổ sung" : "Số lượng theo vị trí"}
          description={
            query.data
              ? `${query.data.total} vị trí tồn kho`
              : "Đang đọc dữ liệu"
          }
          action={
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void query.refetch()}
            >
              <RefreshCw aria-hidden="true" />
              Làm mới
            </Button>
          }
        />
        {query.isPending ? (
          <div className="p-4">
            <LoadingSkeleton />
          </div>
        ) : query.isError ? (
          <ErrorState
            title="Chưa tải được tồn kho"
            description={getApiErrorMessage(query.error)}
            action={<RetryButton onClick={() => void query.refetch()} />}
          />
        ) : (
          <>
            <BalanceTable rows={query.data?.items ?? []} />
            <Pagination
              page={page}
              totalPages={query.data?.total_pages ?? 0}
              onPage={setPage}
            />
          </>
        )}
      </section>
    </div>
  );
}

function MovementWorkspace() {
  const [type, setType] = useState(all);
  const [locationId, setLocationId] = useState(all);
  const [page, setPage] = useState(1);
  const options = useInventoryOptionsQuery();
  const locations = useInventoryLocationsQuery();
  const query = useInventoryMovementsQuery({
    movement_type: type === all ? undefined : type,
    stock_location_id: locationId === all ? undefined : locationId,
    page,
    page_size: pageSize,
  });
  return (
    <div className="space-y-4">
      <section className="rounded-lg border bg-white p-3 sm:p-4">
        <div className="flex flex-wrap items-end gap-3">
          <FilterSelect
            label="Loại biến động"
            value={type}
            onChange={(value) => {
              setType(value);
              setPage(1);
            }}
            options={options.data?.movement_types ?? []}
          />
          <FilterSelect
            label="Vị trí kho"
            value={locationId}
            onChange={(value) => {
              setLocationId(value);
              setPage(1);
            }}
            options={(locations.data ?? []).map((item) => ({
              code: item.id,
              display_name: `${item.code} · ${item.name}`,
            }))}
          />
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setType(all);
              setLocationId(all);
              setPage(1);
            }}
          >
            <RotateCcw aria-hidden="true" />
            Đặt lại
          </Button>
        </div>
      </section>
      <section className="rounded-lg border bg-white">
        <SectionHeading
          title="Lịch sử biến động"
          description={`${query.data?.total ?? 0} lần thay đổi; lịch sử không thể sửa hoặc xóa.`}
        />
        {query.isPending ? (
          <div className="p-4">
            <LoadingSkeleton />
          </div>
        ) : query.isError ? (
          <ErrorState
            title="Chưa tải được lịch sử kho"
            description={getApiErrorMessage(query.error)}
            action={<RetryButton onClick={() => void query.refetch()} />}
          />
        ) : (
          <>
            <MovementTable rows={query.data?.items ?? []} />
            <Pagination
              page={page}
              totalPages={query.data?.total_pages ?? 0}
              onPage={setPage}
            />
          </>
        )}
      </section>
    </div>
  );
}

function ReservationWorkspace() {
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
                        <p className="font-mono text-xs font-semibold">
                          {item.reservation_number}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Lần {item.occurrence_number}
                        </p>
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
                        <p className="text-xs text-muted-foreground">
                          {item.stock_location_code}
                        </p>
                      </TableCell>
                      <TableCell className="tabular-nums">
                        <p>{item.remaining_quantity.toLocaleString("vi-VN")}</p>
                        <p className="text-xs text-muted-foreground">
                          / {item.quantity.toLocaleString("vi-VN")}
                        </p>
                      </TableCell>
                      <TableCell>
                        <InventoryStatusBadge
                          status={item.status}
                          label={item.status_display}
                        />
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
                                  onClick={() =>
                                    requestCloseReservation(item, "release")
                                  }
                                >
                                  Giải phóng
                                </Button>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="sm"
                                  disabled={action.isPending}
                                  onClick={() =>
                                    requestCloseReservation(item, "expire")
                                  }
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

function InventorySettings() {
  const auth = useAuth();
  const categories = useInventoryCategoriesQuery();
  const units = useInventoryUnitsQuery();
  const locations = useInventoryLocationsQuery(true);
  const options = useInventoryOptionsQuery();
  const error =
    categories.error ?? units.error ?? locations.error ?? options.error;
  if (
    categories.isPending ||
    units.isPending ||
    locations.isPending ||
    options.isPending
  ) {
    return <LoadingSkeleton />;
  }
  if (error) {
    return (
      <ErrorState
        title="Chưa tải được thiết lập kho"
        description={getApiErrorMessage(error)}
        action={
          <RetryButton
            onClick={() =>
              void Promise.all([
                categories.refetch(),
                units.refetch(),
                locations.refetch(),
                options.refetch(),
              ])
            }
          />
        }
      />
    );
  }
  return (
    <div className="grid items-start gap-5 xl:grid-cols-3">
      <ReferenceList
        title="Nhóm phụ tùng"
        items={(categories.data ?? []).map((item) => ({
          code: item.code,
          name: item.name_vi,
          detail: item.name_en ?? "Không có tên tiếng Anh",
          active: item.is_active,
        }))}
      />
      <ReferenceList
        title="Đơn vị tính"
        items={(units.data ?? []).map((item) => ({
          code: item.code,
          name: item.name_vi,
          detail: `${item.symbol} · precision ${item.quantity_precision}`,
          active: item.is_active,
        }))}
      />
      <StockLocationSettings
        locations={locations.data ?? []}
        locationTypes={options.data?.stock_location_types ?? []}
        canManage={auth.can(permissions.inventoryLocationsManage)}
      />
    </div>
  );
}

function StockLocationSettings({
  locations,
  locationTypes,
  canManage,
}: {
  locations: StockLocation[];
  locationTypes: Array<{ code: string; display_name: string }>;
  canManage: boolean;
}) {
  const create = useCreateLocationMutation();
  const [showCreate, setShowCreate] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState({
    code: "",
    name: "",
    location_type: "",
    description: "",
  });
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      await create.mutateAsync({
        code: form.code.trim(),
        name: form.name.trim(),
        location_type: form.location_type as
          | "main_store"
          | "engineering_store"
          | "technician_van"
          | "maintenance_room"
          | "quarantine"
          | "other",
        description: form.description.trim() || null,
      });
      setForm({
        code: "",
        name: "",
        location_type: "",
        description: "",
      });
      setShowCreate(false);
      setMessage("Đã tạo vị trí kho.");
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    }
  }
  return (
    <section className="rounded-lg border bg-white xl:col-span-1">
      <SectionHeading
        title="Vị trí kho"
        description={`${locations.length} bản ghi · tách biệt asset location`}
        action={
          canManage ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setShowCreate((current) => !current)}
            >
              {showCreate ? "Đóng" : "Tạo kho"}
            </Button>
          ) : undefined
        }
      />
      {showCreate && (
        <form onSubmit={submit} className="space-y-3 border-b p-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
            <div className="space-y-1.5">
              <Label htmlFor="stock-location-code">Mã kho</Label>
              <Input
                id="stock-location-code"
                required
                minLength={2}
                value={form.code}
                onChange={(event) =>
                  setForm({ ...form, code: event.target.value })
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="stock-location-name">Tên kho</Label>
              <Input
                id="stock-location-name"
                required
                minLength={2}
                value={form.name}
                onChange={(event) =>
                  setForm({ ...form, name: event.target.value })
                }
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="stock-location-type">Loại kho</Label>
            <Select
              value={form.location_type}
              onValueChange={(value) =>
                setForm({ ...form, location_type: value })
              }
            >
              <SelectTrigger id="stock-location-type" className="w-full">
                <SelectValue placeholder="Chọn loại kho" />
              </SelectTrigger>
              <SelectContent>
                {locationTypes.map((type) => (
                  <SelectItem key={type.code} value={type.code}>
                    {type.display_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="stock-location-description">Mô tả</Label>
            <Input
              id="stock-location-description"
              value={form.description}
              onChange={(event) =>
                setForm({ ...form, description: event.target.value })
              }
            />
          </div>
          <Button
            type="submit"
            size="sm"
            className="w-full"
            disabled={
              create.isPending ||
              !form.code.trim() ||
              !form.name.trim() ||
              !form.location_type
            }
          >
            Tạo vị trí kho
          </Button>
        </form>
      )}
      <div className="divide-y">
        {locations.map((location) => (
          <StockLocationRow
            key={location.id}
            location={location}
            canManage={canManage}
          />
        ))}
      </div>
      {(message || create.error) && (
        <p
          role={create.error ? "alert" : "status"}
          className={
            create.error
              ? "m-3 rounded-md bg-red-50 p-2 text-xs text-red-800"
              : "m-3 rounded-md bg-blue-50 p-2 text-xs text-blue-800"
          }
        >
          {create.error ? getApiErrorMessage(create.error) : message}
        </p>
      )}
    </section>
  );
}

function StockLocationRow({
  location,
  canManage,
}: {
  location: StockLocation;
  canManage: boolean;
}) {
  const lifecycle = useStockLocationLifecycleMutation(location.id);
  const [message, setMessage] = useState<string | null>(null);
  const [archiveReason, setArchiveReason] = useState("");
  const [confirmArchive, setConfirmArchive] = useState(false);
  async function change(
    action: "activate" | "deactivate" | "archive" | "restore",
    reason: string | null = null,
  ) {
    try {
      await lifecycle.mutateAsync({
        action,
        expectedVersion: location.version,
        reason,
      });
      setMessage("Đã cập nhật trạng thái vị trí kho.");
      setConfirmArchive(false);
      setArchiveReason("");
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    }
  }
  return (
    <div className="p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-xs font-semibold">{location.code}</p>
          <p className="mt-1 text-sm font-medium">{location.name}</p>
          <p className="mt-1 truncate text-xs text-muted-foreground">
            {location.location_type_display}
          </p>
        </div>
        <InventoryStatusBadge
          status={location.lifecycle_status}
          label={location.lifecycle_status_display}
          context="lifecycle"
        />
      </div>
      {canManage && (
        <div className="mt-3 flex flex-wrap gap-1">
          {location.lifecycle_status === "active" && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={lifecycle.isPending}
              onClick={() => void change("deactivate")}
            >
              Ngừng hoạt động
            </Button>
          )}
          {location.lifecycle_status === "inactive" && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={lifecycle.isPending}
              onClick={() => void change("activate")}
            >
              Kích hoạt
            </Button>
          )}
          {location.lifecycle_status !== "archived" && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={lifecycle.isPending}
              onClick={() => {
                setConfirmArchive(true);
                setArchiveReason("");
                setMessage(null);
              }}
            >
              Lưu trữ
            </Button>
          )}
          {location.lifecycle_status === "archived" && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={lifecycle.isPending}
              onClick={() => void change("restore")}
            >
              Khôi phục
            </Button>
          )}
        </div>
      )}
      {confirmArchive && (
        <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
          <p className="text-sm font-semibold text-amber-950">Lưu trữ vị trí kho</p>
          <p className="mt-1 text-xs text-amber-900/80">
            Vị trí đã lưu trữ không thể dùng cho giao dịch kho mới.
          </p>
          <div className="mt-3 space-y-1.5">
            <Label htmlFor={`archive-location-${location.id}`}>Lý do lưu trữ</Label>
            <Input
              id={`archive-location-${location.id}`}
              value={archiveReason}
              maxLength={1000}
              autoFocus
              onChange={(event) => setArchiveReason(event.target.value)}
              placeholder="Nhập ít nhất 3 ký tự"
            />
          </div>
          <div className="mt-3 flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                setConfirmArchive(false);
                setArchiveReason("");
              }}
            >
              Hủy
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={lifecycle.isPending || archiveReason.trim().length < 3}
              onClick={() => void change("archive", archiveReason.trim())}
            >
              {lifecycle.isPending ? "Đang lưu trữ…" : "Xác nhận lưu trữ"}
            </Button>
          </div>
        </div>
      )}
      {(message || lifecycle.error) && (
        <p role="status" className="mt-2 text-xs text-blue-800">
          {lifecycle.error ? getApiErrorMessage(lifecycle.error) : message}
        </p>
      )}
    </div>
  );
}

function BalanceTable({ rows }: { rows: InventoryBalance[] }) {
  if (!rows.length) {
    return (
      <EmptyState
        title="Chưa có dữ liệu tồn kho"
        description="Chưa có dữ liệu phù hợp với bộ lọc hiện tại."
      />
    );
  }
  return (
    <>
      <div className="grid gap-3 p-3 md:hidden">
        {rows.map((row) => (
          <article key={row.id} className="rounded-lg border p-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <Link
                  href={`/inventory/parts/${row.part_id}`}
                  className="font-mono text-xs font-semibold text-primary"
                >
                  {row.part_number}
                </Link>
                <p className="mt-1 text-sm font-medium">{row.part_name_vi}</p>
              </div>
              <StockStateBadge
                state={row.stock_state}
                label={row.stock_state_display}
              />
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              {row.stock_location_code} · {row.stock_location_name}
            </p>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
              <QuantityTile
                label="Tồn thực tế"
                value={row.on_hand_quantity}
                symbol={row.unit_symbol}
              />
              <QuantityTile
                label="Đã đặt trước"
                value={row.reserved_quantity}
                symbol={row.unit_symbol}
              />
              <QuantityTile
                label="Khả dụng"
                value={row.available_quantity}
                symbol={row.unit_symbol}
              />
            </div>
          </article>
        ))}
      </div>
      <div className="hidden overflow-x-auto md:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Vật tư</TableHead>
              <TableHead>Vị trí kho</TableHead>
              <TableHead className="text-right">Tồn thực tế</TableHead>
              <TableHead className="text-right">Đã đặt trước</TableHead>
              <TableHead className="text-right">Khả dụng</TableHead>
              <TableHead>Trạng thái</TableHead>
              <TableHead className="text-right">Gợi ý bổ sung</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id}>
                <TableCell>
                  <Link
                    href={`/inventory/parts/${row.part_id}`}
                    className="font-mono text-xs font-semibold text-primary hover:underline"
                  >
                    {row.part_number}
                  </Link>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {row.part_name_vi}
                  </p>
                </TableCell>
                <TableCell>
                  <p className="text-sm font-medium">{row.stock_location_code}</p>
                  <p className="text-xs text-muted-foreground">
                    {row.stock_location_name}
                  </p>
                </TableCell>
                <QuantityCell
                  value={row.on_hand_quantity}
                  symbol={row.unit_symbol}
                />
                <QuantityCell
                  value={row.reserved_quantity}
                  symbol={row.unit_symbol}
                />
                <QuantityCell
                  value={row.available_quantity}
                  symbol={row.unit_symbol}
                  strong
                />
                <TableCell>
                  <StockStateBadge
                    state={row.stock_state}
                    label={row.stock_state_display}
                  />
                </TableCell>
                <QuantityCell
                  value={row.suggested_reorder_quantity}
                  symbol={row.unit_symbol}
                />
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </>
  );
}

function MovementTable({ rows }: { rows: InventoryMovement[] }) {
  if (!rows.length) {
    return (
      <EmptyState
        title="Chưa có biến động kho"
        description="Không có biến động kho phù hợp với bộ lọc."
      />
    );
  }
  return (
    <>
      <div className="grid gap-3 p-3 md:hidden">
        {rows.map((row) => (
          <article key={row.id} className="rounded-lg border p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="font-mono text-xs font-semibold text-primary">
                  {row.movement_number}
                </p>
                <p className="mt-1 font-mono text-xs">{row.part_number}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {row.part_name_vi}
                </p>
              </div>
              <Badge variant="outline">{row.movement_type_display}</Badge>
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-3 border-y py-3 text-xs">
              <div>
                <dt className="text-muted-foreground">Vị trí kho</dt>
                <dd className="mt-1 font-medium">{row.stock_location_code}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Số lượng</dt>
                <dd className="mt-1 font-semibold tabular-nums">
                  {formatQuantity(row.quantity, row.unit_symbol)}
                </dd>
              </div>
            </dl>
            <div className="mt-3 flex items-end justify-between gap-3 text-xs">
              <div className="min-w-0">
                <p className="truncate">{row.business_reference}</p>
                {row.work_order_number && (
                  <Link
                    href={`/work-orders/${row.work_order_id}`}
                    className="mt-1 block font-mono text-primary hover:underline"
                  >
                    {row.work_order_number}
                  </Link>
                )}
              </div>
              <time className="shrink-0 text-right text-muted-foreground">
                {formatTimestamp(row.occurred_at)}
              </time>
            </div>
          </article>
        ))}
      </div>
      <div className="hidden overflow-x-auto md:block">
        <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Mã giao dịch</TableHead>
            <TableHead>Vật tư</TableHead>
            <TableHead>Kho</TableHead>
            <TableHead>Loại</TableHead>
            <TableHead className="text-right">Số lượng</TableHead>
            <TableHead>Tham chiếu</TableHead>
            <TableHead>Thời điểm</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.id}>
              <TableCell className="font-mono text-xs font-semibold">
                {row.movement_number}
              </TableCell>
              <TableCell>
                <p className="font-mono text-xs">{row.part_number}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {row.part_name_vi}
                </p>
              </TableCell>
              <TableCell className="text-xs">
                {row.stock_location_code}
              </TableCell>
              <TableCell>
                <Badge variant="outline">{row.movement_type_display}</Badge>
              </TableCell>
              <QuantityCell value={row.quantity} symbol={row.unit_symbol} strong />
              <TableCell>
                <p className="max-w-48 truncate text-xs">
                  {row.business_reference}
                </p>
                {row.work_order_number && (
                  <Link
                    href={`/work-orders/${row.work_order_id}`}
                    className="mt-1 block font-mono text-xs text-primary hover:underline"
                  >
                    {row.work_order_number}
                  </Link>
                )}
              </TableCell>
              <TableCell className="whitespace-nowrap text-xs">
                {formatTimestamp(row.occurred_at)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
        </Table>
      </div>
    </>
  );
}

function MovementBars({ counts }: { counts: Record<string, number> }) {
  const entries = useMemo(
    () => Object.entries(counts).sort((left, right) => right[1] - left[1]),
    [counts],
  );
  const maximum = Math.max(1, ...entries.map(([, count]) => count));
  if (!entries.length) {
    return (
      <EmptyState
        title="Chưa có biến động kho"
        description="Biểu đồ sẽ xuất hiện sau giao dịch kho đầu tiên."
      />
    );
  }
  return (
    <div className="space-y-3 p-4">
      {entries.map(([type, count]) => (
        <div key={type}>
          <div className="mb-1 flex items-center justify-between gap-3 text-xs">
            <span>{movementTypeLabels[type] ?? type.replaceAll("_", " ")}</span>
            <span className="font-semibold tabular-nums">{count}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-neutral-100">
            <div
              className="h-full rounded-full bg-primary"
              style={{ width: `${Math.max(4, (count / maximum) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function ReferenceList({
  title,
  items,
}: {
  title: string;
  items: Array<{
    code: string;
    name: string;
    detail: string;
    active: boolean;
  }>;
}) {
  return (
    <section className="rounded-lg border bg-white">
      <SectionHeading title={title} description={`${items.length} bản ghi`} />
      <div className="divide-y">
        {items.map((item) => (
          <div key={item.code} className="flex items-start justify-between gap-3 p-3">
            <div className="min-w-0">
              <p className="font-mono text-xs font-semibold">{item.code}</p>
              <p className="mt-1 text-sm font-medium">{item.name}</p>
              <p className="mt-1 truncate text-xs text-muted-foreground">
                {item.detail}
              </p>
            </div>
            <Badge variant={item.active ? "default" : "outline"}>
              {item.active ? "Active" : "Inactive"}
            </Badge>
          </div>
        ))}
      </div>
    </section>
  );
}

function SectionHeading({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col justify-between gap-3 border-b p-4 sm:flex-row sm:items-center">
      <div>
        <h2 className="font-semibold">{title}</h2>
        <p className="mt-1 text-xs text-muted-foreground">{description}</p>
      </div>
      {action}
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ code: string; display_name: string }>;
}) {
  return (
    <div className="min-w-48 space-y-1.5">
      <Label>{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={all}>Tất cả</SelectItem>
          {options.map((option) => (
            <SelectItem key={option.code} value={option.code}>
              {option.display_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function Pagination({
  page,
  totalPages,
  onPage,
}: {
  page: number;
  totalPages: number;
  onPage: (page: number) => void;
}) {
  if (totalPages <= 1) return null;
  return (
    <div className="flex items-center justify-between border-t px-4 py-3">
      <p className="text-xs text-muted-foreground">
        Trang {page} / {totalPages}
      </p>
      <div className="flex gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
        >
          <ChevronLeft aria-hidden="true" />
          Trước
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={page >= totalPages}
          onClick={() => onPage(page + 1)}
        >
          Sau
          <ChevronRight aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}

function QuantityCell({
  value,
  symbol,
  strong = false,
}: {
  value: number;
  symbol: string;
  strong?: boolean;
}) {
  return (
    <TableCell className={`text-right tabular-nums ${strong ? "font-semibold" : ""}`}>
      {formatQuantity(value, symbol)}
    </TableCell>
  );
}

function QuantityTile({
  label,
  value,
  symbol,
}: {
  label: string;
  value: number;
  symbol: string;
}) {
  return (
    <div className="rounded-md bg-neutral-50 p-2">
      <p className="text-muted-foreground">{label}</p>
      <p className="mt-1 font-semibold tabular-nums">
        {formatQuantity(value, symbol)}
      </p>
    </div>
  );
}
