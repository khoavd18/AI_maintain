"use client";

import type { Requirement } from "@/lib/api/inventory-schemas";

import { RequirementsTable } from "./requirements-table";

export function RequirementsSection({
  requirements,
}: {
  requirements: Requirement[];
}) {
  return <RequirementsTable requirements={requirements} />;
}
