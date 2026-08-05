"use client";

import Link from "next/link";
import {
  Archive,
  ArchiveRestore,
  Boxes,
  CircleOff,
  Loader2,
  PackageCheck,
  Play,
  RefreshCw,
} from "lucide-react";
import { useState } from "react";

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
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import {
  EmptyState,
  ErrorState,
  LoadingSkeleton,
  RetryButton,
} from "@/components/ui-states";
import {
  useInventoryBalancesQuery,
  useInventoryMovementsQuery,
  useInventoryPartQuery,
  usePartLifecycleMutation,
} from "@/hooks/use-inventory";
import { getApiErrorMessage } from "@/lib/api/errors";
import { permissions } from "@/lib/auth";
import { formatTimestamp } from "@/lib/formatters";
import { formatInventoryCost, formatQuantity } from "@/lib/inventory";

type PartLifecycleAction = "activate" | "deactivate" | "archive" | "restore";

const lifecycleCopy = {
  activate: {
    actionLabel: "Kích hoạt",
    title: "Kích hoạt mã phụ tùng?",
    description:
      "Mã phụ tùng sẽ trở lại trạng thái đang hoạt động và có thể được chọn cho nghiệp vụ kho mới.",
    confirmLabel: "Xác nhận kích hoạt",
    successMessage: "Đã kích hoạt mã phụ tùng.",
  },
  deactivate: {
    actionLabel: "Ngừng kích hoạt",
    title: "Ngừng kích hoạt mã phụ tùng?",
    description:
      "Mã phụ tùng sẽ chuyển sang không hoạt động. Số dư và lịch sử giao dịch không thay đổi.",
    confirmLabel: "Xác nhận ngừng kích hoạt",
    successMessage: "Đã ngừng kích hoạt mã phụ tùng.",
  },
  archive: {
    actionLabel: "Lưu trữ",
    title: "Lưu trữ mã phụ tùng?",
    description:
      "Mã phụ tùng sẽ ngừng được dùng cho giao dịch kho mới. Số dư và toàn bộ lịch sử vẫn được giữ nguyên.",
    confirmLabel: "Xác nhận lưu trữ",
    successMessage: "Đã lưu trữ mã phụ tùng.",
  },
  restore: {
    actionLabel: "Khôi phục",
    title: "Khôi phục mã phụ tùng?",
    description:
      "Mã phụ tùng sẽ trở về trạng thái trước khi lưu trữ. Số dư và lịch sử giao dịch không thay đổi.",
    confirmLabel: "Xác nhận khôi phục",
    successMessage: "Đã khôi phục mã phụ tùng.",
  },
} satisfies Record<
  PartLifecycleAction,
  {
    actionLabel: string;
    title: string;
    description: string;
    confirmLabel: string;
    successMessage: string;
  }
>;

