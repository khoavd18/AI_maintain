"use client";

import { AlertTriangle, RotateCcw } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ErrorState,
  LoadingSkeleton,
  RetryButton,
} from "@/components/ui-states";
import {
  useInventoryLocationsQuery,
  useInventoryPartsQuery,
  useWorkOrderPartsQuery,
} from "@/hooks/use-inventory";
import { getApiErrorMessage } from "@/lib/api/errors";
import { permissions } from "@/lib/auth";

import { IssuesSection } from "./issues/issues-section";
import { IssueForm } from "./issues/issue-form";
import { PartsKpis } from "./components/quantity-display";
import { RequirementForm } from "./requirements/requirement-form";
import { RequirementsSection } from "./requirements/requirements-section";
import { ReservationForm } from "./reservations/reservation-form";
import { ReservationsSection } from "./reservations/reservations-section";

type WorkOrderPartsPanelProps = {
  workOrderId: string;
};

export function WorkOrderPartsPanel({
  workOrderId,
}: WorkOrderPartsPanelProps) {
  const auth = useAuth();
  const canRead = auth.can(permissions.workOrderPartsRead);
  const canManageRequirements = auth.can(
    permissions.inventoryRequirementsManage,
  );
  const canReserve = auth.can(permissions.inventoryReserve);
  const canIssue = auth.can(permissions.inventoryIssue);
  const needsMasterData = canManageRequirements || canIssue;
  const summary = useWorkOrderPartsQuery(workOrderId, canRead);
  const parts = useInventoryPartsQuery(
    { lifecycle_status: "active", page: 1, page_size: 100 },
    needsMasterData,
  );
  const locations = useInventoryLocationsQuery(false, needsMasterData);

  if (!canRead) return null;
  if (
    summary.isPending ||
    (needsMasterData && (parts.isPending || locations.isPending))
  ) {
    return <LoadingSkeleton />;
  }
  const error = summary.error ?? parts.error ?? locations.error;
  if (error || !summary.data) {
    return (
      <section className="rounded-lg border bg-white">
        <ErrorState
          title="Chưa tải được phụ tùng của công việc"
          description={getApiErrorMessage(error)}
          action={
            <RetryButton
              onClick={() =>
                void Promise.all([
                  summary.refetch(),
                  parts.refetch(),
                  locations.refetch(),
                ])
              }
            />
          }
        />
      </section>
    );
  }

  return (
    <section className="rounded-lg border bg-white p-4 sm:p-5">
      <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-start">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-semibold">Vật tư cho công việc</h2>
            {summary.data.open_shortage_count > 0 && (
              <Badge className="bg-red-50 text-red-700 ring-1 ring-red-200">
                <AlertTriangle aria-hidden="true" />
                {summary.data.open_shortage_count} thiếu hụt
              </Badge>
            )}
            {summary.data.has_unresolved_issued_stock && (
              <Badge className="bg-amber-50 text-amber-800 ring-1 ring-amber-200">
                Có vật tư chưa quyết toán
              </Badge>
            )}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Nhu cầu, đặt trước, xuất dùng, sử dụng và trả kho được theo dõi riêng.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void summary.refetch()}
        >
          <RotateCcw aria-hidden="true" />
          Làm mới
        </Button>
      </div>

      <PartsKpis summary={summary.data} />

      {summary.data.completion_warning && (
        <div className="mt-4 flex gap-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <div>
            <p className="font-medium">Cảnh báo khi hoàn tất</p>
            <p className="mt-0.5 text-xs">{summary.data.completion_warning}</p>
            <p className="mt-1 text-xs">
              Người được ủy quyền cần kiểm tra cảnh báo này trước khi hoàn tất.
            </p>
          </div>
        </div>
      )}

      <Tabs defaultValue="requirements" className="mt-5">
        <TabsList className="max-w-full overflow-x-auto" variant="line">
          <TabsTrigger value="requirements">
            Nhu cầu ({summary.data.requirements.length})
          </TabsTrigger>
          <TabsTrigger value="reservations">
            Đặt trước ({summary.data.reservations.length})
          </TabsTrigger>
          <TabsTrigger value="issues">
            Đã xuất ({summary.data.issues.length})
          </TabsTrigger>
          {(canManageRequirements || canReserve || canIssue) && (
            <TabsTrigger value="actions">Thao tác</TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="requirements" className="pt-4">
          <RequirementsSection requirements={summary.data.requirements} />
        </TabsContent>
        <TabsContent value="reservations" className="pt-4">
          <ReservationsSection
            workOrderId={workOrderId}
            reservations={summary.data.reservations}
            locations={locations.data ?? []}
          />
        </TabsContent>
        <TabsContent value="issues" className="pt-4">
          <IssuesSection
            workOrderId={workOrderId}
            issues={summary.data.issues}
            locations={locations.data ?? []}
          />
        </TabsContent>
        <TabsContent value="actions" className="pt-4">
          <div className="grid gap-4 xl:grid-cols-3">
            {canManageRequirements && parts.data && (
              <RequirementForm
                workOrderId={workOrderId}
                parts={parts.data.items}
                locations={locations.data ?? []}
              />
            )}
            {canReserve && (
              <ReservationForm
                workOrderId={workOrderId}
                requirements={summary.data.requirements}
              />
            )}
            {canIssue && parts.data && (
              <IssueForm
                workOrderId={workOrderId}
                assignedToUserId={summary.data.assigned_to_user_id}
                parts={parts.data.items}
                locations={locations.data ?? []}
                reservations={summary.data.reservations}
              />
            )}
          </div>
        </TabsContent>
      </Tabs>
    </section>
  );
}
