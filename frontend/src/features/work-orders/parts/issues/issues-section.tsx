"use client";

import { EmptyState } from "@/components/ui-states";
import type { PartIssue } from "@/lib/api/inventory-schemas";

import { IssueCard } from "./issue-form";
import type { LocationOption } from "../types";

export function IssuesSection({
  workOrderId,
  issues,
  locations,
}: {
  workOrderId: string;
  issues: PartIssue[];
  locations: LocationOption[];
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
