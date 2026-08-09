"use client";

import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { getApiErrorMessage } from "@/lib/api/errors";

export function ActionCard({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-md border p-4">
      <h3 className="font-medium">{title}</h3>
      <p className="mb-4 mt-1 text-xs text-muted-foreground">{description}</p>
      {children}
    </div>
  );
}

export function SubmitFooter({
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

export function Field({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}
