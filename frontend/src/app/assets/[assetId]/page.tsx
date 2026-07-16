import Link from "next/link";
import { notFound } from "next/navigation";
import { Bot, CalendarClock, MapPin, TicketPlus, Wrench } from "lucide-react";

import { AssetDetailTabs } from "@/components/asset-detail-tabs";
import { PageHeader } from "@/components/page-header";
import { MaintenanceBadge, RiskBadge } from "@/components/status-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { assets, tickets } from "@/lib/mock-data";

export function generateStaticParams() {
  return assets.map((asset) => ({ assetId: asset.id }));
}

export default async function AssetDetailPage({ params }: { params: Promise<{ assetId: string }> }) {
  const { assetId } = await params;
  const asset = assets.find((item) => item.id === assetId);

  if (!asset) {
    notFound();
  }

  const assetTickets = tickets.filter((ticket) => ticket.assetId === asset.id);

  return (
    <>
      <PageHeader
        title={asset.id}
        description={asset.name}
        breadcrumbs={[
          { label: "Tổng quan", href: "/" },
          { label: "Thiết bị", href: "/assets" },
          { label: asset.id },
        ]}
        actions={
          <>
            <Button asChild>
              <Link href={`/tickets?asset=${asset.id}`}>
                <TicketPlus aria-hidden="true" />
                Tạo ticket kiểm tra
              </Link>
            </Button>
            <Button asChild variant="outline">
              <Link href={`/copilot?asset=${asset.id}`}>
                <Bot aria-hidden="true" />
                Mở Copilot
              </Link>
            </Button>
          </>
        }
      />

      <Card>
        <CardContent className="grid gap-5 lg:grid-cols-[minmax(260px,1.4fr)_repeat(3,minmax(150px,0.7fr))] lg:items-center">
          <div className="min-w-0 lg:border-r lg:pr-5">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">{asset.type}</Badge>
              <Badge variant="outline">{asset.status}</Badge>
            </div>
            <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
              <MapPin className="size-4" aria-hidden="true" />
              {asset.location}
            </p>
            <p className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
              <Wrench className="size-4" aria-hidden="true" />
              Mức độ quan trọng: <strong className="text-foreground">{asset.criticality}</strong>
            </p>
          </div>

          <SummaryMetric label="Risk hiện tại">
            <div className="flex items-center gap-2">
              <span className="text-2xl font-semibold tabular-nums">{asset.riskScore.toFixed(2)}</span>
              <RiskBadge level={asset.riskLevel} />
            </div>
          </SummaryMetric>

          <SummaryMetric label="Bảo trì phòng ngừa">
            <MaintenanceBadge status={asset.maintenanceStatus} />
            <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
              <CalendarClock className="size-3.5" aria-hidden="true" />
              {asset.overdueDays > 0 ? `${asset.overdueDays} ngày quá hạn` : asset.nextMaintenance}
            </p>
          </SummaryMetric>

          <SummaryMetric label="Ticket chưa xử lý">
            <p className="text-2xl font-semibold tabular-nums">{asset.unresolvedTickets}</p>
            <p className="mt-1 text-xs text-muted-foreground">Cần điều phối kỹ thuật viên</p>
          </SummaryMetric>
        </CardContent>
      </Card>

      <AssetDetailTabs asset={asset} assetTickets={assetTickets} />
    </>
  );
}

function SummaryMetric({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-2 text-xs font-medium text-muted-foreground">{label}</p>
      {children}
    </div>
  );
}
