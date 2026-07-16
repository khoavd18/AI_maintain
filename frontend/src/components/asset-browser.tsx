"use client";

import Link from "next/link";
import { ArrowRight, RotateCcw, Search, TicketPlus, X } from "lucide-react";
import { useMemo, useState } from "react";

import { AssetSummaryCard } from "@/components/asset-summary-card";
import { DataTableShell } from "@/components/data-table-shell";
import { MaintenanceBadge, RiskBadge } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import { useAssetsQuery } from "@/hooks/use-api-queries";
import { adaptAsset } from "@/lib/adapters";
import { getApiErrorMessage } from "@/lib/api/errors";

const allValue = "all";

export function AssetBrowser() {
  const [search, setSearch] = useState("");
  const [assetType, setAssetType] = useState(allValue);
  const [criticality, setCriticality] = useState(allValue);
  const [riskLevel, setRiskLevel] = useState(allValue);
  const [maintenanceStatus, setMaintenanceStatus] = useState(allValue);
  const assetsQuery = useAssetsQuery();
  const assets = useMemo(() => (assetsQuery.data ?? []).map(adaptAsset), [assetsQuery.data]);

  const assetTypes = [...new Set(assets.map((asset) => asset.type))];
  const criticalities = [...new Set(assets.map((asset) => asset.criticality))];

  const filteredAssets = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase("vi");
    return assets.filter((asset) => {
      const matchesSearch =
        !normalizedSearch ||
        [asset.id, asset.name, asset.location].some((value) =>
          value.toLocaleLowerCase("vi").includes(normalizedSearch),
        );
      return (
        matchesSearch &&
        (assetType === allValue || asset.type === assetType) &&
        (criticality === allValue || asset.criticality === criticality) &&
        (riskLevel === allValue || asset.riskLevel === riskLevel) &&
        (maintenanceStatus === allValue || asset.maintenanceStatus === maintenanceStatus)
      );
    });
  }, [assetType, assets, criticality, maintenanceStatus, riskLevel, search]);

  function resetFilters() {
    setSearch("");
    setAssetType(allValue);
    setCriticality(allValue);
    setRiskLevel(allValue);
    setMaintenanceStatus(allValue);
  }

  const activeFilters = [
    assetType !== allValue ? { key: "type", label: `Loại: ${assetType}`, clear: () => setAssetType(allValue) } : null,
    criticality !== allValue ? { key: "criticality", label: `Quan trọng: ${criticality}`, clear: () => setCriticality(allValue) } : null,
    riskLevel !== allValue ? { key: "risk", label: `Risk: ${riskLevel}`, clear: () => setRiskLevel(allValue) } : null,
    maintenanceStatus !== allValue ? { key: "maintenance", label: `Bảo trì: ${maintenanceStatus}`, clear: () => setMaintenanceStatus(allValue) } : null,
  ].filter((filter): filter is { key: string; label: string; clear: () => void } => filter !== null);

  return (
    <div className="space-y-4">
      <section aria-label="Bộ lọc thiết bị" className="rounded-lg border bg-white p-3 sm:p-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[minmax(220px,1.2fr)_repeat(4,minmax(132px,0.75fr))_auto]">
          <div className="space-y-1.5">
            <Label htmlFor="asset-search">Tìm thiết bị</Label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <Input
                id="asset-search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Asset ID, tên hoặc vị trí"
                className="pl-8"
              />
            </div>
          </div>

          <FilterSelect id="asset-type" label="Loại thiết bị" value={assetType} onValueChange={setAssetType} options={assetTypes} />
          <FilterSelect id="criticality" label="Mức độ quan trọng" value={criticality} onValueChange={setCriticality} options={criticalities} />
          <FilterSelect id="risk-level" label="Mức rủi ro" value={riskLevel} onValueChange={setRiskLevel} options={["Thấp", "Trung bình", "Cao", "Khẩn cấp"]} />
          <FilterSelect id="maintenance-status" label="Trạng thái bảo trì" value={maintenanceStatus} onValueChange={setMaintenanceStatus} options={["Chưa đến hạn", "Sắp đến hạn", "Quá hạn"]} />

          <div className="flex items-end">
            <Button type="button" variant="outline" onClick={resetFilters} className="w-full md:w-auto">
              <RotateCcw aria-hidden="true" />
              Đặt lại
            </Button>
          </div>
        </div>

        {(activeFilters.length > 0 || search) && (
          <div className="mt-3 flex flex-wrap items-center gap-2 border-t pt-3" aria-label="Bộ lọc đang áp dụng">
            <span className="text-xs font-medium text-muted-foreground">Đang lọc:</span>
            {search && (
              <Badge variant="secondary" className="gap-1 pr-1">
                Từ khóa: {search}
                <button type="button" onClick={() => setSearch("")} className="rounded-full p-0.5 hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="Xóa từ khóa">
                  <X aria-hidden="true" />
                </button>
              </Badge>
            )}
            {activeFilters.map((filter) => (
              <Badge key={filter.key} variant="secondary" className="gap-1 pr-1">
                {filter.label}
                <button type="button" onClick={filter.clear} className="rounded-full p-0.5 hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label={`Xóa bộ lọc ${filter.label}`}>
                  <X aria-hidden="true" />
                </button>
              </Badge>
            ))}
          </div>
        )}
      </section>

      <DataTableShell
        title="Danh mục thiết bị"
        description={`${filteredAssets.length} kết quả trong ${assets.length} thiết bị từ API`}
      >
        {assetsQuery.isPending ? (
          <div className="p-4"><LoadingSkeleton /></div>
        ) : assetsQuery.isError ? (
          <ErrorState
            title="Chưa tải được danh mục thiết bị"
            description={getApiErrorMessage(assetsQuery.error)}
            action={<RetryButton onClick={() => void assetsQuery.refetch()} />}
          />
        ) : filteredAssets.length === 0 ? (
          <EmptyState
            title="Không tìm thấy thiết bị"
            description="Không có thiết bị phù hợp với tổ hợp bộ lọc hiện tại. Đặt lại bộ lọc để quay về toàn bộ danh sách."
            action={<Button onClick={resetFilters} variant="outline"><RotateCcw aria-hidden="true" />Đặt lại bộ lọc</Button>}
          />
        ) : (
          <>
            <div className="grid gap-3 p-4 md:hidden">
              {filteredAssets.map((asset) => <AssetSummaryCard key={asset.id} asset={asset} />)}
            </div>
            <div className="hidden overflow-x-auto md:block">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Thiết bị</TableHead>
                    <TableHead>Loại / vị trí</TableHead>
                    <TableHead>Rủi ro</TableHead>
                    <TableHead>Bảo trì</TableHead>
                    <TableHead className="text-right">Ticket mở</TableHead>
                    <TableHead>Hành động tiếp theo</TableHead>
                    <TableHead className="text-right">Thao tác</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredAssets.map((asset) => (
                    <TableRow key={asset.id} className="relative hover:bg-blue-50/40">
                      <TableCell>
                        <Link
                          href={`/assets/${asset.id}`}
                          className="font-mono text-xs font-medium text-primary after:absolute after:inset-0 focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          {asset.id}
                        </Link>
                        <p className="mt-1 max-w-52 truncate text-xs text-muted-foreground">{asset.name}</p>
                      </TableCell>
                      <TableCell>
                        <p>{asset.type}</p>
                        <p className="mt-1 max-w-44 truncate text-xs text-muted-foreground">{asset.location}</p>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {asset.riskLevel ? <RiskBadge level={asset.riskLevel} /> : <span className="text-xs text-muted-foreground">Chưa có risk</span>}
                          <span className="text-xs font-semibold tabular-nums">{asset.riskScore == null ? "--" : asset.riskScore.toFixed(2)}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        {asset.maintenanceStatus ? <MaintenanceBadge status={asset.maintenanceStatus} /> : <span className="text-xs text-muted-foreground">Chưa có lịch</span>}
                        <p className="mt-1.5 text-xs text-muted-foreground">
                          {asset.overdueDays > 0 ? `${asset.overdueDays} ngày quá hạn` : `Kế tiếp ${asset.nextMaintenance}`}
                        </p>
                      </TableCell>
                      <TableCell className="text-right font-semibold tabular-nums">{asset.unresolvedTickets}</TableCell>
                      <TableCell className="max-w-64 text-xs leading-5 text-muted-foreground">{asset.recommendedAction}</TableCell>
                      <TableCell>
                        <div className="relative z-10 flex justify-end gap-1">
                          <Button asChild variant="ghost" size="icon-sm">
                            <Link href={`/assets/${asset.id}`} aria-label={`Xem chi tiết ${asset.id}`}>
                              <ArrowRight aria-hidden="true" />
                            </Link>
                          </Button>
                          <Button asChild variant="ghost" size="icon-sm">
                            <Link href={`/tickets?asset=${asset.id}&action=create`} aria-label={`Tạo ticket cho ${asset.id}`}>
                              <TicketPlus aria-hidden="true" />
                            </Link>
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </>
        )}
      </DataTableShell>
    </div>
  );
}

interface FilterSelectProps {
  id: string;
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  options: string[];
}

function FilterSelect({ id, label, value, onValueChange, options }: FilterSelectProps) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value} onValueChange={onValueChange}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={allValue}>Tất cả</SelectItem>
          {options.map((option) => <SelectItem key={option} value={option}>{option}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  );
}
