"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ChartCard } from "@/components/chart-card";
import type { RiskContribution } from "@/lib/types";

const axisStyle = { fontSize: 11, fill: "#737373" };

export interface DistributionDatum {
  name: string;
  value: number;
  color: string;
}

function ChartContainer({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div role="img" aria-label={label} className="h-52 w-full">
      <ResponsiveContainer width="100%" height="100%">
        {children}
      </ResponsiveContainer>
    </div>
  );
}

export function OverviewCharts({
  riskDistribution,
  ticketDistribution,
  preventiveDistribution,
}: {
  riskDistribution: DistributionDatum[];
  ticketDistribution: DistributionDatum[];
  preventiveDistribution: DistributionDatum[];
}) {
  const totalAssets = riskDistribution.reduce((sum, item) => sum + item.value, 0);
  const openTickets = ticketDistribution
    .filter((item) => item.name !== "Đã xử lý")
    .reduce((sum, item) => sum + item.value, 0);
  const overdue = preventiveDistribution.find((item) => item.name === "Quá hạn")?.value ?? 0;
  const dueSoon = preventiveDistribution.find((item) => item.name === "Sắp đến hạn")?.value ?? 0;

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <ChartCard
        title="Phân bố mức rủi ro"
        description="Ảnh chụp risk score mới nhất"
        summary={`${totalAssets} thiết bị trong batch analytics hiện tại.`}
      >
        <ChartContainer label="Biểu đồ phân bố mức rủi ro thiết bị">
          <PieChart accessibilityLayer>
            <Pie data={riskDistribution} dataKey="value" nameKey="name" cx="50%" cy="45%" innerRadius={48} outerRadius={75} paddingAngle={2} isAnimationActive={false}>
              {riskDistribution.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
            </Pie>
            <RechartsTooltip />
            <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
          </PieChart>
        </ChartContainer>
      </ChartCard>

      <ChartCard
        title="Trạng thái ticket"
        description="Dữ liệu ticket hiện tại"
        summary={`${openTickets} ticket đang mở và cần điều phối hoặc theo dõi.`}
      >
        <ChartContainer label="Biểu đồ trạng thái ticket">
          <BarChart data={ticketDistribution} margin={{ top: 8, right: 8, left: -20, bottom: 4 }} accessibilityLayer>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
            <XAxis dataKey="name" tick={axisStyle} axisLine={false} tickLine={false} />
            <YAxis tick={axisStyle} allowDecimals={false} axisLine={false} tickLine={false} />
            <RechartsTooltip cursor={{ fill: "#f5f5f5" }} />
            <Bar dataKey="value" name="Ticket" radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {ticketDistribution.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
            </Bar>
          </BarChart>
        </ChartContainer>
      </ChartCard>

      <ChartCard
        title="Bảo trì phòng ngừa"
        description="Theo next maintenance date"
        summary={`${overdue} thiết bị quá hạn và ${dueSoon} thiết bị sắp đến hạn.`}
      >
        <ChartContainer label="Biểu đồ trạng thái bảo trì phòng ngừa">
          <BarChart data={preventiveDistribution} layout="vertical" margin={{ top: 8, right: 12, left: 18, bottom: 4 }} accessibilityLayer>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e5e7eb" />
            <XAxis type="number" tick={axisStyle} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="name" width={80} tick={axisStyle} axisLine={false} tickLine={false} />
            <RechartsTooltip cursor={{ fill: "#f5f5f5" }} />
            <Bar dataKey="value" name="Thiết bị" radius={[0, 4, 4, 0]} isAnimationActive={false}>
              {preventiveDistribution.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
            </Bar>
          </BarChart>
        </ChartContainer>
      </ChartCard>
    </div>
  );
}

export function RiskHistoryChart({ data, assetId }: { data: { date: string; score: number }[]; assetId: string }) {
  return (
    <ChartContainer label={`Biểu đồ lịch sử risk score của ${assetId}`}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: -14, bottom: 4 }} accessibilityLayer>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
        <XAxis dataKey="date" tick={axisStyle} axisLine={false} tickLine={false} minTickGap={24} />
        <YAxis domain={[0, 100]} tick={axisStyle} axisLine={false} tickLine={false} />
        <RechartsTooltip />
        <Line type="monotone" dataKey="score" name="Risk score" stroke="#2563eb" strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
      </LineChart>
    </ChartContainer>
  );
}

export function RiskContributionChart({ data, assetId }: { data: RiskContribution[]; assetId: string }) {
  return (
    <ChartContainer label={`Biểu đồ các yếu tố đóng góp risk score của ${assetId}`}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 34, bottom: 4 }} accessibilityLayer>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e5e7eb" />
        <XAxis type="number" domain={[0, 25]} tick={axisStyle} axisLine={false} tickLine={false} />
        <YAxis type="category" dataKey="factor" width={96} tick={axisStyle} axisLine={false} tickLine={false} />
        <RechartsTooltip />
        <Bar dataKey="value" name="Điểm đóng góp" fill="#ea580c" radius={[0, 4, 4, 0]} isAnimationActive={false} />
      </BarChart>
    </ChartContainer>
  );
}

export function AnomalyTrendChart({ data }: { data: { date: string; count: number }[] }) {
  return (
    <ChartContainer label="Biểu đồ xu hướng số bất thường theo ngày">
      <BarChart data={data} margin={{ top: 8, right: 12, left: -18, bottom: 4 }} accessibilityLayer>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
        <XAxis dataKey="date" tick={axisStyle} axisLine={false} tickLine={false} minTickGap={16} />
        <YAxis tick={axisStyle} allowDecimals={false} axisLine={false} tickLine={false} />
        <RechartsTooltip cursor={{ fill: "#f5f5f5" }} />
        <Bar dataKey="count" name="Số bất thường" fill="#2563eb" radius={[4, 4, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ChartContainer>
  );
}
