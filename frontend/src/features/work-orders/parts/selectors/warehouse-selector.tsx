"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { Field } from "../components/section-state";
import type { LocationOption } from "../types";

export function LocationSelect({
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
    <Field id={id} label="Vị trí kho">
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
