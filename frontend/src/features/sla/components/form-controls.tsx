"use client";

import { getApiErrorMessage } from "@/lib/api/errors";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function FormInput({
  id,
  label,
  value,
  onChange,
  error,
  type = "text",
  disabled = false,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  type?: string;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type={type}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

export function CheckboxField({
  label,
  checked,
  onChange,
  className = "",
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  className?: string;
}) {
  return (
    <label className={`flex items-center gap-2 text-sm ${className}`}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="size-4 rounded border-input"
      />
      {label}
    </label>
  );
}

export function MutationError({ error }: { error: unknown }) {
  return (
    <p
      role="alert"
      className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900"
    >
      {getApiErrorMessage(error)}
    </p>
  );
}

export function ReadOnlyNotice() {
  return (
    <section className="h-fit rounded-lg border bg-white p-4 text-sm text-muted-foreground">
      Vai trò hiện tại có thể xem cấu hình SLA nhưng không có permission chỉnh sửa.
    </section>
  );
}
