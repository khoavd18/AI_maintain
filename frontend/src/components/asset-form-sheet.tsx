"use client";

import { Loader2, Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { useCreateAsset, useUpdateAsset } from "@/hooks/use-api-mutations";
import { useAssetOptionsQuery, useLocationsQuery } from "@/hooks/use-api-queries";
import { UserSafeApiError, getApiErrorMessage } from "@/lib/api/errors";
import type { AssetCreateRequest, AssetProfile, AssetUpdateRequest } from "@/lib/api/schemas";

interface AssetFormSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  profile?: AssetProfile | null;
  onSaved?: (assetId: string) => void;
  onReload?: () => void;
}

interface FormState {
  assetId: string;
  assetName: string;
  assetType: "hvac" | "pump" | "generator";
  assetCategory: "climate_control" | "water_system" | "power_system" | "other";
  manufacturer: string;
  model: string;
  serialNumber: string;
  productionYear: string;
  locationId: string;
  criticality: "low" | "medium" | "high" | "critical";
  lifecycleStatus: "planned" | "active" | "inactive";
  operationalStatus: "running" | "warning" | "fault" | "under_maintenance" | "out_of_service";
  installedDate: string;
  commissionedDate: string;
  ownershipType: "owned" | "leased" | "managed";
  description: string;
  warrantyStartDate: string;
  warrantyEndDate: string;
  warrantyProvider: string;
  warrantyReference: string;
  maintenanceIntervalDays: string;
  lastMaintenanceDate: string;
  nextMaintenanceDate: string;
}

const categoryByType: Record<FormState["assetType"], FormState["assetCategory"]> = {
  hvac: "climate_control",
  pump: "water_system",
  generator: "power_system",
};

