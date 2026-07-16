import Link from "next/link";
import { ArrowRight, MapPin } from "lucide-react";

import { MaintenanceBadge, RiskBadge } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Asset } from "@/lib/types";

export function AssetSummaryCard({ asset }: { asset: Asset }) {
  return (
    <Card size="sm">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="font-mono text-xs text-muted-foreground">{asset.id}</p>
            <CardTitle className="mt-1 truncate">{asset.name}</CardTitle>
          </div>
          <RiskBadge level={asset.riskLevel} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <MapPin className="size-3.5" aria-hidden="true" />
          <span className="truncate">{asset.location}</span>
        </p>
        <div className="flex items-center justify-between gap-3">
          <MaintenanceBadge status={asset.maintenanceStatus} />
          <span className="text-sm font-semibold tabular-nums">{asset.riskScore.toFixed(2)}</span>
        </div>
        <Button asChild variant="outline" className="w-full justify-between">
          <Link href={`/assets/${asset.id}`}>
            Xem chi tiết
            <ArrowRight aria-hidden="true" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}
