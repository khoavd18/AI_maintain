"use client";

import Link from "next/link";
import { Activity, Bot, CalendarClock, MapPin, TicketPlus, Wrench } from "lucide-react";

import { AssetDetailTabs } from "@/components/asset-detail-tabs";
import { PageHeader } from "@/components/page-header";
import { MaintenanceBadge, RiskBadge } from "@/components/status-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import { useAssetDetailsQuery } from "@/hooks/use-api-queries";
import { adaptAssetDetails } from "@/lib/adapters";
import { UserSafeApiError, getApiErrorMessage } from "@/lib/api/errors";

export function AssetDetailView({ assetId }: { assetId: string }) {
  const detailsQuery = useAssetDetailsQuery(assetId, 20);

  if (detailsQuery.isPending) {
    return <LoadingSkeleton />;
  }
  if (detailsQuery.isError) {
    const notFound =
      detailsQuery.error instanceof UserSafeApiError && detailsQuery.error.code === "not_found";
    return (
      <ErrorState
        title={notFound ? `Không tìm thấy ${assetId}` : "Chưa tải được chi tiết thiết bị"}
        description={
          notFound
            ? "Asset ID này không có trong danh mục hiện tại. Hãy quay lại danh sách thiết bị."
            : getApiErrorMessage(detailsQuery.error)
        }
        action={
          notFound ? (
            <Button asChild variant="outline"><Link href="/assets">Về danh sách thiết bị</Link></Button>
          ) : (
            <RetryButton onClick={() => void detailsQuery.refetch()} />
          )
        }
      />
    );
  }

  const details = detailsQuery.data;
  const asset = adaptAssetDetails(details);

  return (
    <>
      <PageHeader
        title={asset.name}
        description={`Asset ID: ${asset.id}`}
        breadcrumbs={[
          { label: "Tổng quan", href: "/" },
          { label: "Thiết bị", href: "/assets" },
          { label: asset.id },
        ]}
        actions={
          <>
            <Button asChild title="Ghi ticket sẽ được kết nối ở frontend milestone tiếp theo">
              <Link href={`/tickets?asset=${asset.id}&action=create`}><TicketPlus aria-hidden="true" />Tạo ticket kiểm tra</Link>
            </Button>
            <Button asChild variant="outline" title="Copilot hiện dùng nội dung demo, chưa gọi RAG API">
              <Link href={`/copilot?asset=${asset.id}`}><Bot aria-hidden="true" />Mở Copilot</Link>
            </Button>
          </>
        }
      />

      <Card className="overflow-visible">
        <CardContent className="space-y-5">
          <div className="grid gap-5 md:grid-cols-3 md:items-center xl:grid-cols-[minmax(260px,1.4fr)_repeat(3,minmax(150px,0.7fr))]">
            <div className="min-w-0 md:col-span-3 xl:col-span-1 xl:border-r xl:pr-5">
              <div className="flex flex-wrap items-center gap-2"><Badge variant="outline">{asset.type}</Badge><Badge variant="outline">{asset.status}</Badge></div>
              <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground"><MapPin className="size-4" aria-hidden="true" />{asset.location}</p>
              <p className="mt-2 flex items-center gap-2 text-sm text-muted-foreground"><Wrench className="size-4" aria-hidden="true" />Mức độ quan trọng: <strong className="text-foreground">{asset.criticality}</strong></p>
            </div>

            <SummaryMetric label="Risk hiện tại">
              {details.latest_risk ? <div className="flex items-center gap-2"><span className="text-2xl font-semibold tabular-nums">{details.latest_risk.final_risk_score.toFixed(2)}</span><RiskBadge level={details.latest_risk.risk_level} /></div> : <p className="text-sm text-muted-foreground">Chưa có risk score</p>}
            </SummaryMetric>

            <SummaryMetric label="Bảo trì phòng ngừa">
              {details.preventive_maintenance ? <><MaintenanceBadge status={details.preventive_maintenance.maintenance_status_display} /><p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground"><CalendarClock className="size-3.5" aria-hidden="true" />{asset.overdueDays > 0 ? `${asset.overdueDays} ngày quá hạn` : asset.nextMaintenance}</p></> : <p className="text-sm text-muted-foreground">Chưa có lịch preventive</p>}
            </SummaryMetric>

            <SummaryMetric label="Ticket đang mở"><p className="text-2xl font-semibold tabular-nums">{asset.unresolvedTickets}</p><p className="mt-1 text-xs text-muted-foreground">Trong các ticket gần đây</p></SummaryMetric>
          </div>

          <div className="grid gap-3 border-t pt-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(280px,1fr)]">
            <section aria-labelledby="observed-data" className="rounded-lg border border-orange-200 bg-orange-50 p-3">
              <h2 id="observed-data" className="flex items-center gap-2 text-xs font-semibold uppercase text-orange-900"><Activity className="size-4" aria-hidden="true" />Dữ liệu và yếu tố đo được</h2>
              <p className="mt-2 text-sm font-medium leading-6 text-orange-950">{asset.contributingFactors}</p>
            </section>
            <section aria-labelledby="decision-support" className="rounded-lg border border-blue-200 bg-blue-50 p-3">
              <h2 id="decision-support" className="text-xs font-semibold uppercase text-blue-900">Khuyến nghị hỗ trợ quyết định</h2>
              <p className="mt-2 text-sm font-medium leading-6 text-blue-950">{asset.recommendedAction}</p>
            </section>
          </div>
        </CardContent>
      </Card>

      <AssetDetailTabs asset={asset} details={details} />
    </>
  );
}

function SummaryMetric({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><p className="mb-2 text-xs font-medium text-muted-foreground">{label}</p>{children}</div>;
}
