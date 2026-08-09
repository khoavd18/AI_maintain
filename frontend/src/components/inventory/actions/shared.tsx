"use client";

import { CheckCircle2, FileUp } from "lucide-react";
import { useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useUploadInventoryEvidenceMutation } from "@/hooks/use-inventory";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { InventoryMovement } from "@/lib/api/inventory-schemas";
import { permissions } from "@/lib/auth";

export type PartOption = {
  id: string;
  part_number: string;
  name_vi: string;
  unit_symbol: string;
};
export type LocationOption = { id: string; code: string; name: string };

export function PreviewFact({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 text-sm font-semibold tabular-nums">{value}</dd></div>;
}

export function EvidenceUpload({
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

export function ActionShell({
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
            <p className="font-semibold">Đã ghi nhận biến động {movement.movement_number}</p>
            <p className="mt-1 text-xs">
              Số lượng khả dụng sau giao dịch: {movement.resulting_available_quantity}{" "}
              {movement.unit_symbol}.
            </p>
          </div>
        </div>
      )}
      <div className="mt-5">{children}</div>
    </section>
  );
}

export function PartSelect({
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
    <Field id={id} label="Phụ tùng">
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

export function LocationSelect({
  id,
  label = "Vị trí kho",
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

export function MutationFooter({
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

export function Field({
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
