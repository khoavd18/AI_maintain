import { BookOpenText, ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { SourceDocument } from "@/lib/types";

export function SourceCard({ source }: { source: SourceDocument }) {
  return (
    <Card size="sm">
      <CardContent className="space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-2">
            <BookOpenText className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
            <div className="min-w-0">
              <p className="font-medium leading-5">{source.title}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">{source.section}</p>
            </div>
          </div>
          <Badge variant="outline">{Math.round(source.relevance * 100)}%</Badge>
        </div>
        <p className="text-xs leading-5 text-muted-foreground">{source.excerpt}</p>
        <span className="inline-flex items-center gap-1 text-xs font-medium text-primary">
          Nguồn mô phỏng
          <ExternalLink className="size-3" aria-hidden="true" />
        </span>
      </CardContent>
    </Card>
  );
}
