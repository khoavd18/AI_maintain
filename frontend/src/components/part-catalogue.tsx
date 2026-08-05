"use client";

import Link from "next/link";
import {
  ChevronLeft,
  ChevronRight,
  PackagePlus,
  RotateCcw,
  Search,
} from "lucide-react";
import { useDeferredValue, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import {
  InventoryStatusBadge,
  StockStateBadge,
} from "@/components/inventory-badges";
import { InventorySectionNav } from "@/components/inventory-section-nav";
import { PageHeader } from "@/components/page-header";
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
  useCreatePartMutation,
  useInventoryCategoriesQuery,
  useInventoryOptionsQuery,
  useInventoryPartsQuery,
  useInventoryUnitsQuery,
} from "@/hooks/use-inventory";
import { getApiErrorMessage } from "@/lib/api/errors";
import { permissions } from "@/lib/auth";
import {
  resolveStatusPresentation,
  stockStateStatusCatalog,
} from "@/lib/status-terminology";
import { formatInventoryCost, formatQuantity } from "@/lib/inventory";

const all = "all";
const pageSize = 20;

export function PartCatalogue() {
  const auth = useAuth();
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [categoryId, setCategoryId] = useState(all);
  const [lifecycle, setLifecycle] = useState(all);
  const [assetType, setAssetType] = useState(all);
  const [stockState, setStockState] = useState(all);
  const [page, setPage] = useState(1);
  const categories = useInventoryCategoriesQuery();
  const options = useInventoryOptionsQuery();
  const query = useInventoryPartsQuery({
    search: deferredSearch || undefined,
    category_id: categoryId === all ? undefined : categoryId,
    lifecycle_status: lifecycle === all ? undefined : lifecycle,
    asset_type: assetType === all ? undefined : assetType,
    stock_state: stockState === all ? undefined : stockState,
    page,
    page_size: pageSize,
  });

  function reset() {
    setSearch("");
    setCategoryId(all);
    setLifecycle(all);
    setAssetType(all);
    setStockState(all);
    setPage(1);
  }

  return (
    <div>
      <PageHeader
        title="Danh mục spare part"
        description="Master data có lifecycle riêng; archived part vẫn giữ toàn bộ lịch sử."
        breadcrumbs={[
          { label: "Kho vật tư", href: "/inventory" },
          { label: "Danh mục vật tư" },
        ]}
        actions={
          auth.can(permissions.inventoryPartsManage) ? (
            <Button type="button" onClick={() => setShowCreate((value) => !value)}>
              <PackagePlus aria-hidden="true" />
              Tạo mã vật tư
            </Button>
          ) : undefined
        }
      />
      <InventorySectionNav />
      {showCreate && (
        <PartCreateForm onCreated={() => setShowCreate(false)} />
      )}
      <section className="mb-4 rounded-lg border bg-white p-3 sm:p-4">
        <div className="grid gap-3 xl:grid-cols-[minmax(220px,1fr)_repeat(4,180px)_auto] xl:items-end">
          <div className="space-y-1.5">
            <Label htmlFor="part-search">Tìm vật tư</Label>
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <Input
                id="part-search"
                className="pl-8"
                placeholder="Part number hoặc tên"
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setPage(1);
                }}
              />
            </div>
          </div>
          <Filter
            label="Category"
            value={categoryId}
            onChange={(value) => {
              setCategoryId(value);
              setPage(1);
            }}
            options={(categories.data ?? []).map((item) => ({
              code: item.id,
              display_name: item.name_vi,
            }))}
          />
          <Filter
            label="Lifecycle"
            value={lifecycle}
            onChange={(value) => {
              setLifecycle(value);
              setPage(1);
            }}
            options={options.data?.part_lifecycle_statuses ?? []}
          />
          <Filter
            label="Asset type"
            value={assetType}
            onChange={(value) => {
              setAssetType(value);
              setPage(1);
            }}
            options={options.data?.compatible_asset_types ?? []}
          />
          <Filter
            label="Tồn kho"
            value={stockState}
            onChange={(value) => {
              setStockState(value);
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
          <Button type="button" variant="outline" onClick={reset}>
            <RotateCcw aria-hidden="true" />
            Đặt lại
          </Button>
        </div>
      </section>
      <section className="rounded-lg border bg-white">
        <div className="border-b p-4">
          <h2 className="font-semibold">Spare-part master</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {query.data
              ? `${query.data.total} mã vật tư`
              : "Đang đọc PostgreSQL qua FastAPI"}
          </p>
        </div>
        {query.isPending ? (
          <div className="p-4">
            <LoadingSkeleton />
          </div>
        ) : query.isError ? (
          <ErrorState
            title="Chưa tải được danh mục vật tư"
            description={getApiErrorMessage(query.error)}
            action={<RetryButton onClick={() => void query.refetch()} />}
          />
        ) : !query.data?.items.length ? (
          <EmptyState
            title="Không tìm thấy vật tư"
            description="Không có mã phù hợp với bộ lọc hiện tại."
            action={
              <Button type="button" variant="outline" onClick={reset}>
                Đặt lại bộ lọc
              </Button>
            }
          />
        ) : (
          <>
            <div className="grid gap-3 p-3 md:hidden">
              {query.data.items.map((part) => (
                <article key={part.id} className="rounded-lg border p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <Link
                        href={`/inventory/parts/${part.id}`}
                        className="font-mono text-xs font-semibold text-primary"
                      >
                        {part.part_number}
                      </Link>
                      <p className="mt-1 font-medium">{part.name_vi}</p>
                    </div>
                    <StockStateBadge
                      state={part.stock_state}
                      label={part.stock_state_display}
                    />
                  </div>
                  <div className="mt-3 flex items-center justify-between text-xs">
                    <InventoryStatusBadge
                      status={part.lifecycle_status}
                      label={part.lifecycle_status_display}
                      context="lifecycle"
                    />
                    <span className="font-semibold tabular-nums">
                      {formatQuantity(
                        part.total_available_quantity,
                        part.unit_symbol,
                        part.quantity_precision,
                      )}
                    </span>
                  </div>
                </article>
              ))}
            </div>
            <div className="hidden overflow-x-auto md:block">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Mã / tên</TableHead>
                    <TableHead>Category</TableHead>
                    <TableHead>Tương thích</TableHead>
                    <TableHead>Lifecycle</TableHead>
                    <TableHead>Tồn kho</TableHead>
                    <TableHead className="text-right">Available</TableHead>
                    <TableHead className="text-right">Đơn giá metadata</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {query.data.items.map((part) => (
                    <TableRow key={part.id}>
                      <TableCell>
                        <Link
                          href={`/inventory/parts/${part.id}`}
                          className="font-mono text-xs font-semibold text-primary hover:underline"
                        >
                          {part.part_number}
                        </Link>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {part.name_vi}
                        </p>
                      </TableCell>
                      <TableCell className="text-xs">
                        {part.category_name_vi}
                      </TableCell>
                      <TableCell className="text-xs">
                        {part.compatible_asset_types.join(", ") || "Mọi loại"}
                      </TableCell>
                      <TableCell>
                        <InventoryStatusBadge
                          status={part.lifecycle_status}
                          label={part.lifecycle_status_display}
                          context="lifecycle"
                        />
                      </TableCell>
                      <TableCell>
                        <StockStateBadge
                          state={part.stock_state}
                          label={part.stock_state_display}
                        />
                      </TableCell>
                      <TableCell className="text-right font-semibold tabular-nums">
                        {formatQuantity(
                          part.total_available_quantity,
                          part.unit_symbol,
                          part.quantity_precision,
                        )}
                      </TableCell>
                      <TableCell className="text-right text-xs">
                        {formatInventoryCost(part.unit_cost, part.currency_code)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            {query.data.total_pages > 1 && (
              <div className="flex items-center justify-between border-t p-3">
                <p className="text-xs text-muted-foreground">
                  Trang {page} / {query.data.total_pages}
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage((value) => value - 1)}
                  >
                    <ChevronLeft aria-hidden="true" />
                    Trước
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= query.data.total_pages}
                    onClick={() => setPage((value) => value + 1)}
                  >
                    Sau
                    <ChevronRight aria-hidden="true" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}

function PartCreateForm({ onCreated }: { onCreated: () => void }) {
  const categories = useInventoryCategoriesQuery();
  const units = useInventoryUnitsQuery();
  const mutation = useCreatePartMutation();
  const [form, setForm] = useState({
    part_number: "",
    name_vi: "",
    name_en: "",
    category_id: "",
    unit_of_measure_id: "",
    manufacturer_reference: "",
    compatible_asset_types: [] as Array<"hvac" | "pump" | "generator">,
    minimum_stock: "0",
    reorder_point: "0",
    maximum_stock: "",
    unit_cost: "",
    currency_code: "VND",
  });

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      await mutation.mutateAsync({
        part_number: form.part_number,
        name_vi: form.name_vi,
        name_en: form.name_en.trim() || null,
        category_id: form.category_id,
        unit_of_measure_id: form.unit_of_measure_id,
        manufacturer_reference: form.manufacturer_reference.trim() || null,
        compatible_asset_types: form.compatible_asset_types,
        minimum_stock: Number(form.minimum_stock),
        reorder_point: Number(form.reorder_point),
        maximum_stock: form.maximum_stock ? Number(form.maximum_stock) : null,
        unit_cost: form.unit_cost ? Number(form.unit_cost) : null,
        currency_code: form.unit_cost ? form.currency_code : null,
      });
      onCreated();
    } catch {
      // The normalized error is rendered below.
    }
  }

  function toggleAssetType(value: "hvac" | "pump" | "generator") {
    setForm((current) => ({
      ...current,
      compatible_asset_types: current.compatible_asset_types.includes(value)
        ? current.compatible_asset_types.filter((item) => item !== value)
        : [...current.compatible_asset_types, value],
    }));
  }

  return (
    <form
      onSubmit={submit}
      className="mb-4 rounded-lg border border-blue-200 bg-blue-50/40 p-4"
    >
      <div>
        <h2 className="font-semibold">Tạo spare part</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Số dư chỉ được tạo bằng opening balance hoặc receipt sau khi lưu master.
        </p>
      </div>
      <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Field label="Part number" id="part-number">
          <Input
            id="part-number"
            required
            value={form.part_number}
            onChange={(event) =>
              setForm({ ...form, part_number: event.target.value.toUpperCase() })
            }
          />
        </Field>
        <Field label="Tên tiếng Việt" id="part-name-vi">
          <Input
            id="part-name-vi"
            required
            value={form.name_vi}
            onChange={(event) => setForm({ ...form, name_vi: event.target.value })}
          />
        </Field>
        <Field label="Category" id="part-category">
          <Select
            value={form.category_id}
            onValueChange={(value) => setForm({ ...form, category_id: value })}
          >
            <SelectTrigger id="part-category" className="w-full">
              <SelectValue placeholder="Chọn category" />
            </SelectTrigger>
            <SelectContent>
              {(categories.data ?? []).map((item) => (
                <SelectItem key={item.id} value={item.id}>
                  {item.code} · {item.name_vi}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field label="Unit of measure" id="part-unit">
          <Select
            value={form.unit_of_measure_id}
            onValueChange={(value) =>
              setForm({ ...form, unit_of_measure_id: value })
            }
          >
            <SelectTrigger id="part-unit" className="w-full">
              <SelectValue placeholder="Chọn UOM" />
            </SelectTrigger>
            <SelectContent>
              {(units.data ?? []).map((item) => (
                <SelectItem key={item.id} value={item.id}>
                  {item.code} · {item.name_vi}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field label="Tồn tối thiểu" id="part-minimum">
          <Input
            id="part-minimum"
            type="number"
            min={0}
            step="0.001"
            required
            value={form.minimum_stock}
            onChange={(event) =>
              setForm({ ...form, minimum_stock: event.target.value })
            }
          />
        </Field>
        <Field label="Điểm đặt lại" id="part-reorder">
          <Input
            id="part-reorder"
            type="number"
            min={0}
            step="0.001"
            required
            value={form.reorder_point}
            onChange={(event) =>
              setForm({ ...form, reorder_point: event.target.value })
            }
          />
        </Field>
        <Field label="Tồn tối đa" id="part-maximum">
          <Input
            id="part-maximum"
            type="number"
            min={0}
            step="0.001"
            value={form.maximum_stock}
            onChange={(event) =>
              setForm({ ...form, maximum_stock: event.target.value })
            }
          />
        </Field>
        <Field label="Đơn giá metadata" id="part-cost">
          <Input
            id="part-cost"
            type="number"
            min={0}
            step="0.01"
            value={form.unit_cost}
            onChange={(event) => setForm({ ...form, unit_cost: event.target.value })}
          />
        </Field>
      </div>
      <div className="mt-4 flex flex-wrap gap-4">
        {(["hvac", "pump", "generator"] as const).map((assetType) => (
          <label key={assetType} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.compatible_asset_types.includes(assetType)}
              onChange={() => toggleAssetType(assetType)}
            />
            {assetType}
          </label>
        ))}
      </div>
      {mutation.error && (
        <p role="alert" className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-800">
          {getApiErrorMessage(mutation.error)}
        </p>
      )}
      <div className="mt-4 flex justify-end">
        <Button
          type="submit"
          disabled={
            mutation.isPending ||
            !form.category_id ||
            !form.unit_of_measure_id
          }
        >
          {mutation.isPending ? "Đang tạo..." : "Tạo mã vật tư"}
        </Button>
      </div>
    </form>
  );
}

function Filter({
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
    <div className="space-y-1.5">
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

function Field({
  label,
  id,
  children,
}: {
  label: string;
  id: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}
