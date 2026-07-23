"use client";

import { CheckCircle2, FileUp } from "lucide-react";
import { useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { InventorySectionNav } from "@/components/inventory-section-nav";
import { PageHeader } from "@/components/page-header";
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
import { Textarea } from "@/components/ui/textarea";
import { ErrorState, LoadingSkeleton } from "@/components/ui-states";
import {
  useAdjustStockMutation,
  useInventoryLocationsQuery,
  useInventoryPartsQuery,
  useReceiveStockMutation,
  useTransferStockMutation,
  useUploadInventoryEvidenceMutation,
} from "@/hooks/use-inventory";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { InventoryMovement } from "@/lib/api/inventory-schemas";
import { permissions } from "@/lib/auth";
import { createInventoryIdempotencyKey } from "@/lib/inventory";

export type InventoryActionView = "receiving" | "transfer" | "adjustment";

const copy: Record<
  InventoryActionView,
  { title: string; description: string }
> = {
  receiving: {
    title: "Nhập kho",
    description:
      "Ghi opening balance hoặc receipt bằng movement append-only có idempotency key.",
  },
  transfer: {
    title: "Chuyển kho",
    description:
      "Transfer-out và transfer-in commit cùng một transaction hoặc cùng rollback.",
  },
  adjustment: {
    title: "Điều chỉnh tồn",
    description:
      "Điều chỉnh có kiểm soát; không sửa trực tiếp balance hoặc movement history.",
  },
};

export function InventoryActionForm({ view }: { view: InventoryActionView }) {
  const heading = copy[view];
  const parts = useInventoryPartsQuery({
    lifecycle_status: "active",
    page: 1,
    page_size: 200,
  });
  const locations = useInventoryLocationsQuery();
  if (parts.isPending || locations.isPending) return <LoadingSkeleton />;
  const error = parts.error ?? locations.error;
  if (error || !parts.data) {
    return (
      <ErrorState
        title="Chưa tải được dữ liệu biểu mẫu"
        description={getApiErrorMessage(error)}
      />
    );
  }
  return (
    <div>
      <PageHeader
        title={heading.title}
        description={heading.description}
        breadcrumbs={[
          { label: "Kho vật tư", href: "/inventory" },
          { label: heading.title },
        ]}
      />
      <InventorySectionNav />
      {view === "receiving" && (
        <ReceivingForm parts={parts.data.items} locations={locations.data ?? []} />
      )}
      {view === "transfer" && (
        <TransferForm parts={parts.data.items} locations={locations.data ?? []} />
      )}
      {view === "adjustment" && (
        <AdjustmentForm
          parts={parts.data.items}
          locations={locations.data ?? []}
        />
      )}
    </div>
  );
}

type PartOption = {
  id: string;
  part_number: string;
  name_vi: string;
  unit_symbol: string;
};
type LocationOption = { id: string; code: string; name: string };

function ReceivingForm({
  parts,
  locations,
}: {
  parts: PartOption[];
  locations: LocationOption[];
}) {
  const [operation, setOperation] = useState<"receipt" | "opening_balance">(
    "receipt",
  );
  const mutation = useReceiveStockMutation(operation);
  const keys = useRef({
    receipt: createInventoryIdempotencyKey("receipt"),
    opening_balance: createInventoryIdempotencyKey("opening-balance"),
  });
  const [movement, setMovement] = useState<InventoryMovement | null>(null);
  const [form, setForm] = useState({
    part_id: "",
    stock_location_id: "",
    quantity: "",
    business_reference: "",
    reason: "",
    unit_cost_snapshot: "",
  });
  const selectedPart = parts.find((part) => part.id === form.part_id);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      const result = await mutation.mutateAsync({
        request: {
          part_id: form.part_id,
          stock_location_id: form.stock_location_id,
          quantity: Number(form.quantity),
          business_reference: form.business_reference,
          occurred_at: null,
          reason: form.reason,
          unit_cost_snapshot: form.unit_cost_snapshot
            ? Number(form.unit_cost_snapshot)
            : null,
        },
        idempotencyKey: keys.current[operation],
      });
      setMovement(result);
      keys.current[operation] = createInventoryIdempotencyKey(
        operation === "receipt" ? "receipt" : "opening-balance",
      );
    } catch {
      // Normalized mutation error is rendered below.
    }
  }

  return (
    <ActionShell
      title={operation === "receipt" ? "Receipt" : "Opening balance"}
      notice="Thao tác thành công chỉ cập nhật transactional inventory; Risk Score và KPI hiện hữu không đổi."
      movement={movement}
    >
      <form onSubmit={submit}>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <Field id="receiving-operation" label="Loại nghiệp vụ">
            <Select
              value={operation}
              onValueChange={(value) =>
                setOperation(value as "receipt" | "opening_balance")
              }
            >
              <SelectTrigger id="receiving-operation" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="receipt">Nhập kho</SelectItem>
                <SelectItem value="opening_balance">Số dư đầu kỳ</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <PartSelect
            id="receiving-part"
            value={form.part_id}
            onChange={(value) => setForm({ ...form, part_id: value })}
            parts={parts}
          />
          <LocationSelect
            id="receiving-location"
            value={form.stock_location_id}
            onChange={(value) =>
              setForm({ ...form, stock_location_id: value })
            }
            locations={locations}
          />
          <Field id="receiving-quantity" label={`Số lượng ${selectedPart?.unit_symbol ?? ""}`}>
            <Input
              id="receiving-quantity"
              type="number"
              min={0.001}
              step="0.001"
              required
              value={form.quantity}
              onChange={(event) => setForm({ ...form, quantity: event.target.value })}
            />
          </Field>
          <Field id="receiving-reference" label="Business reference">
            <Input
              id="receiving-reference"
              required
              value={form.business_reference}
              onChange={(event) =>
                setForm({ ...form, business_reference: event.target.value })
              }
            />
          </Field>
          <Field id="receiving-cost" label="Unit cost snapshot (tùy chọn)">
            <Input
              id="receiving-cost"
              type="number"
              min={0}
              step="0.01"
              value={form.unit_cost_snapshot}
              onChange={(event) =>
                setForm({ ...form, unit_cost_snapshot: event.target.value })
              }
            />
          </Field>
          <div className="sm:col-span-2 xl:col-span-3">
            <Field id="receiving-reason" label="Lý do">
              <Textarea
                id="receiving-reason"
                required
                value={form.reason}
                onChange={(event) => setForm({ ...form, reason: event.target.value })}
              />
            </Field>
          </div>
        </div>
        <MutationFooter
          error={mutation.error}
          pending={mutation.isPending}
          disabled={!form.part_id || !form.stock_location_id}
          label={operation === "receipt" ? "Ghi receipt" : "Ghi opening balance"}
        />
      </form>
      {movement && <EvidenceUpload movement={movement} defaultCategory="receipt_evidence" />}
    </ActionShell>
  );
}

