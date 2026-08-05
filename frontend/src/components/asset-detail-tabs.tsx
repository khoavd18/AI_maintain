"use client";

import { CalendarClock, CircleDot } from "lucide-react";

import { ChartCard } from "@/components/chart-card";
import { RiskContributionChart, RiskHistoryChart } from "@/components/dashboard-charts";
import { DataTableShell } from "@/components/data-table-shell";
import { TicketCard } from "@/components/ticket-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState } from "@/components/ui-states";
import {
  adaptAnomaly,
  adaptMaintenanceLog,
  adaptRiskContributions,
  adaptRiskHistory,
  adaptTicket,
} from "@/lib/adapters";
import type { AssetDetailsResponse } from "@/lib/api/schemas";
import { formatDate, formatTimestamp, presentContributingFactors } from "@/lib/formatters";
import type { Asset } from "@/lib/types";

export function AssetDetailTabs({ asset, details }: { asset: Asset; details: AssetDetailsResponse }) {
  const anomalies = details.recent_anomalies.map(adaptAnomaly);
  const tickets = details.recent_tickets.map(adaptTicket);
  const maintenance = details.recent_maintenance_logs.map(adaptMaintenanceLog);
  const history = adaptRiskHistory(details.risk_history);
  const contributions = adaptRiskContributions(details.latest_risk);
  const explanations = presentContributingFactors(details.risk_contributing_factors);

  return (
    <Tabs defaultValue="ticket" className="mt-6">
      <div className="overflow-x-auto pb-1">
        <TabsList aria-label="Thông tin chi tiết thiết bị" className="min-w-max">
          <TabsTrigger value="ticket">Sự cố</TabsTrigger>
          <TabsTrigger value="maintenance">Lịch sử bảo trì</TabsTrigger>
          <TabsTrigger value="risk">Chỉ số ưu tiên</TabsTrigger>
          <TabsTrigger value="anomaly">Tín hiệu bất thường</TabsTrigger>
          <TabsTrigger value="recurring">Lỗi lặp lại</TabsTrigger>
          <TabsTrigger value="metadata">Thông tin kỹ thuật</TabsTrigger>
        </TabsList>
      </div>

      <TabsContent value="risk" className="mt-4">
        {!details.latest_risk ? (
          <Card><EmptyState title="Chưa có chỉ số ưu tiên" description="Đợt phân tích hiện tại chưa có kết quả cho thiết bị này." /></Card>
        ) : (
          <>
            <div className="grid gap-4 xl:grid-cols-2">
              <ChartCard title="Yếu tố tạo chỉ số ưu tiên" description="Các yếu tố trong đợt phân tích gần nhất" summary={`Chỉ số ${details.latest_risk.final_risk_score.toFixed(2)} dùng để ưu tiên kiểm tra, không phải xác suất hỏng hóc.`}>
                <RiskContributionChart data={contributions} assetId={asset.id} />
              </ChartCard>
              <ChartCard title="Lịch sử chỉ số ưu tiên" description="Các ngày có dữ liệu phân tích" summary={`Điểm mới nhất ${details.latest_risk.final_risk_score.toFixed(2)} ở mức ${details.latest_risk.risk_level}.`}>
                <RiskHistoryChart data={history} assetId={asset.id} />
              </ChartCard>
            </div>
            <Card className="mt-4">
              <CardHeader><CardTitle>Giải thích theo yếu tố</CardTitle></CardHeader>
              <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {contributions.filter((item) => item.value > 0).map((item) => (
                  <div key={item.factor} className="rounded-lg border p-3"><div className="flex items-center justify-between gap-2"><p className="text-sm font-medium">{item.factor}</p><span className="font-mono text-sm font-semibold text-orange-700">+{item.value.toFixed(2)}</span></div><p className="mt-1 text-xs leading-5 text-muted-foreground">{item.explanation}</p></div>
                ))}
                {explanations.map((explanation) => <p key={explanation} className="rounded-lg bg-muted p-3 text-xs leading-5 text-muted-foreground">{explanation}</p>)}
              </CardContent>
            </Card>
          </>
        )}
      </TabsContent>

      <TabsContent value="anomaly" className="mt-4">
        <DataTableShell title="Tín hiệu bất thường gần đây" description={`Kết quả phân tích liên quan ${asset.id}`}>
          {anomalies.length === 0 ? <EmptyState title="Không có bất thường gần đây" description="Không có tín hiệu được đánh dấu trong phạm vi đang xem." /> : (
            <div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead>Ngày</TableHead><TableHead>Chỉ số đo</TableHead><TableHead>Loại</TableHead><TableHead>Lý do</TableHead><TableHead className="text-right">Điểm</TableHead></TableRow></TableHeader><TableBody>{anomalies.map((record) => <TableRow key={record.id}><TableCell>{record.date}</TableCell><TableCell>{record.metric}</TableCell><TableCell>{record.anomalyType}</TableCell><TableCell className="min-w-72 text-muted-foreground">{record.reason}</TableCell><TableCell className="text-right font-semibold tabular-nums">{record.score.toFixed(2)}</TableCell></TableRow>)}</TableBody></Table></div>
          )}
        </DataTableShell>
      </TabsContent>

      <TabsContent value="ticket" className="mt-4">
        {tickets.length === 0 ? <Card><EmptyState title="Chưa có phiếu sự cố" description="Thiết bị chưa có phiếu sự cố trong phạm vi đang xem." /></Card> : <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{tickets.map((ticket) => <TicketCard key={ticket.id} ticket={ticket} />)}</div>}
      </TabsContent>

      <TabsContent value="maintenance" className="mt-4">
        <Card><CardHeader><CardTitle>Lịch sử bảo trì gần đây</CardTitle></CardHeader><CardContent>
          {maintenance.length ? <ol className="relative ml-2 border-l">{maintenance.map((event) => <li key={event.id} className="relative pb-6 pl-6 last:pb-0"><span className="absolute -left-2 top-0 flex size-4 items-center justify-center rounded-full bg-white ring-2 ring-primary"><CircleDot className="size-2 text-primary" aria-hidden="true" /></span><div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between"><div><p className="font-mono text-xs font-medium text-primary">{event.id}</p><p className="mt-1 text-sm font-medium">{event.actions}</p><p className="mt-1 text-xs text-muted-foreground">{event.technician}</p></div><div className="shrink-0 text-left sm:text-right"><p className="text-xs font-medium">{event.date}</p><p className="mt-1 text-xs text-muted-foreground">{event.result}</p></div></div>{event.followUp && <p className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-amber-700"><CalendarClock className="size-3.5" aria-hidden="true" />Cần theo dõi, lịch kế tiếp {event.nextMaintenance}</p>}</li>)}</ol> : <EmptyState title="Chưa có bản ghi bảo trì" description="Không có bản ghi bảo trì trong phạm vi dữ liệu đang xem." />}
        </CardContent></Card>
      </TabsContent>

      <TabsContent value="recurring" className="mt-4">
        <DataTableShell title="Vấn đề lặp lại" description="Nhóm theo nguyên nhân trong lịch sử phiếu sự cố">
          {details.recurring_issues.length === 0 ? <EmptyState title="Chưa có nhóm lỗi" description="Không có lịch sử đủ để tạo nhóm lỗi cho thiết bị này." /> : <div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead>Nhóm lỗi</TableHead><TableHead className="text-right">Số lần</TableHead><TableHead className="text-right">Chưa xử lý</TableHead><TableHead>Gần nhất</TableHead><TableHead>Kết luận</TableHead></TableRow></TableHeader><TableBody>{details.recurring_issues.map((issue) => <TableRow key={`${issue.asset_id}-${issue.failure_category}`}><TableCell className="font-medium">{issue.failure_category}</TableCell><TableCell className="text-right tabular-nums">{issue.occurrence_count}</TableCell><TableCell className="text-right tabular-nums">{issue.unresolved_count}</TableCell><TableCell>{formatTimestamp(issue.last_occurrence)}</TableCell><TableCell>{issue.recurrence_flag ? "Đạt ngưỡng lặp lại" : `Chưa đạt ngưỡng ${issue.recurrence_threshold}`}</TableCell></TableRow>)}</TableBody></Table></div>}
        </DataTableShell>
      </TabsContent>

      <TabsContent value="metadata" className="mt-4">
        <Card><CardHeader><CardTitle>Thông tin thiết bị</CardTitle></CardHeader><CardContent className="grid gap-x-8 gap-y-3 md:grid-cols-2"><FactRow label="Mã thiết bị" value={asset.id} /><FactRow label="Tên thiết bị" value={asset.name} /><FactRow label="Loại thiết bị" value={asset.type} /><FactRow label="Vị trí" value={asset.location} /><FactRow label="Mức độ quan trọng" value={asset.criticality} /><FactRow label="Trạng thái" value={asset.status} /><FactRow label="Ngày lắp đặt" value={formatDate(details.asset_profile.installation_date)} /><FactRow label="Bảo trì gần nhất" value={asset.lastMaintenance} /><FactRow label="Bảo trì kế tiếp" value={asset.nextMaintenance} /></CardContent></Card>
      </TabsContent>
    </Tabs>
  );
}

function FactRow({ label, value }: { label: string; value: string }) {
  return <div className="flex items-center justify-between gap-4 border-b pb-3 last:border-0 last:pb-0"><span className="text-sm text-muted-foreground">{label}</span><span className="text-right text-sm font-medium">{value}</span></div>;
}