export function PartDetail({ partId }: { partId: string }) {
  const auth = useAuth();
  const part = useInventoryPartQuery(partId);
  const balances = useInventoryBalancesQuery({
    part_id: partId,
    page: 1,
    page_size: 100,
  });
  const movements = useInventoryMovementsQuery({
    part_id: partId,
    page: 1,
    page_size: 20,
  });
  const lifecycle = usePartLifecycleMutation(partId);
  const [message, setMessage] = useState<string | null>(null);
  const [selectedLifecycleAction, setSelectedLifecycleAction] =
    useState<PartLifecycleAction | null>(null);
  const [lifecycleReason, setLifecycleReason] = useState("");
  const error = part.error ?? balances.error ?? movements.error;

  function requestLifecycleChange(action: PartLifecycleAction) {
    setSelectedLifecycleAction(action);
    setLifecycleReason("");
    setMessage(null);
  }

  async function confirmLifecycleChange(
    event: React.FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();
    if (!part.data || !selectedLifecycleAction) return;
    const reason = lifecycleReason.trim();
    if (selectedLifecycleAction === "archive" && reason.length < 3) return;
    try {
      await lifecycle.mutateAsync({
        action: selectedLifecycleAction,
        expectedVersion: part.data.version,
        reason: selectedLifecycleAction === "archive" ? reason : null,
      });
      setMessage(lifecycleCopy[selectedLifecycleAction].successMessage);
      setSelectedLifecycleAction(null);
      setLifecycleReason("");
    } catch (mutationError) {
      setMessage(getApiErrorMessage(mutationError));
    }
  }

  if (part.isPending || balances.isPending || movements.isPending) {
    return <LoadingSkeleton />;
  }
  if (error || !part.data) {
    return (
      <ErrorState
        title="Chưa tải được spare part"
        description={getApiErrorMessage(error)}
        action={
          <RetryButton
            onClick={() =>
              void Promise.all([
                part.refetch(),
                balances.refetch(),
                movements.refetch(),
              ])
            }
          />
        }
      />
    );
  }
  const item = part.data;
  return (
    <div>
      <PageHeader
        title={item.name_vi}
        description={`${item.part_number} · ${item.category_name_vi} · ${item.unit_name_vi}`}
        breadcrumbs={[
          { label: "Kho vật tư", href: "/inventory" },
          { label: "Danh mục", href: "/inventory/parts" },
          { label: item.part_number },
        ]}
        actions={
          <Button asChild variant="outline">
            <Link href="/inventory/receiving">Nhập kho</Link>
          </Button>
        }
      />
      <InventorySectionNav />
      {message && (
        <div
          role="status"
          className="mb-4 flex items-center justify-between gap-3 rounded-lg bg-blue-50 p-3 text-sm text-blue-900"
        >
          <span>{message}</span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void part.refetch()}
          >
            <RefreshCw aria-hidden="true" />
            Tải bản mới
          </Button>
        </div>
      )}
      <section className="rounded-lg border bg-white p-4 sm:p-5">
        <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-sm font-semibold text-primary">
                {item.part_number}
              </span>
              <InventoryStatusBadge
                status={item.lifecycle_status}
                label={item.lifecycle_status_display}
                context="lifecycle"
              />
              <StockStateBadge
                state={item.stock_state}
                label={item.stock_state_display}
              />
              <Badge variant="outline">Version {item.version}</Badge>
            </div>
            <p className="mt-3 text-sm text-muted-foreground">
              {item.name_en ?? "Chưa có tên tiếng Anh"}
            </p>
          </div>
          {auth.can(permissions.inventoryPartsManage) && (
            <div className="flex flex-wrap gap-2">
              {item.lifecycle_status === "active" && (
                <Button
                  type="button"
                  variant={
                    selectedLifecycleAction === "deactivate"
                      ? "secondary"
                      : "outline"
                  }
                  disabled={lifecycle.isPending}
                  aria-controls="part-lifecycle-confirmation"
                  aria-expanded={selectedLifecycleAction === "deactivate"}
                  onClick={() => requestLifecycleChange("deactivate")}
                >
                  <CircleOff aria-hidden="true" />
                  {lifecycleCopy.deactivate.actionLabel}
                </Button>
              )}
              {item.lifecycle_status === "inactive" && (
                <Button
                  type="button"
                  variant={
                    selectedLifecycleAction === "activate"
                      ? "secondary"
                      : "outline"
                  }
                  disabled={lifecycle.isPending}
                  aria-controls="part-lifecycle-confirmation"
                  aria-expanded={selectedLifecycleAction === "activate"}
                  onClick={() => requestLifecycleChange("activate")}
                >
                  <Play aria-hidden="true" />
                  {lifecycleCopy.activate.actionLabel}
                </Button>
              )}
              {item.lifecycle_status !== "archived" ? (
                <Button
                  type="button"
                  variant={
                    selectedLifecycleAction === "archive"
                      ? "secondary"
                      : "outline"
                  }
                  disabled={lifecycle.isPending}
                  aria-controls="part-lifecycle-confirmation"
                  aria-expanded={selectedLifecycleAction === "archive"}
                  onClick={() => requestLifecycleChange("archive")}
                >
                  <Archive aria-hidden="true" />
                  {lifecycleCopy.archive.actionLabel}
                </Button>
              ) : (
                <Button
                  type="button"
                  variant={
                    selectedLifecycleAction === "restore"
                      ? "secondary"
                      : "outline"
                  }
                  disabled={lifecycle.isPending}
                  aria-controls="part-lifecycle-confirmation"
                  aria-expanded={selectedLifecycleAction === "restore"}
                  onClick={() => requestLifecycleChange("restore")}
                >
                  <ArchiveRestore aria-hidden="true" />
                  {lifecycleCopy.restore.actionLabel}
                </Button>
              )}
            </div>
          )}
        </div>
        {selectedLifecycleAction && (
          <form
            id="part-lifecycle-confirmation"
            className="mt-5 rounded-lg border border-blue-200 bg-blue-50/70 p-4"
            onSubmit={confirmLifecycleChange}
            aria-labelledby="part-lifecycle-confirmation-title"
          >
            <div>
              <h2
                id="part-lifecycle-confirmation-title"
                className="text-sm font-semibold text-blue-950"
              >
                {lifecycleCopy[selectedLifecycleAction].title}
              </h2>
              <p className="mt-1 text-sm leading-5 text-blue-900/80">
                {lifecycleCopy[selectedLifecycleAction].description}
              </p>
            </div>

            {selectedLifecycleAction === "archive" && (
              <div className="mt-4 space-y-1.5">
                <Label htmlFor="part-archive-reason">Lý do lưu trữ</Label>
                <Textarea
                  id="part-archive-reason"
                  value={lifecycleReason}
                  onChange={(event) => setLifecycleReason(event.target.value)}
                  placeholder="Ví dụ: thay thế bằng mã phụ tùng mới"
                  minLength={3}
                  maxLength={1000}
                  required
                  disabled={lifecycle.isPending}
                  aria-describedby="part-archive-reason-help"
                  aria-invalid={
                    lifecycleReason.length > 0 &&
                    lifecycleReason.trim().length < 3
                  }
                  autoFocus
                />
                <p
                  id="part-archive-reason-help"
                  className="text-xs text-muted-foreground"
                >
                  Nhập ít nhất 3 ký tự để lưu cùng lịch sử thay đổi.
                </p>
              </div>
            )}

            <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button
                type="button"
                variant="outline"
                disabled={lifecycle.isPending}
                onClick={() => {
                  setSelectedLifecycleAction(null);
                  setLifecycleReason("");
                }}
              >
                Hủy
              </Button>
              <Button
                type="submit"
                variant={
                  selectedLifecycleAction === "archive"
                    ? "destructive"
                    : "default"
                }
                disabled={
                  lifecycle.isPending ||
                  (selectedLifecycleAction === "archive" &&
                    lifecycleReason.trim().length < 3)
                }
                autoFocus={selectedLifecycleAction !== "archive"}
              >
                {lifecycle.isPending && (
                  <Loader2 className="animate-spin" aria-hidden="true" />
                )}
                {lifecycle.isPending
                  ? "Đang cập nhật…"
                  : lifecycleCopy[selectedLifecycleAction].confirmLabel}
              </Button>
            </div>
          </form>
        )}
        <dl className="mt-5 grid gap-4 border-t pt-4 sm:grid-cols-2 lg:grid-cols-4">
          <Detail label="Category" value={`${item.category_code} · ${item.category_name_vi}`} />
          <Detail label="UOM" value={`${item.unit_code} · ${item.unit_symbol}`} />
          <Detail
            label="Manufacturer reference"
            value={item.manufacturer_reference ?? "Chưa cập nhật"}
          />
          <Detail
            label="Asset type tương thích"
            value={item.compatible_asset_types.join(", ") || "Không giới hạn"}
          />
          <Detail
            label="Minimum / reorder"
            value={`${item.minimum_stock} / ${item.reorder_point} ${item.unit_symbol}`}
          />
          <Detail
            label="Maximum"
            value={
              item.maximum_stock === null
                ? "Không cấu hình"
                : formatQuantity(
                    item.maximum_stock,
                    item.unit_symbol,
                    item.quantity_precision,
                  )
            }
          />
          <Detail
            label="Unit cost metadata"
            value={formatInventoryCost(item.unit_cost, item.currency_code)}
          />
          <Detail label="Cập nhật" value={formatTimestamp(item.updated_at)} />
        </dl>
      </section>

      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <KpiCard
          label="On-hand"
          value={formatQuantity(
            item.total_on_hand_quantity,
            item.unit_symbol,
            item.quantity_precision,
          )}
          detail="Physical stock"
          icon={Boxes}
          tone="blue"
        />
        <KpiCard
          label="Reserved"
          value={formatQuantity(
            item.total_reserved_quantity,
            item.unit_symbol,
            item.quantity_precision,
          )}
          detail="Đã phân bổ, chưa issue"
          icon={Archive}
          tone="amber"
        />
        <KpiCard
          label="Available"
          value={formatQuantity(
            item.total_available_quantity,
            item.unit_symbol,
            item.quantity_precision,
          )}
          detail="On-hand trừ reserved"
          icon={PackageCheck}
          tone="green"
        />
      </div>

      <div className="mt-5 grid items-start gap-5 xl:grid-cols-2">
        <section className="rounded-lg border bg-white">
          <SectionTitle
            title="Tồn kho theo vị trí"
            description="Ngưỡng hiệu lực có thể khác part default theo từng kho."
          />
          {!balances.data?.items.length ? (
            <EmptyState
              title="Chưa có inventory position"
              description="Tạo opening balance hoặc receipt để bắt đầu."
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Kho</TableHead>
                    <TableHead className="text-right">On-hand</TableHead>
                    <TableHead className="text-right">Reserved</TableHead>
                    <TableHead>Trạng thái</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {balances.data.items.map((balance) => (
                    <TableRow key={balance.id}>
                      <TableCell>
                        <p className="text-sm font-medium">
                          {balance.stock_location_code}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {balance.stock_location_name}
                        </p>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatQuantity(
                          balance.on_hand_quantity,
                          balance.unit_symbol,
                          item.quantity_precision,
                        )}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatQuantity(
                          balance.reserved_quantity,
                          balance.unit_symbol,
                          item.quantity_precision,
                        )}
                      </TableCell>
                      <TableCell>
                        <StockStateBadge
                          state={balance.stock_state}
                          label={balance.stock_state_display}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </section>
        <section className="rounded-lg border bg-white">
          <SectionTitle
            title="Movement gần đây"
            description="Lịch sử append-only; không sửa số dư trực tiếp."
          />
          {!movements.data?.items.length ? (
            <EmptyState
              title="Chưa có movement"
              description="Lịch sử sẽ xuất hiện sau giao dịch kho đầu tiên."
            />
          ) : (
            <div className="divide-y">
              {movements.data.items.map((movement) => (
                <div
                  key={movement.id}
                  className="flex items-start justify-between gap-4 p-4"
                >
                  <div className="min-w-0">
                    <p className="font-mono text-xs font-semibold">
                      {movement.movement_number}
                    </p>
                    <p className="mt-1 text-sm">
                      {movement.movement_type_display} ·{" "}
                      {movement.stock_location_code}
                    </p>
                    <p className="mt-1 truncate text-xs text-muted-foreground">
                      {movement.business_reference} ·{" "}
                      {formatTimestamp(movement.occurred_at)}
                    </p>
                  </div>
                  <span className="shrink-0 text-sm font-semibold tabular-nums">
                    {formatQuantity(
                      movement.quantity,
                      movement.unit_symbol,
                      item.quantity_precision,
                    )}
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-sm font-medium">{value}</dd>
    </div>
  );
}

function SectionTitle({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="border-b p-4">
      <h2 className="font-semibold">{title}</h2>
      <p className="mt-1 text-xs text-muted-foreground">{description}</p>
    </div>
  );
}
