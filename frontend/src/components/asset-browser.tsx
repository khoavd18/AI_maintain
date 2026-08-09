"use client";

import { ChevronLeft, ChevronRight, Plus, RotateCcw, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useDeferredValue, useMemo, useState } from "react";

import { AssetFormSheet } from "@/components/asset-form-sheet";
import { useAuth } from "@/components/auth-provider";
import { DataTableShell } from "@/components/data-table-shell";
import { LifecycleBadge, MaintenanceBadge, OperationalBadge, RiskBadge } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import { useAssetCatalogQuery, useAssetOptionsQuery, useAssetsQuery, useLocationsQuery } from "@/hooks/use-api-queries";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { AssetOverviewRecord, AssetProfile } from "@/lib/api/schemas";
import { permissions } from "@/lib/auth";

const allValue = "all";
const pageSize = 10;

export function AssetBrowser() {
  const auth = useAuth();
  const router = useRouter();
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [assetType, setAssetType] = useState(allValue);
  const [criticality, setCriticality] = useState(allValue);
  const [lifecycleStatus, setLifecycleStatus] = useState(allValue);
  const [operationalStatus, setOperationalStatus] = useState(allValue);
  const [locationId, setLocationId] = useState(allValue);
  const [riskLevel, setRiskLevel] = useState(allValue);
  const [maintenanceStatus, setMaintenanceStatus] = useState(allValue);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);

  const filters = {
    search: deferredSearch || undefined,
    asset_type: assetType === allValue ? undefined : assetType,
    criticality: criticality === allValue ? undefined : criticality,
    lifecycle_status: lifecycleStatus === allValue ? undefined : lifecycleStatus,
    operational_status: operationalStatus === allValue ? undefined : operationalStatus,
    location_id: locationId === allValue ? undefined : locationId,
    include_archived: includeArchived,
    page,
    page_size: pageSize,
  };
  const catalog = useAssetCatalogQuery(filters);
  const analytics = useAssetsQuery();
  const options = useAssetOptionsQuery();
  const locations = useLocationsQuery(includeArchived, auth.can(permissions.locationsRead));
  const analyticsById = useMemo(
    () => new Map((analytics.data ?? []).map((asset) => [asset.asset_id, asset])),
    [analytics.data],
  );
  const rows = useMemo(
    () =>
      (catalog.data?.items ?? []).filter((profile) => {
        const signals = analyticsById.get(profile.asset_id);
        return (
          (riskLevel === allValue || signals?.risk_level === riskLevel) &&
          (maintenanceStatus === allValue || signals?.maintenance_status_display === maintenanceStatus)
        );
      }),
    [analyticsById, catalog.data?.items, maintenanceStatus, riskLevel],
  );
  const activeFilterCount = [
    search,
    assetType !== allValue,
    criticality !== allValue,
    lifecycleStatus !== allValue,
    operationalStatus !== allValue,
    locationId !== allValue,
    riskLevel !== allValue,
    maintenanceStatus !== allValue,
    includeArchived,
  ].filter(Boolean).length;

  function resetFilters() {
    setSearch("");
    setAssetType(allValue);
    setCriticality(allValue);
    setLifecycleStatus(allValue);
    setOperationalStatus(allValue);
    setLocationId(allValue);
    setRiskLevel(allValue);
    setMaintenanceStatus(allValue);
    setIncludeArchived(false);
    setPage(1);
  }

  function selectFilter(setter: (value: string) => void, value: string) {
    setter(value);
    setPage(1);
  }

  return (
    <div className="space-y-4">
      <section aria-label="Bộ lọc thiết bị" className="rounded-lg border bg-white p-3 sm:p-4">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-end">
          <div className="min-w-56 flex-1 space-y-1.5">
            <Label htmlFor="asset-search">Tìm thiết bị</Label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <Input id="asset-search" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder="Mã, tên, hãng hoặc model" className="pl-8" />
            </div>
          </div>
          <FilterSelect id="asset-operational-filter" label="Trạng thái" value={operationalStatus} onValueChange={(value) => selectFilter(setOperationalStatus, value)} options={options.data?.operational_statuses ?? []} />
          <FilterSelect id="asset-risk-filter" label="Mức ưu tiên" value={riskLevel} onValueChange={(value) => selectFilter(setRiskLevel, value)} options={["Thấp", "Trung bình", "Cao", "Khẩn cấp"].map((value) => ({ code: value, display_name: value }))} />
          <Button type="button" variant="outline" onClick={resetFilters}><RotateCcw aria-hidden="true" />Đặt lại</Button>
        </div>
        <details className="group mt-3 border-t pt-3">
          <summary className="w-fit cursor-pointer rounded-md text-sm font-medium text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            Bộ lọc thêm{activeFilterCount > 0 ? ` · ${activeFilterCount} đang dùng` : ""}
          </summary>
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <FilterSelect id="asset-type-filter" label="Loại thiết bị" value={assetType} onValueChange={(value) => selectFilter(setAssetType, value)} options={options.data?.asset_types ?? []} />
            <FilterSelect id="asset-lifecycle-filter" label="Vòng đời" value={lifecycleStatus} onValueChange={(value) => selectFilter(setLifecycleStatus, value)} options={options.data?.lifecycle_statuses ?? []} />
            <FilterSelect id="asset-criticality-filter" label="Mức quan trọng" value={criticality} onValueChange={(value) => selectFilter(setCriticality, value)} options={options.data?.criticalities ?? []} />
            <FilterSelect id="asset-location-filter" label="Vị trí" value={locationId} onValueChange={(value) => selectFilter(setLocationId, value)} options={(locations.data ?? []).map((location) => ({ code: location.id, display_name: location.breadcrumb }))} wide />
            <FilterSelect id="asset-maintenance-filter" label="Lịch bảo trì" value={maintenanceStatus} onValueChange={(value) => selectFilter(setMaintenanceStatus, value)} options={["Chưa đến hạn", "Sắp đến hạn", "Quá hạn"].map((value) => ({ code: value, display_name: value }))} />
            <label className="flex h-9 items-center gap-2 rounded-lg border px-3 text-sm">
              <input type="checkbox" checked={includeArchived} onChange={(event) => { setIncludeArchived(event.target.checked); setPage(1); }} />
              Hiện thiết bị đã lưu trữ
            </label>
          </div>
        </details>
        <p className="mt-3 text-xs text-muted-foreground">Chỉ số ưu tiên được cập nhật theo đợt phân tích gần nhất.</p>
      </section>

      <DataTableShell
        title="Danh sách thiết bị"
        description={catalog.data ? `${catalog.data.total} thiết bị phù hợp` : "Đang tải danh sách thiết bị"}
        actions={auth.can(permissions.assetsCreate) ? <Button type="button" onClick={() => setCreateOpen(true)}><Plus aria-hidden="true" />Thêm thiết bị</Button> : undefined}
      >
        {catalog.isPending ? (
          <div className="p-4"><LoadingSkeleton /></div>
        ) : catalog.isError ? (
          <ErrorState title="Chưa tải được danh sách thiết bị" description={getApiErrorMessage(catalog.error)} action={<RetryButton onClick={() => void catalog.refetch()} />} />
        ) : rows.length === 0 ? (
          <EmptyState title="Không tìm thấy thiết bị" description="Không có thiết bị phù hợp với bộ lọc hiện tại." action={<Button onClick={resetFilters} variant="outline"><RotateCcw aria-hidden="true" />Đặt lại bộ lọc</Button>} />
        ) : (
          <>
            <div className="grid gap-3 p-3 md:hidden">
              {rows.map((profile) => <ManagedAssetCard key={profile.asset_id} profile={profile} analytics={analyticsById.get(profile.asset_id)} />)}
            </div>
            <div className="hidden overflow-x-auto md:block">
              <Table>
                <TableHeader><TableRow><TableHead>Thiết bị</TableHead><TableHead>Loại</TableHead><TableHead>Vị trí</TableHead><TableHead>Trạng thái</TableHead><TableHead>Tình trạng hiện tại</TableHead><TableHead className="text-right">Thao tác</TableHead></TableRow></TableHeader>
                <TableBody>
                  {rows.map((profile) => {
                    const signals = analyticsById.get(profile.asset_id);
                    return <TableRow key={profile.asset_id}>
                      <TableCell><Link href={`/assets/${profile.asset_id}`} className="font-mono text-xs font-semibold text-primary hover:underline">{profile.asset_id}</Link><p className="mt-1 max-w-52 truncate text-xs text-muted-foreground">{profile.asset_name}</p></TableCell>
                      <TableCell><p className="text-sm">{profile.asset_type}</p><p className="mt-1 text-xs text-muted-foreground">{profile.manufacturer || profile.model || "Chưa cập nhật"}</p></TableCell>
                      <TableCell className="max-w-56 text-xs">{profile.location_breadcrumb}</TableCell>
                      <TableCell><div className="flex flex-wrap gap-1.5"><OperationalBadge status={profile.operational_status} label={profile.operational_status_display} />{profile.lifecycle_status !== "active" && <LifecycleBadge status={profile.lifecycle_status} label={profile.lifecycle_status_display} />}</div></TableCell>
                      <TableCell><div className="flex flex-wrap items-center gap-1.5">{signals?.risk_level ? <RiskBadge level={signals.risk_level} /> : <span className="text-xs text-muted-foreground">Chưa có chỉ số</span>}{signals?.maintenance_status_display && <MaintenanceBadge status={signals.maintenance_status_display} />}</div></TableCell>
                      <TableCell><div className="flex justify-end"><Button asChild variant="outline" size="sm"><Link href={`/assets/${profile.asset_id}`}>Xem thiết bị</Link></Button></div></TableCell>
                    </TableRow>;
                  })}
                </TableBody>
              </Table>
            </div>
          </>
        )}

        {catalog.data && catalog.data.total_pages > 1 && (
          <div className="flex items-center justify-between border-t px-4 py-3">
            <p className="text-xs text-muted-foreground">Trang {catalog.data.page} / {catalog.data.total_pages}</p>
            <div className="flex gap-2"><Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft aria-hidden="true" />Trước</Button><Button variant="outline" size="sm" disabled={page >= catalog.data.total_pages} onClick={() => setPage((value) => value + 1)}>Sau<ChevronRight aria-hidden="true" /></Button></div>
          </div>
        )}
      </DataTableShell>

      {auth.can(permissions.assetsCreate) && createOpen && <AssetFormSheet open onOpenChange={setCreateOpen} onSaved={(assetId) => router.push(`/assets/${assetId}`)} />}
    </div>
  );
}