function TransferForm({
  parts,
  locations,
}: {
  parts: PartOption[];
  locations: LocationOption[];
}) {
  const mutation = useTransferStockMutation();
  const key = useRef(createInventoryIdempotencyKey("transfer"));
  const [movement, setMovement] = useState<InventoryMovement | null>(null);
  const [form, setForm] = useState({
    part_id: "",
    source_stock_location_id: "",
    destination_stock_location_id: "",
    quantity: "",
    business_reference: "",
    reason: "",
  });
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      const result = await mutation.mutateAsync({
        request: {
          ...form,
          quantity: Number(form.quantity),
          occurred_at: null,
        },
        idempotencyKey: key.current,
      });
      setMovement(result.transfer_in);
      key.current = createInventoryIdempotencyKey("transfer");
    } catch {
      // Normalized mutation error is rendered below.
    }
  }
  return (
    <ActionShell
      title="Atomic stock transfer"
      notice="Frontend gửi đúng một command. Backend lock hai position và commit cả hai movement."
      movement={movement}
    >
      <form onSubmit={submit}>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <PartSelect
            id="transfer-part"
            value={form.part_id}
            onChange={(value) => setForm({ ...form, part_id: value })}
            parts={parts}
          />
          <LocationSelect
            id="transfer-source"
            label="Kho nguồn"
            value={form.source_stock_location_id}
            onChange={(value) =>
              setForm({ ...form, source_stock_location_id: value })
            }
            locations={locations}
          />
          <LocationSelect
            id="transfer-destination"
            label="Kho đích"
            value={form.destination_stock_location_id}
            onChange={(value) =>
              setForm({ ...form, destination_stock_location_id: value })
            }
            locations={locations.filter(
              (location) => location.id !== form.source_stock_location_id,
            )}
          />
          <Field id="transfer-quantity" label="Số lượng">
            <Input
              id="transfer-quantity"
              type="number"
              min={0.001}
              step="0.001"
              required
              value={form.quantity}
              onChange={(event) => setForm({ ...form, quantity: event.target.value })}
            />
          </Field>
          <Field id="transfer-reference" label="Business reference">
            <Input
              id="transfer-reference"
              required
              value={form.business_reference}
              onChange={(event) =>
                setForm({ ...form, business_reference: event.target.value })
              }
            />
          </Field>
          <div className="sm:col-span-2 xl:col-span-3">
            <Field id="transfer-reason" label="Lý do chuyển">
              <Textarea
                id="transfer-reason"
                required
                value={form.reason}
                onChange={(event) => setForm({ ...form, reason: event.target.value })}
              />
            </Field>
          </div>
        </div>
        <MutationFooter
          error={mutation.error}
          pending={mutation.isPending}
          disabled={
            !form.part_id ||
            !form.source_stock_location_id ||
            !form.destination_stock_location_id
          }
          label="Chuyển kho"
        />
      </form>
      {movement && <EvidenceUpload movement={movement} defaultCategory="transfer_evidence" />}
    </ActionShell>
  );
}

