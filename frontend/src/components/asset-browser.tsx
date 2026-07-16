"use client";

import Link from "next/link";
import { ArrowRight, RotateCcw, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { AssetSummaryCard } from "@/components/asset-summary-card";
import { DataTableShell } from "@/components/data-table-shell";
import { MaintenanceBadge, RiskBadge } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState } from "@/components/ui-states";
import { assets } from "@/lib/mock-data";

const allValue = "all";

export function AssetBrowser() {
  const [search, setSearch] = useState("");
  const [assetType, setAssetType] = useState(allValue);
  const [criticality, setCriticality] = useState(allValue);
  const [riskLevel, setRiskLevel] = useState(allValue);
  const [maintenanceStatus, setMaintenanceStatus] = useState(allValue);

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
  }, [assetType, criticality, maintenanceStatus, riskLevel, search]);

  function resetFilters() {
    setSearch("");
    setAssetType(allValue);
    setCriticality(allValue);
    setRiskLevel(allValue);
    setMaintenanceStatus(allValue);
  }

  return (
    <div className="space-y-4">
      <section aria-label="Bộ lọc thiết bị" className="rounded-lg border bg-white p-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[minmax(240px,1.3fr)_repeat(4,minmax(140px,0.8fr))_auto]">
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
          <FilterSelect id="risk-level" label="Mức rủi ro" value={riskLevel} onValueChange={setRiskLevel} options={["Thấp", "Trung bình", "Cao", "Nghiêm trọng"]} />
          <FilterSelect id="maintenance-status" label="Trạng thái bảo trì" value={maintenanceStatus} onValueChange={setMaintenanceStatus} options={["Chưa đến hạn", "Sắp đến hạn", "Quá hạn"]} />

          <div className="flex items-end">
            <Button type="button" variant="outline" onClick={resetFilters} className="w-full md:w-auto">
              <RotateCcw aria-hidden="true" />
              Đặt lại
            </Button>
          </div>
        </div>
      </section>

      <DataTableShell
        title="Danh mục thiết bị"
        description={`${filteredAssets.length} thiết bị trong dữ liệu mock hiện tại`}
      >
        {filteredAssets.length === 0 ? (
          <EmptyState title="Không tìm thấy thiết bị" description="Điều chỉnh từ khóa hoặc bộ lọc để xem kết quả khác." />
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
                    <TableHead>Loại</TableHead>
                    <TableHead>Vị trí</TableHead>
                    <TableHead>Quan trọng</TableHead>
                    <TableHead>Rủi ro</TableHead>
                    <TableHead>Bảo trì</TableHead>
                    <TableHead className="text-right">Risk score</TableHead>
                    <TableHead><span className="sr-only">Thao tác</span></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredAssets.map((asset) => (
                    <TableRow key={asset.id}>
                      <TableCell>
                        <p className="font-mono text-xs font-medium text-primary">{asset.id}</p>
                        <p className="mt-1 max-w-56 truncate text-xs text-muted-foreground">{asset.name}</p>
                      </TableCell>
                      <TableCell>{asset.type}</TableCell>
                      <TableCell className="max-w-44 truncate text-muted-foreground">{asset.location}</TableCell>
                      <TableCell>{asset.criticality}</TableCell>
                      <TableCell><RiskBadge level={asset.riskLevel} /></TableCell>
                      <TableCell><MaintenanceBadge status={asset.maintenanceStatus} /></TableCell>
                      <TableCell className="text-right font-semibold tabular-nums">{asset.riskScore.toFixed(2)}</TableCell>
                      <TableCell className="text-right">
                        <Button asChild variant="ghost" size="icon-sm">
                          <Link href={`/assets/${asset.id}`} aria-label={`Xem chi tiết ${asset.id}`}>
                            <ArrowRight aria-hidden="true" />
                          </Link>
                        </Button>
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
