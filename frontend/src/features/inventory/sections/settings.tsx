"use client";

import { useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { InventoryStatusBadge } from "@/components/inventory-badges";
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
  ErrorState,
  LoadingSkeleton,
  RetryButton,
} from "@/components/ui-states";
import {
  useCreateLocationMutation,
  useInventoryCategoriesQuery,
  useInventoryLocationsQuery,
  useInventoryOptionsQuery,
  useInventoryUnitsQuery,
  useStockLocationLifecycleMutation,
} from "@/hooks/use-inventory";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { StockLocation } from "@/lib/api/inventory-schemas";
import { permissions } from "@/lib/auth";

import { ReferenceList } from "../components/inventory-common";
import { SectionHeading } from "../components/inventory-controls";

export function InventorySettings() {
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
      setForm({ code: "", name: "", location_type: "", description: "" });
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
                onChange={(event) => setForm({ ...form, code: event.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="stock-location-name">Tên kho</Label>
              <Input
                id="stock-location-name"
                required
                minLength={2}
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="stock-location-type">Loại kho</Label>
            <Select
              value={form.location_type}
              onValueChange={(value) => setForm({ ...form, location_type: value })}
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
              onChange={(event) => setForm({ ...form, description: event.target.value })}
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
          <StockLocationRow key={location.id} location={location} canManage={canManage} />
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
            <Button type="button" variant="outline" size="sm" disabled={lifecycle.isPending} onClick={() => void change("deactivate")}>
              Ngừng hoạt động
            </Button>
          )}
          {location.lifecycle_status === "inactive" && (
            <Button type="button" variant="outline" size="sm" disabled={lifecycle.isPending} onClick={() => void change("activate")}>
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
            <Button type="button" variant="outline" size="sm" disabled={lifecycle.isPending} onClick={() => void change("restore")}>
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