function AdjustmentForm({
  parts,
  locations,
}: {
  parts: PartOption[];
  locations: LocationOption[];
}) {
  const mutation = useAdjustStockMutation();
  const key = useRef(createInventoryIdempotencyKey("adjustment"));
  const [movement, setMovement] = useState<InventoryMovement | null>(null);
  const [form, setForm] = useState({
    part_id: "",
    stock_location_id: "",
    quantity: "",
    adjustment_type: "increase" as
      | "increase"
      | "decrease"
      | "damaged_scrapped",
    business_reference: "",
    reason: "",
    supporting_note: "",
  });
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      const result = await mutation.mutateAsync({
        request: {
          ...form,
          quantity: Number(form.quantity),
          occurred_at: null,
          unit_cost_snapshot: null,
        },
        idempotencyKey: key.current,
      });
      setMovement(result);
      key.current = createInventoryIdempotencyKey("adjustment");
    } catch {
      // Normalized mutation error is rendered below.
    }
  }
  return (
    <ActionShell
      title="Controlled adjustment"
      notice="Giảm tồn và damaged/scrapped bị từ chối nếu làm on-hand âm hoặc thấp hơn reserved."
      movement={movement}
    >
      <form onSubmit={submit}>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <PartSelect
            id="adjustment-part"
            value={form.part_id}
            onChange={(value) => setForm({ ...form, part_id: value })}
            parts={parts}
          />
          <LocationSelect
            id="adjustment-location"
            value={form.stock_location_id}
            onChange={(value) =>
              setForm({ ...form, stock_location_id: value })
            }
            locations={locations}
          />
          <Field id="adjustment-type" label="Loại điều chỉnh">
            <Select
              value={form.adjustment_type}
              onValueChange={(value) =>
                setForm({
                  ...form,
                  adjustment_type: value as typeof form.adjustment_type,
                })
              }
            >
              <SelectTrigger id="adjustment-type" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="increase">Điều chỉnh tăng</SelectItem>
                <SelectItem value="decrease">Điều chỉnh giảm</SelectItem>
                <SelectItem value="damaged_scrapped">Hư hỏng / loại bỏ</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field id="adjustment-quantity" label="Số lượng">
            <Input
              id="adjustment-quantity"
              type="number"
              min={0.001}
              step="0.001"
              required
              value={form.quantity}
              onChange={(event) => setForm({ ...form, quantity: event.target.value })}
            />
          </Field>
          <Field id="adjustment-reference" label="Business reference">
            <Input
              id="adjustment-reference"
              required
              value={form.business_reference}
              onChange={(event) =>
                setForm({ ...form, business_reference: event.target.value })
              }
            />
          </Field>
          <Field id="adjustment-reason" label="Lý do">
            <Input
              id="adjustment-reason"
              required
              value={form.reason}
              onChange={(event) => setForm({ ...form, reason: event.target.value })}
            />
          </Field>
          <div className="sm:col-span-2 xl:col-span-3">
            <Field id="adjustment-note" label="Supporting note">
              <Textarea
                id="adjustment-note"
                required
                value={form.supporting_note}
                onChange={(event) =>
                  setForm({ ...form, supporting_note: event.target.value })
                }
              />
            </Field>
          </div>
        </div>
        <MutationFooter
          error={mutation.error}
          pending={mutation.isPending}
          disabled={!form.part_id || !form.stock_location_id}
          label="Ghi adjustment"
        />
      </form>
      {movement && (
        <EvidenceUpload
          movement={movement}
          defaultCategory={
            form.adjustment_type === "damaged_scrapped"
              ? "damage_evidence"
              : "adjustment_evidence"
          }
        />
      )}
    </ActionShell>
  );
}

