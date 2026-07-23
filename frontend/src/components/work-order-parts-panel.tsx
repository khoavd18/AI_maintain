"use client";

import {
  AlertTriangle,
  Boxes,
  CheckCircle2,
  PackageCheck,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { InventoryStatusBadge } from "@/components/inventory-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  EmptyState,
  ErrorState,
  LoadingSkeleton,
  RetryButton,
} from "@/components/ui-states";
import {
  useConsumeStockMutation,
  useCreateRequirementMutation,
  useInventoryLocationsQuery,
  useInventoryPartsQuery,
  useIssueStockMutation,
  useReplaceReservationMutation,
  useReservationActionMutation,
  useReserveStockMutation,
  useReturnStockMutation,
  useWorkOrderPartsQuery,
} from "@/hooks/use-inventory";
import { getApiErrorMessage } from "@/lib/api/errors";
import type {
  PartIssue,
  Requirement,
  Reservation,
  WorkOrderPartsSummary,
} from "@/lib/api/inventory-schemas";
import { permissions } from "@/lib/auth";
import { formatTimestamp } from "@/lib/formatters";
import {
  createInventoryIdempotencyKey,
  formatQuantity,
} from "@/lib/inventory";

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
    { lifecycle_status: "active", page: 1, page_size: 200 },
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
          title="Chưa tải được vật tư của work order"
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
            Planned, reserved, issued, consumed và returned được ghi nhận độc
            lập; số tồn do backend tính.
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
              Đây là warning-only policy; quyết định hoàn tất vẫn thuộc người
              được ủy quyền.
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
            Giữ kho ({summary.data.reservations.length})
          </TabsTrigger>
          <TabsTrigger value="issues">
            Xuất dùng ({summary.data.issues.length})
          </TabsTrigger>
          {(canManageRequirements || canReserve || canIssue) && (
            <TabsTrigger value="actions">Thao tác</TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="requirements" className="pt-4">
          <RequirementsTable requirements={summary.data.requirements} />
        </TabsContent>
        <TabsContent value="reservations" className="pt-4">
          <ReservationsList
            workOrderId={workOrderId}
            reservations={summary.data.reservations}
            locations={locations.data ?? []}
          />
        </TabsContent>
        <TabsContent value="issues" className="pt-4">
          <IssuesList
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

function PartsKpis({ summary }: { summary: WorkOrderPartsSummary }) {
  const metrics = [
    {
      label: "Kế hoạch",
      value: summary.total_planned_quantity,
      icon: Boxes,
    },
    {
      label: "Đã giữ",
      value: summary.total_reserved_quantity,
      icon: ShieldCheck,
    },
    {
      label: "Đã xuất",
      value: summary.total_issued_quantity,
      icon: PackageCheck,
    },
    {
      label: "Net consumed",
      value: summary.net_consumed_quantity,
      icon: CheckCircle2,
    },
  ];
  return (
    <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {metrics.map(({ label, value, icon: Icon }) => (
        <div key={label} className="rounded-md border p-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-muted-foreground">{label}</p>
            <Icon className="size-4 text-primary" aria-hidden="true" />
          </div>
          <p className="mt-1 text-xl font-semibold">
            {new Intl.NumberFormat("vi-VN", {
              maximumFractionDigits: 3,
            }).format(value)}
          </p>
        </div>
      ))}
    </div>
  );
}

function RequirementsTable({
  requirements,
}: {
  requirements: Requirement[];
}) {
  if (!requirements.length) {
    return (
      <EmptyState
        title="Chưa có nhu cầu vật tư"
        description="Chief Engineer có thể thêm planned requirement cho work order."
      />
    );
  }
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Vật tư</TableHead>
            <TableHead>Kho nguồn</TableHead>
            <TableHead>Trạng thái</TableHead>
            <TableHead className="text-right">Kế hoạch</TableHead>
            <TableHead className="text-right">Đã giữ</TableHead>
            <TableHead className="text-right">Đã xuất</TableHead>
            <TableHead className="text-right">Thiếu</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {requirements.map((item) => (
            <TableRow key={item.id}>
              <TableCell>
                <p className="font-medium">{item.part_name_vi}</p>
                <p className="font-mono text-xs text-muted-foreground">
                  {item.part_number}
                </p>
              </TableCell>
              <TableCell>{item.source_stock_location_name}</TableCell>
              <TableCell>
                <InventoryStatusBadge
                  status={item.status}
                  label={item.status_display}
                />
              </TableCell>
              <TableCell className="text-right">
                {formatQuantity(item.planned_quantity, item.unit_symbol)}
              </TableCell>
              <TableCell className="text-right">
                {formatQuantity(item.reserved_quantity, item.unit_symbol)}
              </TableCell>
              <TableCell className="text-right">
                {formatQuantity(item.issued_quantity, item.unit_symbol)}
              </TableCell>
              <TableCell className="text-right font-medium text-red-700">
                {formatQuantity(item.shortage_quantity, item.unit_symbol)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function ReservationsList({
  workOrderId,
  reservations,
  locations,
}: {
  workOrderId: string;
  reservations: Reservation[];
  locations: Array<{ id: string; code: string; name: string }>;
}) {
  const auth = useAuth();
  const action = useReservationActionMutation(workOrderId);
  const keys = useRef(new Map<string, string>());
  const [message, setMessage] = useState<string | null>(null);
  const [replacementId, setReplacementId] = useState<string | null>(null);

  function keyFor(reservationId: string, actionName: string) {
    const mapKey = `${reservationId}:${actionName}`;
    const existing = keys.current.get(mapKey);
    if (existing) return existing;
    const next = createInventoryIdempotencyKey(actionName);
    keys.current.set(mapKey, next);
    return next;
  }

  async function close(
    reservation: Reservation,
    actionName: "release" | "expire",
  ) {
    const mapKey = `${reservation.id}:${actionName}`;
    try {
      await action.mutateAsync({
        reservationId: reservation.id,
        action: actionName,
        request: {
          expected_version: reservation.version,
          reason:
            actionName === "release"
              ? "Giải phóng reservation từ work order workspace"
              : "Xác nhận reservation hết hạn từ work order workspace",
        },
        idempotencyKey: keyFor(reservation.id, actionName),
      });
      keys.current.delete(mapKey);
      setMessage(
        actionName === "release"
          ? "Đã giải phóng reservation."
          : "Đã đánh dấu reservation hết hạn.",
      );
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    }
  }

  if (!reservations.length) {
    return (
      <EmptyState
        title="Chưa có reservation"
        description="Reservation làm giảm available nhưng không giảm on-hand."
      />
    );
  }
  return (
    <div className="space-y-3">
      {reservations.map((item) => (
        <div
          key={item.id}
          className="rounded-md border p-3"
        >
          <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-center">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs font-semibold">
                  {item.reservation_number}
                </span>
                <InventoryStatusBadge
                  status={item.status}
                  label={item.status_display}
                />
              </div>
              <p className="mt-1 text-sm font-medium">
                {item.part_name_vi} · {item.stock_location_name}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Còn {item.remaining_quantity} / {item.quantity} · hết hạn{" "}
                {formatTimestamp(item.expires_at)}
              </p>
            </div>
            {auth.can(permissions.inventoryReserve) &&
              ["active", "partially_issued"].includes(item.status) && (
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={action.isPending}
                    onClick={() => void close(item, "release")}
                  >
                    Giải phóng
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={action.isPending}
                    onClick={() => void close(item, "expire")}
                  >
                    Hết hạn
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={action.isPending}
                    onClick={() =>
                      setReplacementId((current) =>
                        current === item.id ? null : item.id,
                      )
                    }
                  >
                    Thay thế
                  </Button>
                </div>
              )}
          </div>
          {replacementId === item.id && (
            <ReplaceReservationForm
              workOrderId={workOrderId}
              reservation={item}
              locations={locations}
              onDone={() => setReplacementId(null)}
            />
          )}
        </div>
      ))}
      {message && (
        <p
          role="status"
          className="rounded-md bg-blue-50 p-3 text-sm text-blue-800"
        >
          {message}
        </p>
      )}
    </div>
  );
}

function ReplaceReservationForm({
  workOrderId,
  reservation,
  locations,
  onDone,
}: {
  workOrderId: string;
  reservation: Reservation;
  locations: Array<{ id: string; code: string; name: string }>;
  onDone: () => void;
}) {
  const mutation = useReplaceReservationMutation(workOrderId);
  const key = useRef(createInventoryIdempotencyKey("replace-reservation"));
  const [locationId, setLocationId] = useState(reservation.stock_location_id);
  const [quantity, setQuantity] = useState(
    String(reservation.remaining_quantity),
  );
  const [reason, setReason] = useState("Thay thế nguồn giữ vật tư cho work order");
  const [message, setMessage] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      await mutation.mutateAsync({
        reservationId: reservation.id,
        request: {
          quantity: Number(quantity),
          stock_location_id: locationId,
          expected_version: reservation.version,
          expires_at: reservation.expires_at,
          reason: reason.trim(),
        },
        idempotencyKey: key.current,
      });
      key.current = createInventoryIdempotencyKey("replace-reservation");
      setMessage("Đã thay thế reservation trong một transaction.");
      onDone();
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    }
  }

  return (
    <form
      onSubmit={submit}
      className="border-t pt-3 lg:col-span-2 lg:min-w-[520px]"
    >
      <div className="grid gap-2 sm:grid-cols-[1.2fr_0.7fr_1.5fr_auto] sm:items-end">
        <Field id={`replace-location-${reservation.id}`} label="Kho thay thế">
          <Select value={locationId} onValueChange={setLocationId}>
            <SelectTrigger
              id={`replace-location-${reservation.id}`}
              className="w-full"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {locations.map((location) => (
                <SelectItem key={location.id} value={location.id}>
                  {location.code} · {location.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field id={`replace-quantity-${reservation.id}`} label="Số lượng">
          <Input
            id={`replace-quantity-${reservation.id}`}
            required
            type="number"
            min={0.001}
            step="0.001"
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
          />
        </Field>
        <Field id={`replace-reason-${reservation.id}`} label="Lý do">
          <Input
            id={`replace-reason-${reservation.id}`}
            required
            minLength={3}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </Field>
        <Button
          type="submit"
          size="sm"
          disabled={
            mutation.isPending ||
            !locationId ||
            !quantity ||
            !reason.trim()
          }
        >
          Xác nhận
        </Button>
      </div>
      {message && (
        <p role="status" className="mt-2 text-xs text-blue-800">
          {message}
        </p>
      )}
    </form>
  );
}

function IssuesList({
  workOrderId,
  issues,
  locations,
}: {
  workOrderId: string;
  issues: PartIssue[];
  locations: Array<{ id: string; code: string; name: string }>;
}) {
  if (!issues.length) {
    return (
      <EmptyState
        title="Chưa xuất vật tư"
        description="Issue làm giảm on-hand; consumption chỉ được ghi khi kỹ thuật viên xác nhận sử dụng."
      />
    );
  }
  return (
    <div className="space-y-3">
      {issues.map((issue) => (
        <IssueCard
          key={issue.id}
          workOrderId={workOrderId}
          issue={issue}
          locations={locations}
        />
      ))}
    </div>
  );
}

function IssueCard({
  workOrderId,
  issue,
  locations,
}: {
  workOrderId: string;
  issue: PartIssue;
  locations: Array<{ id: string; code: string; name: string }>;
}) {
  const auth = useAuth();
  const consume = useConsumeStockMutation(workOrderId);
  const returnPart = useReturnStockMutation(workOrderId);
  const consumeKey = useRef(createInventoryIdempotencyKey("consume"));
  const returnKey = useRef(createInventoryIdempotencyKey("return"));
  const [consumeQuantity, setConsumeQuantity] = useState("");
  const [returnQuantity, setReturnQuantity] = useState("");
  const [returnLocation, setReturnLocation] = useState(issue.stock_location_id);
  const [message, setMessage] = useState<string | null>(null);

  async function recordConsumption() {
    try {
      await consume.mutateAsync({
        issueId: issue.id,
        request: {
          quantity: Number(consumeQuantity),
          consumed_at: null,
          note: "Kỹ thuật viên xác nhận sử dụng tại work order",
        },
        idempotencyKey: consumeKey.current,
      });
      consumeKey.current = createInventoryIdempotencyKey("consume");
      setConsumeQuantity("");
      setMessage("Đã ghi nhận consumption; tồn kho không bị trừ lần thứ hai.");
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    }
  }

  async function recordReturn() {
    try {
      await returnPart.mutateAsync({
        issueId: issue.id,
        request: {
          stock_location_id: returnLocation,
          quantity: Number(returnQuantity),
          returned_at: null,
          reason: "Hoàn trả vật tư chưa sử dụng từ work order",
        },
        idempotencyKey: returnKey.current,
      });
      returnKey.current = createInventoryIdempotencyKey("return");
      setReturnQuantity("");
      setMessage("Đã hoàn trả vật tư và ghi movement append-only.");
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    }
  }

  return (
    <article className="rounded-md border p-3">
      <div className="flex flex-col justify-between gap-3 lg:flex-row">
        <div>
          <p className="font-medium">{issue.part_name_vi}</p>
          <p className="mt-0.5 font-mono text-xs text-muted-foreground">
            {issue.issue_number} · {issue.part_number}
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            Xuất {formatQuantity(issue.quantity, issue.unit_symbol)} · đã dùng{" "}
            {formatQuantity(issue.consumed_quantity, issue.unit_symbol)} · hoàn{" "}
            {formatQuantity(issue.returned_quantity, issue.unit_symbol)}
          </p>
        </div>
        <div className="text-left text-xs lg:text-right">
          <p className="font-medium">
            Chưa quyết toán{" "}
            {formatQuantity(issue.outstanding_quantity, issue.unit_symbol)}
          </p>
          <p className="mt-1 text-muted-foreground">
            {issue.stock_location_name} · {formatTimestamp(issue.issued_at)}
          </p>
        </div>
      </div>

      {issue.outstanding_quantity > 0 && (
        <div className="mt-3 grid gap-3 border-t pt-3 lg:grid-cols-2">
          {auth.can(permissions.inventoryConsume) && (
            <div className="rounded-md bg-neutral-50 p-3">
              <Label htmlFor={`consume-${issue.id}`}>
                Xác nhận đã sử dụng ({issue.unit_symbol})
              </Label>
              <div className="mt-2 flex gap-2">
                <Input
                  id={`consume-${issue.id}`}
                  type="number"
                  min={0.001}
                  max={issue.outstanding_quantity}
                  step="0.001"
                  value={consumeQuantity}
                  onChange={(event) => setConsumeQuantity(event.target.value)}
                />
                <Button
                  type="button"
                  size="sm"
                  disabled={
                    consume.isPending ||
                    !consumeQuantity ||
                    Number(consumeQuantity) <= 0
                  }
                  onClick={() => void recordConsumption()}
                >
                  Ghi dùng
                </Button>
              </div>
            </div>
          )}
          {auth.can(permissions.inventoryReturn) && (
            <div className="rounded-md bg-neutral-50 p-3">
              <Label htmlFor={`return-${issue.id}`}>
                Hoàn vật tư ({issue.unit_symbol})
              </Label>
              <div className="mt-2 grid gap-2 sm:grid-cols-[1fr_1.4fr_auto]">
                <Input
                  id={`return-${issue.id}`}
                  type="number"
                  min={0.001}
                  max={issue.outstanding_quantity}
                  step="0.001"
                  value={returnQuantity}
                  onChange={(event) => setReturnQuantity(event.target.value)}
                />
                <Select
                  value={returnLocation}
                  onValueChange={setReturnLocation}
                >
                  <SelectTrigger aria-label="Kho nhận vật tư hoàn">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {locations.map((location) => (
                      <SelectItem key={location.id} value={location.id}>
                        {location.code} · {location.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={
                    returnPart.isPending ||
                    !returnQuantity ||
                    !returnLocation ||
                    Number(returnQuantity) <= 0
                  }
                  onClick={() => void recordReturn()}
                >
                  Hoàn kho
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {message && (
        <p
          role="status"
          className="mt-3 rounded-md bg-blue-50 p-2 text-xs text-blue-800"
        >
          {message}
        </p>
      )}
    </article>
  );
}

type PartOption = {
  id: string;
  part_number: string;
  name_vi: string;
  unit_symbol: string;
};
type LocationOption = { id: string; code: string; name: string };

function RequirementForm({
  workOrderId,
  parts,
  locations,
}: {
  workOrderId: string;
  parts: PartOption[];
  locations: LocationOption[];
}) {
  const mutation = useCreateRequirementMutation(workOrderId);
  const [form, setForm] = useState({
    part_id: "",
    source_stock_location_id: "",
    planned_quantity: "",
    required_by_date: "",
    notes: "",
  });
  const [message, setMessage] = useState<string | null>(null);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      await mutation.mutateAsync({
        part_id: form.part_id,
        source_stock_location_id: form.source_stock_location_id,
        planned_quantity: Number(form.planned_quantity),
        required_by_date: form.required_by_date || null,
        notes: form.notes.trim() || null,
      });
      setForm({
        part_id: "",
        source_stock_location_id: "",
        planned_quantity: "",
        required_by_date: "",
        notes: "",
      });
      setMessage("Đã thêm planned requirement.");
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    }
  }
  return (
    <ActionCard title="Thêm nhu cầu" description="Không làm thay đổi tồn kho.">
      <form onSubmit={submit} className="space-y-3">
        <PartSelect
          id="requirement-part"
          value={form.part_id}
          onChange={(value) => setForm({ ...form, part_id: value })}
          parts={parts}
        />
        <LocationSelect
          id="requirement-location"
          value={form.source_stock_location_id}
          onChange={(value) =>
            setForm({ ...form, source_stock_location_id: value })
          }
          locations={locations}
        />
        <Field id="requirement-quantity" label="Số lượng dự kiến">
          <Input
            id="requirement-quantity"
            required
            type="number"
            min={0.001}
            step="0.001"
            value={form.planned_quantity}
            onChange={(event) =>
              setForm({ ...form, planned_quantity: event.target.value })
            }
          />
        </Field>
        <Field id="requirement-date" label="Cần trước ngày">
          <Input
            id="requirement-date"
            type="date"
            value={form.required_by_date}
            onChange={(event) =>
              setForm({ ...form, required_by_date: event.target.value })
            }
          />
        </Field>
        <Field id="requirement-notes" label="Ghi chú">
          <Textarea
            id="requirement-notes"
            value={form.notes}
            onChange={(event) => setForm({ ...form, notes: event.target.value })}
          />
        </Field>
        <SubmitFooter
          mutationError={mutation.error}
          message={message}
          pending={mutation.isPending}
          disabled={!form.part_id || !form.source_stock_location_id}
          label="Thêm nhu cầu"
        />
      </form>
    </ActionCard>
  );
}

function ReservationForm({
  workOrderId,
  requirements,
}: {
  workOrderId: string;
  requirements: Requirement[];
}) {
  const eligible = requirements.filter(
    (item) =>
      item.shortage_quantity > 0 &&
      !["fulfilled", "cancelled"].includes(item.status),
  );
  const mutation = useReserveStockMutation(workOrderId);
  const key = useRef(createInventoryIdempotencyKey("reserve"));
  const [requirementId, setRequirementId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const selected = eligible.find((item) => item.id === requirementId);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!selected) return;
    try {
      await mutation.mutateAsync({
        requirementId: selected.id,
        request: {
          quantity: Number(quantity),
          expected_requirement_version: selected.version,
          expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
          reason: "Giữ vật tư cho work order",
        },
        idempotencyKey: key.current,
      });
      key.current = createInventoryIdempotencyKey("reserve");
      setRequirementId("");
      setQuantity("");
      setExpiresAt("");
      setMessage("Đã giữ vật tư; available giảm, on-hand không đổi.");
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    }
  }
  return (
    <ActionCard title="Giữ vật tư" description="Reserve theo nhu cầu đã lập.">
      {!eligible.length ? (
        <p className="text-sm text-muted-foreground">
          Không có requirement đang thiếu để reserve.
        </p>
      ) : (
        <form onSubmit={submit} className="space-y-3">
          <Field id="reservation-requirement" label="Nhu cầu">
            <Select value={requirementId} onValueChange={setRequirementId}>
              <SelectTrigger id="reservation-requirement" className="w-full">
                <SelectValue placeholder="Chọn vật tư" />
              </SelectTrigger>
              <SelectContent>
                {eligible.map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    {item.part_number} · thiếu {item.shortage_quantity}{" "}
                    {item.unit_symbol}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field id="reservation-quantity" label="Số lượng giữ">
            <Input
              id="reservation-quantity"
              required
              type="number"
              min={0.001}
              max={selected?.shortage_quantity}
              step="0.001"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
            />
          </Field>
          <Field id="reservation-expiry" label="Hết hạn (tùy chọn)">
            <Input
              id="reservation-expiry"
              type="datetime-local"
              value={expiresAt}
              onChange={(event) => setExpiresAt(event.target.value)}
            />
          </Field>
          <SubmitFooter
            mutationError={mutation.error}
            message={message}
            pending={mutation.isPending}
            disabled={!selected}
            label="Giữ vật tư"
          />
        </form>
      )}
    </ActionCard>
  );
}

function IssueForm({
  workOrderId,
  assignedToUserId,
  parts,
  locations,
  reservations,
}: {
  workOrderId: string;
  assignedToUserId: string | null;
  parts: PartOption[];
  locations: LocationOption[];
  reservations: Reservation[];
}) {
  const eligibleReservations = reservations.filter((item) =>
    ["active", "partially_issued"].includes(item.status),
  );
  const mutation = useIssueStockMutation(workOrderId);
  const key = useRef(createInventoryIdempotencyKey("issue"));
  const [reservationId, setReservationId] = useState("none");
  const [partId, setPartId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const selectedReservation = eligibleReservations.find(
    (item) => item.id === reservationId,
  );
  const effectivePartId = selectedReservation?.part_id ?? partId;
  const effectiveLocationId =
    selectedReservation?.stock_location_id ?? locationId;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      await mutation.mutateAsync({
        request: {
          part_id: effectivePartId,
          stock_location_id: effectiveLocationId,
          quantity: Number(quantity),
          requirement_id: selectedReservation?.requirement_id ?? null,
          reservation_id: selectedReservation?.id ?? null,
          issued_to_user_id: assignedToUserId,
          issued_at: null,
          reason: reason.trim(),
        },
        idempotencyKey: key.current,
      });
      key.current = createInventoryIdempotencyKey("issue");
      setReservationId("none");
      setPartId("");
      setLocationId("");
      setQuantity("");
      setReason("");
      setMessage(
        "Đã xuất kho. Consumption chỉ được ghi khi kỹ thuật viên xác nhận.",
      );
    } catch (error) {
      setMessage(getApiErrorMessage(error));
    }
  }
  return (
    <ActionCard title="Xuất vật tư" description="Issue làm giảm on-hand.">
      <form onSubmit={submit} className="space-y-3">
        <Field id="issue-reservation" label="Reservation (tùy chọn)">
          <Select value={reservationId} onValueChange={setReservationId}>
            <SelectTrigger id="issue-reservation" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">Xuất trực tiếp</SelectItem>
              {eligibleReservations.map((item) => (
                <SelectItem key={item.id} value={item.id}>
                  {item.reservation_number} · {item.part_number} · còn{" "}
                  {item.remaining_quantity}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        {!selectedReservation && (
          <>
            <PartSelect
              id="issue-part"
              value={partId}
              onChange={setPartId}
              parts={parts}
            />
            <LocationSelect
              id="issue-location"
              value={locationId}
              onChange={setLocationId}
              locations={locations}
            />
          </>
        )}
        <Field id="issue-quantity" label="Số lượng xuất">
          <Input
            id="issue-quantity"
            required
            type="number"
            min={0.001}
            max={selectedReservation?.remaining_quantity}
            step="0.001"
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
          />
        </Field>
        <Field id="issue-reason" label="Lý do xuất">
          <Textarea
            id="issue-reason"
            required
            minLength={3}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </Field>
        {!assignedToUserId && (
          <p className="rounded-md bg-amber-50 p-2 text-xs text-amber-900">
            Work order chưa phân công; issue sẽ không gán người nhận.
          </p>
        )}
        <SubmitFooter
          mutationError={mutation.error}
          message={message}
          pending={mutation.isPending}
          disabled={!effectivePartId || !effectiveLocationId || !reason.trim()}
          label="Xuất vật tư"
        />
      </form>
    </ActionCard>
  );
}

function PartSelect({
  id,
  value,
  onChange,
  parts,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  parts: PartOption[];
}) {
  return (
    <Field id={id} label="Vật tư">
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue placeholder="Chọn vật tư" />
        </SelectTrigger>
        <SelectContent>
          {parts.map((part) => (
            <SelectItem key={part.id} value={part.id}>
              {part.part_number} · {part.name_vi}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  );
}

function LocationSelect({
  id,
  value,
  onChange,
  locations,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  locations: LocationOption[];
}) {
  return (
    <Field id={id} label="Stock location">
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue placeholder="Chọn kho" />
        </SelectTrigger>
        <SelectContent>
          {locations.map((location) => (
            <SelectItem key={location.id} value={location.id}>
              {location.code} · {location.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  );
}

function ActionCard({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-md border p-4">
      <h3 className="font-medium">{title}</h3>
      <p className="mb-4 mt-1 text-xs text-muted-foreground">{description}</p>
      {children}
    </div>
  );
}

function SubmitFooter({
  mutationError,
  message,
  pending,
  disabled,
  label,
}: {
  mutationError: unknown;
  message: string | null;
  pending: boolean;
  disabled: boolean;
  label: string;
}) {
  const error = mutationError ? getApiErrorMessage(mutationError) : null;
  return (
    <>
      {(error || message) && (
        <p
          role={error ? "alert" : "status"}
          className={
            error
              ? "rounded-md bg-red-50 p-2 text-xs text-red-800"
              : "rounded-md bg-blue-50 p-2 text-xs text-blue-800"
          }
        >
          {error ?? message}
        </p>
      )}
      <Button
        type="submit"
        size="sm"
        disabled={pending || disabled}
        className="w-full"
      >
        {pending ? "Đang ghi..." : label}
      </Button>
    </>
  );
}

function Field({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}
