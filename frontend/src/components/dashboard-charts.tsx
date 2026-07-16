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
import {
  anomalyTrend,
  generatorRiskContributions,
  generatorRiskHistory,
  preventiveDistribution,
  riskDistribution,
  ticketStatusDistribution,
} from "@/lib/mock-data";
import type { RiskContribution } from "@/lib/types";

const axisStyle = { fontSize: 11, fill: "#737373" };

function ChartContainer({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div role="img" aria-label={label} className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        {children}
      </ResponsiveContainer>
    </div>
  );
}

export function OverviewCharts() {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <ChartCard
        title="Phân bố mức rủi ro"
        description="Ảnh chụp risk score mới nhất"
        summary="2/27 thiết bị ở mức Cao; chưa có thiết bị ở mức Nghiêm trọng."
      >
        <ChartContainer label="Biểu đồ tròn: 14 thiết bị rủi ro thấp, 11 trung bình, 2 cao, 0 nghiêm trọng">
          <PieChart accessibilityLayer>
            <Pie
              data={riskDistribution}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="45%"
              innerRadius={48}
              outerRadius={75}
              paddingAngle={2}
            >
              {riskDistribution.map((entry) => (
                <Cell key={entry.name} fill={entry.color} />
              ))}
            </Pie>
            <RechartsTooltip />
            <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
          </PieChart>
        </ChartContainer>
      </ChartCard>

      <ChartCard
        title="Trạng thái ticket"
        description="42 ticket trong bộ dữ liệu"
        summary="18 ticket đang mở gồm 7 Mới tạo và 11 Đang xử lý."
      >
        <ChartContainer label="Biểu đồ cột: 7 ticket mới tạo, 11 đang xử lý, 24 đã xử lý">
          <BarChart data={ticketStatusDistribution} margin={{ top: 8, right: 8, left: -20, bottom: 4 }} accessibilityLayer>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
            <XAxis dataKey="name" tick={axisStyle} axisLine={false} tickLine={false} />
            <YAxis tick={axisStyle} allowDecimals={false} axisLine={false} tickLine={false} />
            <RechartsTooltip cursor={{ fill: "#f5f5f5" }} />
            <Bar dataKey="value" name="Ticket" radius={[4, 4, 0, 0]}>
              {ticketStatusDistribution.map((entry) => (
                <Cell key={entry.name} fill={entry.color} />
              ))}
            </Bar>
          </BarChart>
        </ChartContainer>
      </ChartCard>

      <ChartCard
        title="Bảo trì phòng ngừa"
        description="Theo next maintenance date"
        summary="2 thiết bị quá hạn và 2 thiết bị sắp đến hạn bảo trì."
      >
        <ChartContainer label="Biểu đồ cột: 23 thiết bị chưa đến hạn, 2 sắp đến hạn, 2 quá hạn">
          <BarChart data={preventiveDistribution} layout="vertical" margin={{ top: 8, right: 12, left: 18, bottom: 4 }} accessibilityLayer>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e5e7eb" />
            <XAxis type="number" tick={axisStyle} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="name" width={80} tick={axisStyle} axisLine={false} tickLine={false} />
            <RechartsTooltip cursor={{ fill: "#f5f5f5" }} />
            <Bar dataKey="value" name="Thiết bị" radius={[0, 4, 4, 0]}>
              {preventiveDistribution.map((entry) => (
                <Cell key={entry.name} fill={entry.color} />
              ))}
            </Bar>
          </BarChart>
        </ChartContainer>
      </ChartCard>
    </div>
  );
}

export function RiskHistoryChart({
  data = generatorRiskHistory,
  assetId = "GENERATOR_002",
}: {
  data?: { date: string; score: number }[];
  assetId?: string;
}) {
  return (
    <ChartContainer label={`Biểu đồ lịch sử risk score của ${assetId} trong bảy ngày`}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: -14, bottom: 4 }} accessibilityLayer>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
        <XAxis dataKey="date" tick={axisStyle} axisLine={false} tickLine={false} />
        <YAxis domain={[0, 100]} tick={axisStyle} axisLine={false} tickLine={false} />
        <RechartsTooltip />
        <Line type="monotone" dataKey="score" name="Risk score" stroke="#2563eb" strokeWidth={2.5} dot={{ r: 3, fill: "#2563eb" }} />
      </LineChart>
    </ChartContainer>
  );
}

export function RiskContributionChart({
  data = generatorRiskContributions,
  assetId = "GENERATOR_002",
}: {
  data?: RiskContribution[];
  assetId?: string;
}) {
  return (
    <ChartContainer label={`Biểu đồ các yếu tố đóng góp risk score của ${assetId}`}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 34, bottom: 4 }} accessibilityLayer>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e5e7eb" />
        <XAxis type="number" domain={[0, 25]} tick={axisStyle} axisLine={false} tickLine={false} />
        <YAxis type="category" dataKey="factor" width={96} tick={axisStyle} axisLine={false} tickLine={false} />
        <RechartsTooltip />
        <Bar dataKey="value" name="Điểm đóng góp" fill="#ea580c" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ChartContainer>
  );
}

export function AnomalyTrendChart() {
  return (
    <ChartContainer label="Biểu đồ xu hướng số bất thường từ ngày 24 đến 30 tháng 4">
      <BarChart data={anomalyTrend} margin={{ top: 8, right: 12, left: -18, bottom: 4 }} accessibilityLayer>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
        <XAxis dataKey="date" tick={axisStyle} axisLine={false} tickLine={false} />
        <YAxis tick={axisStyle} allowDecimals={false} axisLine={false} tickLine={false} />
        <RechartsTooltip cursor={{ fill: "#f5f5f5" }} />
        <Bar dataKey="count" name="Số bất thường" fill="#2563eb" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ChartContainer>
  );
}
