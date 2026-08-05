import { BookOpenText, ChevronDown } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { CopilotSource } from "@/lib/api/schemas";

export function SourceCard({ source }: { source: CopilotSource }) {
  return (
    <Card size="sm">
      <CardContent className="space-y-2">
        <div className="flex min-w-0 items-start gap-2">
          <BookOpenText className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
          <div className="min-w-0">
            <h4 className="break-words font-medium leading-5">{source.title}</h4>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {source.doc_type}{source.asset_type ? ` · ${source.asset_type}` : ""}
            </p>
          </div>
        </div>
        {source.citation_ids.length > 0 && (
          <div className="flex flex-wrap gap-1.5" aria-label="Trích dẫn được dùng trong câu trả lời">
            {source.citation_ids.map((citationId) => (
              <Badge key={citationId} variant="outline" className="max-w-full break-all">
                Trích dẫn [{citationId}]
              </Badge>
            ))}
          </div>
        )}
        <details className="group rounded-md border bg-muted/20 px-3 py-2 text-xs">
          <summary className="flex min-h-6 cursor-pointer list-none items-center justify-between gap-2 rounded-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
            Phạm vi tài liệu
            <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" aria-hidden="true" />
          </summary>
          <dl className="mt-2 grid gap-2 text-muted-foreground">
            {source.failure_category && <SourceFact label="Nhóm sự cố" value={source.failure_category} />}
            {source.version && <SourceFact label="Phiên bản" value={source.version} />}
            <SourceFact label="Ngày hiệu lực" value={formatDate(source.effective_date)} />
          </dl>
        </details>
      </CardContent>
    </Card>
  );
}

function formatDate(value?: string | null): string {
  if (!value) return "Chưa khai báo";
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : value;
}

function SourceFact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className="mt-0.5 break-words font-medium text-foreground">{value}</dd>
    </div>
  );
}
