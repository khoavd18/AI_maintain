import { BookOpenText, ChevronDown } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { CopilotSource } from "@/lib/api/schemas";

export function SourceCard({ source }: { source: CopilotSource }) {
  return (
    <Card size="sm">
      <CardContent className="space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-2">
            <BookOpenText className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
            <div className="min-w-0">
              <p className="font-medium leading-5">{source.title}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {source.doc_type}{source.asset_type ? ` · ${source.asset_type}` : ""}
              </p>
            </div>
          </div>
          {source.version && <Badge variant="outline">v{source.version}</Badge>}
        </div>
        {source.failure_category && (
          <p className="text-xs leading-5 text-muted-foreground">Nhóm lỗi: {source.failure_category}</p>
        )}
        <details className="group rounded-md border bg-muted/20 px-3 py-2 text-xs">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            Thông tin nguồn
            <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" aria-hidden="true" />
          </summary>
          <dl className="mt-2 grid gap-2 text-muted-foreground">
            <SourceFact label="Mã tài liệu" value={source.document_id ?? source.doc_id} />
            <SourceFact label="Ngày hiệu lực" value={source.effective_date ?? "Chưa khai báo"} />
            <SourceFact label="Nguồn" value={source.source} />
          </dl>
        </details>
      </CardContent>
    </Card>
  );
}

function SourceFact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className="mt-0.5 break-words font-medium text-foreground">{value}</dd>
    </div>
  );
}
