import Link from "next/link";
import { ArrowRight, MapPin, TicketPlus } from "lucide-react";

import { MaintenanceBadge, RiskBadge } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Asset } from "@/lib/types";

export function AssetSummaryCard({ asset }: { asset: Asset }) {
  return (
    <Card size="sm" className="relative transition-colors hover:bg-muted/30 hover:ring-primary/30">
      <Link
        href={`/assets/${asset.id}`}
        aria-label={`Xem chi tiết ${asset.id}`}
        className="absolute inset-0 z-0 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      />
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="font-mono text-xs text-muted-foreground">{asset.id}</p>
            <CardTitle className="mt-1 truncate">{asset.name}</CardTitle>
          </div>
          {asset.riskLevel ? <RiskBadge level={asset.riskLevel} /> : <span className="text-xs text-muted-foreground">Chưa có risk</span>}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <MapPin className="size-3.5" aria-hidden="true" />
          <span className="truncate">{asset.location}</span>
        </p>
        <div className="flex items-center justify-between gap-3">
          {asset.maintenanceStatus ? <MaintenanceBadge status={asset.maintenanceStatus} /> : <span className="text-xs text-muted-foreground">Chưa có lịch</span>}
          <span className="text-sm font-semibold tabular-nums">{asset.riskScore == null ? "--" : asset.riskScore.toFixed(2)}</span>
        </div>
        <div className="flex items-center justify-between border-t pt-3 text-xs text-muted-foreground">
          <span>{asset.unresolvedTickets} ticket đang mở</span>
          <span className="max-w-36 truncate text-right">{asset.recommendedAction}</span>
        </div>
        <div className="relative z-10 flex gap-2">
          <Button asChild variant="outline" className="flex-1 justify-between">
            <Link href={`/assets/${asset.id}`}>
              Xem
              <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
          <Button asChild className="flex-1">
            <Link href={`/tickets?asset=${asset.id}&action=create`}>
              <TicketPlus aria-hidden="true" />
              Tạo ticket
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
