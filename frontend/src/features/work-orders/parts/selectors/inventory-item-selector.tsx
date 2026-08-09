"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { Field } from "../components/section-state";
import type { PartOption } from "../types";

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
