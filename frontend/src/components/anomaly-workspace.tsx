"use client";

import Link from "next/link";
import { Activity, AlertTriangle, ArrowRight, Filter, Repeat2, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { ChartCard } from "@/components/chart-card";
import { AnomalyTrendChart } from "@/components/dashboard-charts";
import { DataTableShell } from "@/components/data-table-shell";
import { KpiCard } from "@/components/kpi-card";
import { AnomalySeverityBadge } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import { useAnomaliesQuery, useRecurringIssuesQuery } from "@/hooks/use-api-queries";
import { adaptAnomaly, adaptRecurringIssue } from "@/lib/adapters";
import { getApiErrorMessage } from "@/lib/api/errors";
import { formatDate } from "@/lib/formatters";

export function AnomalyWorkspace() {
  const anomaliesQuery = useAnomaliesQuery({ only_anomalies: true, limit: 1000 });
  const recurringQuery = useRecurringIssuesQuery({ recurrence_flag: true });
  const [search, setSearch] = useState("");
  const [assetType, setAssetType] = useState("all");
  const [severity, setSeverity] = useState("all");
  const anomalies = useMemo(() => (anomaliesQuery.data ?? []).map(adaptAnomaly), [anomaliesQuery.data]);
  const recurringIssues = useMemo(() => (recurringQuery.data ?? []).map(adaptRecurringIssue), [recurringQuery.data]);
  const assetTypes = [...new Set(anomalies.map((record) => record.assetType))];
  const filteredAnomalies = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase("vi");
    return anomalies.filter((record) => {
      const matchesSearch = !normalizedSearch || [record.assetId, record.metric, record.change, record.reason].some((value) => value.toLocaleLowerCase("vi").includes(normalizedSearch));
      return matchesSearch && (assetType === "all" || record.assetType === assetType) && (severity === "all" || record.severity === severity);
    });
  }, [anomalies, assetType, search, severity]);

  if (anomaliesQuery.isPending || recurringQuery.isPending) return <LoadingSkeleton />;
  const failedQuery = [anomaliesQuery, recurringQuery].find((query) => query.isError);
  if (failedQuery) return <ErrorState title="Chưa tải được dữ liệu bất thường" description={getApiErrorMessage(failedQuery.error)} action={<RetryButton onClick={() => void Promise.all([anomaliesQuery.refetch(), recurringQuery.refetch()])} />} />;

  const trend = buildAnomalyTrend(anomaliesQuery.data ?? []);
  const priorityCount = anomalies.filter((record) => record.severity === "Ưu tiên").length;

  return (
    <div className="space-y-4">
      <section aria-label="Tóm tắt bất thường" className="grid gap-3 sm:grid-cols-3">
        <KpiCard label="Bất thường gần đây" value={String(anomalies.length)} detail="Record được gắn cờ" icon={Activity} tone="blue" />
        <KpiCard label="Sự kiện ưu tiên" value={String(priorityCount)} detail="Anomaly score từ 85" icon={AlertTriangle} tone="orange" />
        <KpiCard label="Nhóm lỗi lặp lại" value={String(recurringIssues.length)} detail="Đạt recurrence threshold" icon={Repeat2} tone="amber" />
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.65fr)]">
        <ChartCard title="Xu hướng bất thường" description="Số record được gắn cờ theo ngày" summary={`${trend.reduce((sum, item) => sum + item.count, 0)} record trong cửa sổ API hiện tại.`}><AnomalyTrendChart data={trend} /></ChartCard>
        <section aria-label="Bộ lọc bất thường" className="rounded-lg border bg-white p-4">
          <h2 className="text-sm font-semibold">Bộ lọc record</h2>
          <div className="mt-4 space-y-3">
            <div className="space-y-1.5"><Label htmlFor="anomaly-search">Tìm theo thiết bị hoặc lý do</Label><div className="relative"><Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" /><Input id="anomaly-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Ví dụ: GENERATOR_002" className="pl-8" /></div></div>
            <AnomalyFilter id="anomaly-asset-type" label="Loại thiết bị" value={assetType} onValueChange={setAssetType} options={assetTypes} />
            <AnomalyFilter id="anomaly-severity" label="Mức cần chú ý" value={severity} onValueChange={setSeverity} options={["Ưu tiên", "Cảnh báo", "Theo dõi"]} />
            <p className="flex items-center gap-2 pt-1 text-xs text-muted-foreground"><Filter className="size-3.5" aria-hidden="true" />{filteredAnomalies.length} record phù hợp</p>
          </div>
        </section>
      </div>

      <DataTableShell title="Sự kiện bất thường gần đây" description="Tín hiệu vận hành từ rule và Isolation Forest">
        {filteredAnomalies.length === 0 ? <EmptyState title="Không có record phù hợp" description="Điều chỉnh bộ lọc để xem bất thường khác." /> : <>
          <div className="grid gap-3 p-4 md:hidden">{filteredAnomalies.map((record) => <article key={record.id} className="rounded-lg border p-3"><div className="flex items-start justify-between gap-3"><div><p className="font-mono text-xs font-semibold text-primary">{record.assetId}</p><p className="mt-1 text-xs text-muted-foreground">{record.assetType} · {record.date}</p></div><AnomalySeverityBadge severity={record.severity} /></div><p className="mt-3 text-xs font-medium text-muted-foreground">{record.metric}</p><p className="mt-1 text-sm font-medium leading-5">{record.change}</p><p className="mt-3 text-xs leading-5 text-muted-foreground">{record.reason}</p><Button asChild variant="outline" className="mt-3 w-full justify-between"><Link href={`/assets/${record.assetId}`}>Xem thiết bị<ArrowRight aria-hidden="true" /></Link></Button></article>)}</div>
          <div className="hidden overflow-x-auto md:block"><Table><TableHeader><TableRow><TableHead>Thiết bị / thời điểm</TableHead><TableHead>Metric</TableHead><TableHead>Thay đổi quan sát</TableHead><TableHead>Mức độ</TableHead><TableHead>Lý do</TableHead><TableHead className="text-right">Score</TableHead><TableHead><span className="sr-only">Thao tác</span></TableHead></TableRow></TableHeader><TableBody>{filteredAnomalies.map((record) => <TableRow key={record.id}><TableCell><p className="font-mono text-xs font-medium text-primary">{record.assetId}</p><p className="mt-1 text-xs text-muted-foreground">{record.assetType} · {record.date}</p></TableCell><TableCell className="min-w-40 font-medium">{record.metric}</TableCell><TableCell className="min-w-52 text-muted-foreground">{record.change}</TableCell><TableCell><AnomalySeverityBadge severity={record.severity} /></TableCell><TableCell className="min-w-72 text-xs leading-5 text-muted-foreground">{record.reason}</TableCell><TableCell className="text-right font-semibold tabular-nums">{record.score.toFixed(2)}</TableCell><TableCell className="text-right"><Button asChild variant="ghost" size="icon-sm"><Link href={`/assets/${record.assetId}`} aria-label={`Xem ${record.assetId}`}><ArrowRight aria-hidden="true" /></Link></Button></TableCell></TableRow>)}</TableBody></Table></div>
        </>}
      </DataTableShell>

      <DataTableShell title="Vấn đề lặp lại" description="Nhóm đạt recurrence threshold trong lịch sử ticket">
        {recurringIssues.length === 0 ? <EmptyState title="Chưa có lỗi lặp lại" description="Không có nhóm lỗi nào đạt ngưỡng trong dữ liệu hiện tại." /> : <div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead>Thiết bị</TableHead><TableHead>Nhóm vấn đề</TableHead><TableHead className="text-right">Số lần</TableHead><TableHead className="text-right">Chưa xử lý</TableHead><TableHead>Gần nhất</TableHead><TableHead><span className="sr-only">Thao tác</span></TableHead></TableRow></TableHeader><TableBody>{recurringIssues.map((issue) => <TableRow key={`${issue.assetId}-${issue.category}`}><TableCell className="font-mono text-xs font-medium text-primary">{issue.assetId}</TableCell><TableCell className="font-medium">{issue.category}</TableCell><TableCell className="text-right font-semibold tabular-nums">{issue.occurrences}</TableCell><TableCell className="text-right tabular-nums">{issue.unresolvedCount}</TableCell><TableCell>{issue.latestDate}</TableCell><TableCell className="text-right"><Button asChild variant="ghost" size="sm"><Link href={`/assets/${issue.assetId}`}>Xem thiết bị</Link></Button></TableCell></TableRow>)}</TableBody></Table></div>}
      </DataTableShell>
    </div>
  );
}

function AnomalyFilter({ id, label, value, onValueChange, options }: { id: string; label: string; value: string; onValueChange: (value: string) => void; options: string[] }) {
  return <div className="space-y-1.5"><Label htmlFor={id}>{label}</Label><Select value={value} onValueChange={onValueChange}><SelectTrigger id={id} className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Tất cả</SelectItem>{options.map((option) => <SelectItem key={option} value={option}>{option}</SelectItem>)}</SelectContent></Select></div>;
}

function buildAnomalyTrend(records: NonNullable<ReturnType<typeof useAnomaliesQuery>["data"]>) {
  const counts = new Map<string, number>();
  records.forEach((record) => counts.set(record.date, (counts.get(record.date) ?? 0) + 1));
  return [...counts.entries()].sort(([left], [right]) => left.localeCompare(right)).slice(-14).map(([date, count]) => ({ date: formatDate(date), count }));
}