export function AssetFormSheet({
  open,
  onOpenChange,
  profile,
  onSaved,
  onReload,
}: AssetFormSheetProps) {
  const auth = useAuth();
  const options = useAssetOptionsQuery();
  const locations = useLocationsQuery(false);
  const createMutation = useCreateAsset();
  const updateMutation = useUpdateAsset(profile?.asset_id ?? "");
  const [form, setForm] = useState<FormState>(() => initialForm(profile));
  const [dirty, setDirty] = useState(false);
  const editing = Boolean(profile);
  const managerLimited = auth.user?.role === "property_manager";
  const mutation = editing ? updateMutation : createMutation;
  const selectedLocationId = form.locationId || locations.data?.[0]?.id || "";

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const errorMessage = mutation.isError ? getApiErrorMessage(mutation.error) : null;
  const stale = mutation.error instanceof UserSafeApiError && mutation.error.code === "conflict";
  const technicalDisabled = editing && managerLimited;

  function update<K extends keyof FormState>(field: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [field]: value }));
    setDirty(true);
  }

  function changeAssetType(value: FormState["assetType"]) {
    setForm((current) => ({
      ...current,
      assetType: value,
      assetCategory: categoryByType[value],
    }));
    setDirty(true);
  }

  function requestClose(nextOpen: boolean) {
    if (!nextOpen && dirty && !window.confirm("Hủy các thay đổi chưa lưu?")) return;
    onOpenChange(nextOpen);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      if (profile) {
        await updateMutation.mutateAsync(buildUpdateRequest({ ...form, locationId: selectedLocationId }, profile, managerLimited));
        setDirty(false);
        onSaved?.(profile.asset_id);
      } else {
        const created = await createMutation.mutateAsync(buildCreateRequest({ ...form, locationId: selectedLocationId }));
        setDirty(false);
        onSaved?.(created.asset_id);
      }
      onOpenChange(false);
    } catch {
      // Mutation state renders the safe API error beside the submit controls.
    }
  }

  const optionData = useMemo(() => options.data, [options.data]);

  return (
    <Sheet open={open} onOpenChange={requestClose}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-2xl">
        <SheetHeader className="border-b pr-12">
          <SheetTitle>{editing ? `Cập nhật ${profile?.asset_id}` : "Đăng ký asset"}</SheetTitle>
          <SheetDescription>
            Hồ sơ kỹ thuật, vị trí, bảo hành và chu kỳ bảo trì. Lifecycle và trạng thái vận hành được quản lý riêng sau khi tạo.
          </SheetDescription>
        </SheetHeader>

        <form id="asset-form" onSubmit={submit} className="space-y-6 px-4 pb-4">
          <FormSection title="Nhận diện">
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField label="Asset ID" value={form.assetId} onChange={(value) => update("assetId", value.toUpperCase())} required disabled={editing} />
              <TextField label="Tên thiết bị" value={form.assetName} onChange={(value) => update("assetName", value)} required disabled={technicalDisabled} />
              <SelectField label="Loại thiết bị" value={form.assetType} onValueChange={(value) => changeAssetType(value as FormState["assetType"])} options={optionData?.asset_types ?? []} disabled={technicalDisabled} />
              <SelectField label="Nhóm thiết bị" value={form.assetCategory} onValueChange={(value) => update("assetCategory", value as FormState["assetCategory"])} options={optionData?.asset_categories ?? []} disabled={technicalDisabled} />
              <TextField label="Nhà sản xuất" value={form.manufacturer} onChange={(value) => update("manufacturer", value)} disabled={technicalDisabled} />
              <TextField label="Model" value={form.model} onChange={(value) => update("model", value)} disabled={technicalDisabled} />
              <TextField label="Serial number" value={form.serialNumber} onChange={(value) => update("serialNumber", value.toUpperCase())} disabled={technicalDisabled} />
              <TextField label="Năm sản xuất" value={form.productionYear} onChange={(value) => update("productionYear", value)} type="number" disabled={technicalDisabled} />
            </div>
          </FormSection>

          <FormSection title="Vòng đời và vị trí">
            <div className="grid gap-3 sm:grid-cols-2">
              <SelectField label="Vị trí" value={selectedLocationId} onValueChange={(value) => update("locationId", value)} options={(locations.data ?? []).map((location) => ({ code: location.id, display_name: location.breadcrumb }))} />
              <SelectField label="Mức độ quan trọng" value={form.criticality} onValueChange={(value) => update("criticality", value as FormState["criticality"])} options={optionData?.criticalities ?? []} />
              {!editing && <SelectField label="Lifecycle ban đầu" value={form.lifecycleStatus} onValueChange={(value) => update("lifecycleStatus", value as FormState["lifecycleStatus"])} options={(optionData?.lifecycle_statuses ?? []).filter((item) => !["retired", "archived"].includes(item.code))} />}
              {!editing && <SelectField label="Trạng thái vận hành" value={form.operationalStatus} onValueChange={(value) => update("operationalStatus", value as FormState["operationalStatus"])} options={optionData?.operational_statuses ?? []} />}
              <TextField label="Ngày lắp đặt" value={form.installedDate} onChange={(value) => update("installedDate", value)} type="date" required disabled={technicalDisabled} />
              <TextField label="Ngày nghiệm thu" value={form.commissionedDate} onChange={(value) => update("commissionedDate", value)} type="date" disabled={technicalDisabled} />
              <SelectField label="Hình thức sở hữu" value={form.ownershipType} onValueChange={(value) => update("ownershipType", value as FormState["ownershipType"])} options={optionData?.ownership_types ?? []} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="asset-description">Mô tả</Label>
              <Textarea id="asset-description" value={form.description} onChange={(event) => update("description", event.target.value)} rows={3} />
            </div>
          </FormSection>

          <FormSection title="Bảo hành">
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField label="Bắt đầu bảo hành" value={form.warrantyStartDate} onChange={(value) => update("warrantyStartDate", value)} type="date" />
              <TextField label="Kết thúc bảo hành" value={form.warrantyEndDate} onChange={(value) => update("warrantyEndDate", value)} type="date" />
              <TextField label="Đơn vị bảo hành" value={form.warrantyProvider} onChange={(value) => update("warrantyProvider", value)} />
              <TextField label="Mã tham chiếu" value={form.warrantyReference} onChange={(value) => update("warrantyReference", value)} />
            </div>
          </FormSection>

          <FormSection title="Bảo trì">
            <div className="grid gap-3 sm:grid-cols-3">
              <TextField label="Chu kỳ (ngày)" value={form.maintenanceIntervalDays} onChange={(value) => update("maintenanceIntervalDays", value)} type="number" required />
              <TextField label="Bảo trì gần nhất" value={form.lastMaintenanceDate} onChange={(value) => update("lastMaintenanceDate", value)} type="date" required />
              <TextField label="Bảo trì kế tiếp" value={form.nextMaintenanceDate} onChange={(value) => update("nextMaintenanceDate", value)} type="date" required />
            </div>
          </FormSection>

          {errorMessage && (
            <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              <p>{errorMessage}</p>
              {stale && onReload && <Button type="button" variant="outline" size="sm" className="mt-2" onClick={onReload}>Tải hồ sơ mới nhất</Button>}
            </div>
          )}
        </form>

        <SheetFooter className="border-t bg-white">
          <Button type="submit" form="asset-form" disabled={mutation.isPending || !selectedLocationId}>
            {mutation.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
            {editing ? "Lưu hồ sơ" : "Tạo asset"}
          </Button>
          <Button type="button" variant="outline" onClick={() => requestClose(false)}>Hủy</Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

function FormSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="space-y-3 border-t pt-4 first:border-t-0 first:pt-0"><h3 className="text-sm font-semibold">{title}</h3>{children}</section>;
}

function TextField({
  label,
  value,
  onChange,
  type = "text",
  required = false,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  required?: boolean;
  disabled?: boolean;
}) {
  const id = `asset-${label.toLocaleLowerCase("vi").replace(/\s+/g, "-")}`;
  return <div className="space-y-1.5"><Label htmlFor={id}>{label}</Label><Input id={id} type={type} value={value} onChange={(event) => onChange(event.target.value)} required={required} disabled={disabled} /></div>;
}

function SelectField({
  label,
  value,
  onValueChange,
  options,
  disabled = false,
}: {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  options: { code: string; display_name: string }[];
  disabled?: boolean;
}) {
  return <div className="space-y-1.5"><Label>{label}</Label><Select value={value} onValueChange={onValueChange} disabled={disabled}><SelectTrigger className="w-full"><SelectValue placeholder="Chọn giá trị" /></SelectTrigger><SelectContent>{options.map((option) => <SelectItem key={option.code} value={option.code}>{option.display_name}</SelectItem>)}</SelectContent></Select></div>;
}

function initialForm(profile?: AssetProfile | null): FormState {
  const today = new Date().toISOString().slice(0, 10);
  return {
    assetId: profile?.asset_id ?? "",
    assetName: profile?.asset_name ?? "",
    assetType: profile?.asset_type_code ?? "generator",
    assetCategory: profile?.asset_category ?? "power_system",
    manufacturer: profile?.manufacturer ?? "",
    model: profile?.model ?? "",
    serialNumber: profile?.serial_number ?? "",
    productionYear: profile?.production_year?.toString() ?? "",
    locationId: profile?.location_id ?? "",
    criticality: profile?.criticality_code ?? "medium",
    lifecycleStatus: profile && profile.lifecycle_status !== "retired" && profile.lifecycle_status !== "archived" ? profile.lifecycle_status : "active",
    operationalStatus: profile?.operational_status ?? "running",
    installedDate: datePart(profile?.installed_at) || today,
    commissionedDate: datePart(profile?.commissioned_at),
    ownershipType: profile?.ownership_type ?? "owned",
    description: profile?.description ?? "",
    warrantyStartDate: profile?.warranty_start_date ?? "",
    warrantyEndDate: profile?.warranty_end_date ?? "",
    warrantyProvider: profile?.warranty_provider ?? "",
    warrantyReference: profile?.warranty_reference ?? "",
    maintenanceIntervalDays: profile?.maintenance_interval_days.toString() ?? "30",
    lastMaintenanceDate: profile?.last_maintenance_date ?? today,
    nextMaintenanceDate: profile?.next_maintenance_date ?? today,
  };
}

function buildCreateRequest(form: FormState): AssetCreateRequest {
  return {
    asset_id: form.assetId,
    asset_name: form.assetName,
    asset_type: form.assetType,
    asset_category: form.assetCategory,
    manufacturer: nullable(form.manufacturer),
    model: nullable(form.model),
    serial_number: nullable(form.serialNumber),
    production_year: form.productionYear ? Number(form.productionYear) : null,
    location_id: form.locationId,
    criticality: form.criticality,
    lifecycle_status: form.lifecycleStatus,
    operational_status: form.operationalStatus,
    installed_at: dateToUtc(form.installedDate),
    commissioned_at: form.commissionedDate ? dateToUtc(form.commissionedDate) : null,
    ownership_type: form.ownershipType,
    description: nullable(form.description),
    warranty_start_date: nullable(form.warrantyStartDate),
    warranty_end_date: nullable(form.warrantyEndDate),
    warranty_provider: nullable(form.warrantyProvider),
    warranty_reference: nullable(form.warrantyReference),
    maintenance_interval_days: Number(form.maintenanceIntervalDays),
    last_maintenance_date: form.lastMaintenanceDate,
    next_maintenance_date: form.nextMaintenanceDate,
  };
}

function buildUpdateRequest(
  form: FormState,
  profile: AssetProfile,
  managerLimited: boolean,
): AssetUpdateRequest {
  const shared = {
    expected_version: profile.version,
    location_id: form.locationId,
    criticality: form.criticality,
    ownership_type: form.ownershipType,
    description: nullable(form.description),
    warranty_start_date: nullable(form.warrantyStartDate),
    warranty_end_date: nullable(form.warrantyEndDate),
    warranty_provider: nullable(form.warrantyProvider),
    warranty_reference: nullable(form.warrantyReference),
    maintenance_interval_days: Number(form.maintenanceIntervalDays),
    last_maintenance_date: form.lastMaintenanceDate,
    next_maintenance_date: form.nextMaintenanceDate,
  } satisfies AssetUpdateRequest;
  if (managerLimited) return shared;
  return {
    ...shared,
    asset_name: form.assetName,
    asset_type: form.assetType,
    asset_category: form.assetCategory,
    manufacturer: nullable(form.manufacturer),
    model: nullable(form.model),
    serial_number: nullable(form.serialNumber),
    production_year: form.productionYear ? Number(form.productionYear) : null,
    installed_at: dateToUtc(form.installedDate),
    commissioned_at: form.commissionedDate ? dateToUtc(form.commissionedDate) : null,
  };
}

function nullable(value: string): string | null {
  return value.trim() || null;
}

function dateToUtc(value: string): string {
  return `${value}T00:00:00.000Z`;
}

function datePart(value?: string | null): string {
  return value?.slice(0, 10) ?? "";
}
