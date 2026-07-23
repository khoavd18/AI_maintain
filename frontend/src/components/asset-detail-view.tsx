"use client";

import Link from "next/link";
import { Activity, Bot, CalendarClock, MapPin, TicketPlus, Wrench } from "lucide-react";
import { useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { AssetDetailTabs } from "@/components/asset-detail-tabs";
import { AssetManagementTabs } from "@/components/asset-management-tabs";
import { PageHeader } from "@/components/page-header";
import { TicketCreateSheet } from "@/components/ticket-create-sheet";
import { LifecycleBadge, MaintenanceBadge, OperationalBadge, RiskBadge } from "@/components/status-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import { useAssetDetailsQuery, useAssetProfileQuery } from "@/hooks/use-api-queries";
import { adaptAssetDetails, adaptAssetProfile } from "@/lib/adapters";
import { UserSafeApiError, getApiErrorMessage } from "@/lib/api/errors";
import { permissions } from "@/lib/auth";

export function AssetDetailView({ assetId }: { assetId: string }) {
  const auth = useAuth();
  const detailsQuery = useAssetDetailsQuery(assetId, 20);
  const profileQuery = useAssetProfileQuery(assetId);
  const [ticketFormOpen, setTicketFormOpen] = useState(false);
  const [analyticsStale, setAnalyticsStale] = useState(false);

  if (profileQuery.isPending) {
    return <LoadingSkeleton />;
  }
  if (profileQuery.isError) {
    const error = profileQuery.error;
    const notFound =
      error instanceof UserSafeApiError && error.code === "not_found";
    return (
      <ErrorState
        title={notFound ? `Không tìm thấy ${assetId}` : "Chưa tải được chi tiết thiết bị"}
        description={
          notFound
            ? "Asset ID này không có trong danh mục hiện tại. Hãy quay lại danh sách thiết bị."
            : getApiErrorMessage(error)
        }
        action={
          notFound ? (
            <Button asChild variant="outline"><Link href="/assets">Về danh sách thiết bị</Link></Button>
          ) : (
            <RetryButton onClick={() => void profileQuery.refetch()} />
          )
        }
      />
    );
  }

  const details = detailsQuery.data;
  const profile = profileQuery.data;
  const asset = details ? adaptAssetDetails(details) : adaptAssetProfile(profile);
  const ticketCreationAllowed = !["retired", "archived"].includes(profile.lifecycle_status);

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
            {auth.can(permissions.ticketsCreate) && ticketCreationAllowed && <Button type="button" onClick={() => setTicketFormOpen(true)}><TicketPlus aria-hidden="true" />Tạo ticket kiểm tra</Button>}
            {auth.can(permissions.copilotUse) && <Button asChild variant="outline">
              <Link href={`/copilot?asset=${asset.id}`}><Bot aria-hidden="true" />Mở Copilot</Link>
            </Button>}
          </>
        }
      />

      {analyticsStale && <div role="status" className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm font-medium text-amber-950">Dữ liệu phân tích chưa được chạy lại. Risk Score và KPI vẫn thuộc batch gần nhất.</div>}

      <Card className="overflow-visible">
        <CardContent className="space-y-5">
          <div className="grid gap-5 md:grid-cols-3 md:items-center xl:grid-cols-[minmax(260px,1.4fr)_repeat(3,minmax(150px,0.7fr))]">
            <div className="min-w-0 md:col-span-3 xl:col-span-1 xl:border-r xl:pr-5">
              <div className="flex flex-wrap items-center gap-2"><Badge variant="outline">{asset.type}</Badge><LifecycleBadge status={profile.lifecycle_status} label={profile.lifecycle_status_display} /><OperationalBadge status={profile.operational_status} label={profile.operational_status_display} /></div>
              <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground"><MapPin className="size-4" aria-hidden="true" />{profile.location_breadcrumb}</p>
              <p className="mt-2 flex items-center gap-2 text-sm text-muted-foreground"><Wrench className="size-4" aria-hidden="true" />Mức độ quan trọng: <strong className="text-foreground">{asset.criticality}</strong></p>
            </div>

            <SummaryMetric label="Risk hiện tại">
              {details?.latest_risk ? <div className="flex items-center gap-2"><span className="text-2xl font-semibold tabular-nums">{details.latest_risk.final_risk_score.toFixed(2)}</span><RiskBadge level={details.latest_risk.risk_level} /></div> : <p className="text-sm text-muted-foreground">{detailsQuery.isPending ? "Đang tải batch..." : "Chưa có risk score"}</p>}
            </SummaryMetric>

            <SummaryMetric label="Bảo trì phòng ngừa">
              {details?.preventive_maintenance ? <><MaintenanceBadge status={details.preventive_maintenance.maintenance_status_display} /><p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground"><CalendarClock className="size-3.5" aria-hidden="true" />{asset.overdueDays > 0 ? `${asset.overdueDays} ngày quá hạn` : asset.nextMaintenance}</p></> : <p className="text-sm text-muted-foreground">Chưa có latest preventive batch</p>}
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

      <AssetManagementTabs profile={profile} onReload={() => void profileQuery.refetch()} />
      {details ? <AssetDetailTabs asset={asset} details={details} /> : detailsQuery.isError ? <div className="mt-5 rounded-lg border bg-white"><ErrorState title="Analytics batch chưa sẵn sàng" description={getApiErrorMessage(detailsQuery.error)} action={<RetryButton onClick={() => void detailsQuery.refetch()} />} /></div> : <div className="mt-5"><LoadingSkeleton /></div>}
      {auth.can(permissions.ticketsCreate) && ticketCreationAllowed && <TicketCreateSheet
        asset={asset}
        latestAnomaly={details?.recent_anomalies[0]?.anomaly_reasons}
        open={ticketFormOpen}
        onOpenChange={setTicketFormOpen}
        onCreated={() => setAnalyticsStale(true)}
      />}
    </>
  );
}

function SummaryMetric({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><p className="mb-2 text-xs font-medium text-muted-foreground">{label}</p>{children}</div>;
}
