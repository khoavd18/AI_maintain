"use client";

import { AlertTriangle, CalendarClock, CircleDot, ClipboardList, Info, Wrench } from "lucide-react";

import { ChartCard } from "@/components/chart-card";
import { RiskContributionChart, RiskHistoryChart } from "@/components/dashboard-charts";
import { DataTableShell } from "@/components/data-table-shell";
import { TicketCard } from "@/components/ticket-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState } from "@/components/ui-states";
import {
  anomalies,
  generatorMaintenance,
  generatorRiskContributions,
  generatorRiskHistory,
} from "@/lib/mock-data";
import type { Asset, RiskContribution, Ticket } from "@/lib/types";

interface AssetDetailTabsProps {
  asset: Asset;
  assetTickets: Ticket[];
}

export function AssetDetailTabs({ asset, assetTickets }: AssetDetailTabsProps) {
  const assetAnomalies = anomalies.filter((record) => record.assetId === asset.id);
  const isPrimaryDemoAsset = asset.id === "GENERATOR_002";
  const history = isPrimaryDemoAsset
    ? generatorRiskHistory
    : [0.78, 0.82, 0.85, 0.88, 0.92, 0.96, 1].map((factor, index) => ({
        date: `${24 + index}/04`,
        score: Number((asset.riskScore * factor).toFixed(2)),
      }));
  const contributions = isPrimaryDemoAsset
    ? generatorRiskContributions
    : buildMockContributions(asset);

  return (
    <Tabs defaultValue="overview" className="mt-6">
      <div className="overflow-x-auto pb-1">
        <TabsList aria-label="Thông tin chi tiết thiết bị" className="min-w-max">
          <TabsTrigger value="overview">Tổng quan</TabsTrigger>
          <TabsTrigger value="risk">Risk</TabsTrigger>
          <TabsTrigger value="anomaly">Anomaly</TabsTrigger>
          <TabsTrigger value="ticket">Ticket</TabsTrigger>
          <TabsTrigger value="maintenance">Bảo trì</TabsTrigger>
        </TabsList>
      </div>

      <TabsContent value="overview" className="mt-4">
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader><CardTitle>Dữ liệu quan sát</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <FactRow label="Trạng thái vận hành" value={asset.status} />
              <FactRow label="Lần bảo trì gần nhất" value={asset.lastMaintenance} />
              <FactRow label="Lần bảo trì kế tiếp" value={asset.nextMaintenance} />
              <FactRow label="Ticket chưa xử lý" value={`${asset.unresolvedTickets}`} />
              <div className="rounded-lg border border-orange-200 bg-orange-50 p-3">
                <p className="flex items-center gap-2 text-xs font-semibold text-orange-900">
                  <AlertTriangle className="size-4" aria-hidden="true" />
                  Bất thường gần nhất
                </p>
                <p className="mt-1 text-sm leading-6 text-orange-950">{asset.latestAnomaly}</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Khuyến nghị hỗ trợ</CardTitle></CardHeader>
            <CardContent>
              <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
                <p className="flex items-center gap-2 text-xs font-semibold text-blue-900">
                  <ClipboardList className="size-4" aria-hidden="true" />
                  Hành động gợi ý
                </p>
                <p className="mt-2 text-sm leading-6 text-blue-950">{asset.recommendedAction}</p>
              </div>
              <div className="mt-4 flex gap-2 text-xs leading-5 text-muted-foreground">
                <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                <p>Quản lý và kỹ thuật viên xác minh hiện trường trước khi quyết định công việc bảo trì.</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </TabsContent>

      <TabsContent value="risk" className="mt-4">
        <div className="grid gap-4 xl:grid-cols-2">
          <ChartCard
            title="Đóng góp vào risk score"
            description="Các thành phần giải thích điểm ưu tiên hiện tại"
            summary={`Tổng đóng góp mô phỏng bằng risk score ${asset.riskScore.toFixed(2)}; đây không phải xác suất hỏng hóc.`}
          >
            <RiskContributionChart data={contributions} assetId={asset.id} />
          </ChartCard>
          <ChartCard
            title="Lịch sử risk score"
            description="Bảy ngày trong batch gần nhất"
            summary={`Điểm mới nhất ${asset.riskScore.toFixed(2)} ở mức ${asset.riskLevel}.`}
          >
            <RiskHistoryChart data={history} assetId={asset.id} />
          </ChartCard>
        </div>
        <Card className="mt-4">
          <CardHeader><CardTitle>Giải thích theo yếu tố</CardTitle></CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {contributions.map((item) => (
              <div key={item.factor} className="rounded-lg border p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium">{item.factor}</p>
                  <span className="font-mono text-sm font-semibold text-orange-700">+{item.value.toFixed(2)}</span>
                </div>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{item.explanation}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </TabsContent>

      <TabsContent value="anomaly" className="mt-4">
        <DataTableShell title="Bất thường gần đây" description={`Các tín hiệu batch liên quan ${asset.id}`}>
          {assetAnomalies.length === 0 ? (
            <EmptyState title="Không có bất thường gần đây" description="Không có anomaly record trong tập mock hiện tại cho thiết bị này." />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ngày</TableHead>
                    <TableHead>Loại</TableHead>
                    <TableHead>Lý do</TableHead>
                    <TableHead className="text-right">Score</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {assetAnomalies.map((record) => (
                    <TableRow key={record.id}>
                      <TableCell>{record.date}</TableCell>
                      <TableCell>{record.anomalyType}</TableCell>
                      <TableCell className="min-w-72 text-muted-foreground">{record.reason}</TableCell>
                      <TableCell className="text-right font-semibold tabular-nums">{record.score.toFixed(2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </DataTableShell>
      </TabsContent>

      <TabsContent value="ticket" className="mt-4">
        {assetTickets.length === 0 ? (
          <Card><EmptyState title="Chưa có ticket" description="Thiết bị chưa có ticket trong dữ liệu mock hiện tại." /></Card>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {assetTickets.map((ticket) => <TicketCard key={ticket.id} ticket={ticket} />)}
          </div>
        )}
      </TabsContent>

      <TabsContent value="maintenance" className="mt-4">
        <Card>
          <CardHeader><CardTitle>Lịch sử bảo trì gần đây</CardTitle></CardHeader>
          <CardContent>
            {isPrimaryDemoAsset ? (
              <ol className="relative ml-2 border-l">
                {generatorMaintenance.map((event) => (
                  <li key={event.id} className="relative pb-6 pl-6 last:pb-0">
                    <span className="absolute -left-2 top-0 flex size-4 items-center justify-center rounded-full bg-white ring-2 ring-primary">
                      <CircleDot className="size-2 text-primary" aria-hidden="true" />
                    </span>
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <p className="font-mono text-xs font-medium text-primary">{event.id}</p>
                        <p className="mt-1 text-sm font-medium">{event.actions}</p>
                        <p className="mt-1 text-xs text-muted-foreground">{event.technician}</p>
                      </div>
                      <div className="shrink-0 text-left sm:text-right">
                        <p className="text-xs font-medium">{event.date}</p>
                        <p className="mt-1 text-xs text-muted-foreground">{event.result}</p>
                      </div>
                    </div>
                    {event.followUp && (
                      <p className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-amber-700">
                        <CalendarClock className="size-3.5" aria-hidden="true" />
                        Cần theo dõi
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            ) : (
              <EmptyState title="Chưa có timeline mock" description="Timeline chi tiết đang được minh họa cho GENERATOR_002." icon={Wrench} />
            )}
          </CardContent>
        </Card>
      </TabsContent>
    </Tabs>
  );
}

function FactRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b pb-3 last:border-0 last:pb-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-right text-sm font-medium">{value}</span>
    </div>
  );
}

function buildMockContributions(asset: Asset): RiskContribution[] {
  const values = [0.38, 0.24, 0.18, 0.14, 0.06];
  const labels = ["Bất thường", "Bảo trì", "Ticket", "Mức độ quan trọng", "Runtime"];
  return labels.map((factor, index) => ({
    factor,
    value: Number((asset.riskScore * values[index]).toFixed(2)),
    explanation: "Đóng góp minh họa từ dữ liệu mock cho màn hình chi tiết.",
  }));
}