function EvidenceUpload({
  movement,
  defaultCategory,
}: {
  movement: InventoryMovement;
  defaultCategory: string;
}) {
  const auth = useAuth();
  const upload = useUploadInventoryEvidenceMutation();
  const [file, setFile] = useState<File | null>(null);
  if (!auth.can(permissions.inventoryAttachmentsCreate)) return null;
  return (
    <div className="mt-5 border-t pt-4">
      <h3 className="text-sm font-semibold">Evidence tùy chọn</h3>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <Input
          type="file"
          aria-label="Chọn inventory evidence"
          accept="image/jpeg,image/png,application/pdf"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <Button
          type="button"
          variant="outline"
          disabled={!file || upload.isPending}
          onClick={() => {
            if (!file) return;
            void upload.mutateAsync({
              movementId: movement.id,
              category: defaultCategory,
              file,
            });
          }}
        >
          <FileUp aria-hidden="true" />
          Tải evidence
        </Button>
      </div>
      {upload.isSuccess && (
        <p role="status" className="mt-2 text-sm text-green-700">
          Đã lưu evidence và checksum.
        </p>
      )}
      {upload.error && (
        <p role="alert" className="mt-2 text-sm text-red-700">
          {getApiErrorMessage(upload.error)}
        </p>
      )}
    </div>
  );
}

function ActionShell({
  title,
  notice,
  movement,
  children,
}: {
  title: string;
  notice: string;
  movement: InventoryMovement | null;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border bg-white p-4 sm:p-5">
      <div>
        <h2 className="font-semibold">{title}</h2>
        <p className="mt-1 text-xs text-muted-foreground">{notice}</p>
      </div>
      {movement && (
        <div
          role="status"
          className="mt-4 flex gap-3 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-900"
        >
          <CheckCircle2 className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
          <div>
            <p className="font-semibold">Đã ghi movement {movement.movement_number}</p>
            <p className="mt-1 text-xs">
              Resulting available: {movement.resulting_available_quantity}{" "}
              {movement.unit_symbol}. Không có recalculation analytics tức thời.
            </p>
          </div>
        </div>
      )}
      <div className="mt-5">{children}</div>
    </section>
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
    <Field id={id} label="Spare part">
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
  label = "Stock location",
  value,
  onChange,
  locations,
}: {
  id: string;
  label?: string;
  value: string;
  onChange: (value: string) => void;
  locations: LocationOption[];
}) {
  return (
    <Field id={id} label={label}>
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

function MutationFooter({
  error,
  pending,
  disabled,
  label,
}: {
  error: Error | null;
  pending: boolean;
  disabled: boolean;
  label: string;
}) {
  return (
    <>
      {error && (
        <p role="alert" className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-800">
          {getApiErrorMessage(error)}
        </p>
      )}
      <div className="mt-4 flex justify-end">
        <Button type="submit" disabled={pending || disabled}>
          {pending ? "Đang ghi..." : label}
        </Button>
      </div>
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