function ManagedAssetCard({ profile, analytics }: { profile: AssetProfile; analytics?: AssetOverviewRecord }) {
  return <article className="space-y-3 rounded-lg border p-3"><div className="flex items-start justify-between gap-3"><div><Link href={`/assets/${profile.asset_id}`} className="font-mono text-xs font-semibold text-primary">{profile.asset_id}</Link><h3 className="mt-1 font-semibold">{profile.asset_name}</h3><p className="mt-1 text-xs text-muted-foreground">{profile.asset_type}</p></div>{analytics?.risk_level && <RiskBadge level={analytics.risk_level} />}</div><div className="flex flex-wrap gap-1.5"><OperationalBadge status={profile.operational_status} label={profile.operational_status_display} />{analytics?.maintenance_status_display && <MaintenanceBadge status={analytics.maintenance_status_display} />}</div><p className="text-xs text-muted-foreground">{profile.location_breadcrumb}</p><Button asChild variant="outline" size="sm" className="w-full"><Link href={`/assets/${profile.asset_id}`}>Xem thiết bị</Link></Button></article>;
}

function FilterSelect({ id, label, value, onValueChange, options, wide = false }: { id: string; label: string; value: string; onValueChange: (value: string) => void; options: { code: string; display_name: string }[]; wide?: boolean }) {
  return <div className={wide ? "min-w-52 space-y-1.5" : "min-w-36 space-y-1.5"}><Label htmlFor={id}>{label}</Label><Select value={value} onValueChange={onValueChange}><SelectTrigger id={id} className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value={allValue}>Tất cả</SelectItem>{options.map((option) => <SelectItem key={option.code} value={option.code}>{option.display_name}</SelectItem>)}</SelectContent></Select></div>;
}
