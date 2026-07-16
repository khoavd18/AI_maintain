"use client";

import { Activity, AlertTriangle, Filter, Repeat2, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { ChartCard } from "@/components/chart-card";
import { AnomalyTrendChart } from "@/components/dashboard-charts";
import { DataTableShell } from "@/components/data-table-shell";
import { KpiCard } from "@/components/kpi-card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState } from "@/components/ui-states";
import { anomalies, recurringIssues } from "@/lib/mock-data";

export function AnomalyWorkspace() {
  const [search, setSearch] = useState("");
  const [assetType, setAssetType] = useState("all");
  const [anomalyType, setAnomalyType] = useState("all");

  const assetTypes = [...new Set(anomalies.map((record) => record.assetType))];
  const anomalyTypes = [...new Set(anomalies.map((record) => record.anomalyType))];
  const filteredAnomalies = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase("vi");
    return anomalies.filter((record) => {
      const matchesSearch =
        !normalizedSearch ||
        [record.assetId, record.reason].some((value) =>
          value.toLocaleLowerCase("vi").includes(normalizedSearch),
        );
      return (
        matchesSearch &&
        (assetType === "all" || record.assetType === assetType) &&
        (anomalyType === "all" || record.anomalyType === anomalyType)
      );
    });
  }, [anomalyType, assetType, search]);

  return (
    <div className="space-y-4">
      <section aria-label="Tóm tắt bất thường" className="grid gap-3 sm:grid-cols-3">
        <KpiCard label="Bất thường gần đây" value="6" detail="Trong batch hiện tại" icon={Activity} tone="blue" />
        <KpiCard label="Anomaly score cao nhất" value="0,86" detail="GENERATOR_002" icon={AlertTriangle} tone="orange" />
        <KpiCard label="Nhóm lỗi lặp lại" value="4" detail="Theo lịch sử ticket" icon={Repeat2} tone="amber" />
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.65fr)]">
        <ChartCard
          title="Xu hướng bất thường"
          description="Số record được gắn cờ theo ngày"
          summary="Ngày 30/04 có 4 tín hiệu bất thường, cao nhất trong cửa sổ hiển thị."
        >
          <AnomalyTrendChart />
        </ChartCard>

        <section aria-label="Bộ lọc bất thường" className="rounded-lg border bg-white p-4">
          <h2 className="text-sm font-semibold">Bộ lọc record</h2>
          <div className="mt-4 space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="anomaly-search">Tìm theo thiết bị hoặc lý do</Label>
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
                <Input
                  id="anomaly-search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Ví dụ: GENERATOR_002"
                  className="pl-8"
                />
              </div>
            </div>
            <AnomalyFilter id="anomaly-asset-type" label="Loại thiết bị" value={assetType} onValueChange={setAssetType} options={assetTypes} />
            <AnomalyFilter id="anomaly-type" label="Loại phát hiện" value={anomalyType} onValueChange={setAnomalyType} options={anomalyTypes} />
            <p className="flex items-center gap-2 pt-1 text-xs text-muted-foreground">
              <Filter className="size-3.5" aria-hidden="true" />
              {filteredAnomalies.length} record phù hợp
            </p>
          </div>
        </section>
      </div>

      <DataTableShell title="Bất thường gần đây" description="Sắp xếp theo anomaly score giảm dần">
        {filteredAnomalies.length === 0 ? (
          <EmptyState title="Không có record phù hợp" description="Điều chỉnh bộ lọc để xem bất thường khác." />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Ngày</TableHead>
                  <TableHead>Thiết bị</TableHead>
                  <TableHead>Loại phát hiện</TableHead>
                  <TableHead>Lý do bất thường</TableHead>
                  <TableHead className="text-right">Score</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredAnomalies.map((record) => (
                  <TableRow key={record.id}>
                    <TableCell>{record.date}</TableCell>
                    <TableCell>
                      <p className="font-mono text-xs font-medium text-primary">{record.assetId}</p>
                      <p className="mt-1 text-xs text-muted-foreground">{record.assetType}</p>
                    </TableCell>
                    <TableCell className="min-w-48">{record.anomalyType}</TableCell>
                    <TableCell className="min-w-72 text-muted-foreground">{record.reason}</TableCell>
                    <TableCell className="text-right">
                      <Badge className="bg-orange-50 font-mono text-orange-700 ring-1 ring-orange-200 hover:bg-orange-50">
                        {record.score.toFixed(2)}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </DataTableShell>

      <DataTableShell title="Vấn đề lặp lại" description="Nhóm theo loại vấn đề trong lịch sử ticket">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nhóm vấn đề</TableHead>
                <TableHead>Loại thiết bị</TableHead>
                <TableHead className="text-right">Số lần</TableHead>
                <TableHead className="text-right">Thiết bị ảnh hưởng</TableHead>
                <TableHead>Gần nhất</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {recurringIssues.map((issue) => (
                <TableRow key={issue.category}>
                  <TableCell className="font-medium">{issue.category}</TableCell>
                  <TableCell>{issue.assetType}</TableCell>
                  <TableCell className="text-right font-semibold tabular-nums">{issue.occurrences}</TableCell>
                  <TableCell className="text-right tabular-nums">{issue.affectedAssets}</TableCell>
                  <TableCell>{issue.latestDate}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </DataTableShell>
    </div>
  );
}

function AnomalyFilter({
  id,
  label,
  value,
  onValueChange,
  options,
}: {
  id: string;
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  options: string[];
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value} onValueChange={onValueChange}>
        <SelectTrigger id={id} className="w-full"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Tất cả</SelectItem>
          {options.map((option) => <SelectItem key={option} value={option}>{option}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  );
}
