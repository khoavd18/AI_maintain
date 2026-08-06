"use client";

import { AlertCircle, RefreshCw, Sparkles, UserRound } from "lucide-react";

import { SourceCard } from "@/components/source-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getApiErrorMessage, UserSafeApiError } from "@/lib/api/errors";
import type { CopilotAskResponse } from "@/lib/api/schemas";
import {
  copilotConfidenceLabel,
  copilotEvidenceLabel,
  copilotEvidenceMessage,
  copilotProvenanceMessage,
  copilotSectionTitle,
  copilotUserText,
  isCopilotSummarySection,
  orderCopilotAnswerSections,
  parseCopilotAnswer,
  retrievalStatusMessage,
  shouldShowSection,
} from "@/lib/copilot";
import { cn } from "@/lib/utils";

export interface ConversationTurn {
  id: number;
  question: string;
  response: CopilotAskResponse;
}

export function ConversationResponse({
  turn,
  onRetry,
}: {
  turn: ConversationTurn;
  onRetry: (question: string) => Promise<void>;
}) {
  const status = retrievalStatusMessage(turn.response.retrieval_status);
  const provenance = copilotProvenanceMessage(turn.response);
  const conversational = turn.response.response_mode === "llm_conversation"
    || turn.response.retrieval_status === "conversation";
  const retrievalSucceeded = ["success", "relevant"].includes(turn.response.retrieval_status);
  const sections = orderCopilotAnswerSections(
    parseCopilotAnswer(turn.response.answer).filter((section) => shouldShowSection(section.title)),
  );
  const summarySections = sections.filter((section) => isCopilotSummarySection(section.title));
  const detailSections = sections.filter((section) => !isCopilotSummarySection(section.title));
  const showAnswerGuidance = conversational || retrievalSucceeded || turn.response.sources.length > 0;
  const safetyMessages = Array.from(new Set([
    turn.response.safety_notice,
    ...(turn.response.structured_answer?.safety_warnings.map((warning) => warning.text) ?? []),
  ].map((message) => message.trim()).filter(Boolean)));
  const retryableFallback = turn.response.retrieval_status === "unavailable" || [
    "llm_timeout",
    "llm_unavailable",
    "llm_provider_error",
  ].includes(turn.response.fallback_reason ?? "");

  return (
    <article className="space-y-4" aria-label="Câu hỏi và câu trả lời từ Trợ lý bảo trì">
      <div className="flex justify-end gap-3">
        <div className="max-w-[85%] break-words whitespace-pre-wrap rounded-lg bg-primary px-4 py-3 text-sm leading-6 text-primary-foreground">
          {turn.question}
        </div>
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-neutral-100 text-neutral-700"><UserRound className="size-4" aria-hidden="true" /></span>
      </div>
      <div className="flex gap-2 sm:gap-3">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-700"><Sparkles className="size-4" aria-hidden="true" /></span>
        <div className="min-w-0 flex-1 space-y-4">
          <StatusCallout status={retrievalSucceeded ? provenance : status} />
          <div className="flex flex-wrap items-center gap-2" aria-label="Mức độ tài liệu tham khảo">
            {!retrievalSucceeded && turn.response.response_mode !== "llm_grounded" && (
              <Badge variant="outline">{provenance.title}</Badge>
            )}
            <Badge variant="outline">{copilotEvidenceLabel(turn.response)}</Badge>
            <Badge variant="outline">{copilotConfidenceLabel(turn.response)}</Badge>
            <p className="w-full text-xs leading-5 text-muted-foreground">
              {copilotEvidenceMessage(turn.response)}
            </p>
          </div>

          {showAnswerGuidance && summarySections.map((section, sectionIndex) => (
            <AnswerSection key={`${section.title}-${sectionIndex}`} section={section} summary />
          ))}

          {safetyMessages.length > 0 && (
            <section
              aria-labelledby={`copilot-safety-${turn.id}`}
              className="flex gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950"
            >
              <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <div>
                <h3 id={`copilot-safety-${turn.id}`} className="font-semibold">Cảnh báo an toàn</h3>
                {safetyMessages.length === 1
                  ? <p className="mt-1 leading-5">{safetyMessages[0]}</p>
                  : (
                    <ul className="mt-1 list-disc space-y-1 pl-5 leading-5">
                      {safetyMessages.map((message) => <li key={message}>{message}</li>)}
                    </ul>
                  )}
              </div>
            </section>
          )}

          {showAnswerGuidance && detailSections.map((section, sectionIndex) => (
            <AnswerSection key={`${section.title}-${sectionIndex}`} section={section} />
          ))}

          {turn.response.sources.length > 0 && (
            <section aria-labelledby={`copilot-sources-${turn.id}`}>
              <h3 id={`copilot-sources-${turn.id}`} className="mb-2 text-sm font-semibold">Nguồn tham khảo</h3>
              <div className="grid gap-3 md:grid-cols-2">
                {turn.response.sources.map((source) => <SourceCard key={`${source.doc_id}-${source.title}`} source={source} />)}
              </div>
            </section>
          )}

          {retryableFallback && (
            <Button type="button" variant="outline" size="sm" onClick={() => void onRetry(turn.question)}>
              <RefreshCw aria-hidden="true" />Thử lại câu hỏi này
            </Button>
          )}
        </div>
      </div>
    </article>
  );
}

function AnswerSection({
  section,
  summary = false,
}: {
  section: ReturnType<typeof parseCopilotAnswer>[number];
  summary?: boolean;
}) {
  const checklist = copilotSectionTitle(section.title) === "Các bước nên kiểm tra";
  return (
    <section className={cn("min-w-0", summary && "rounded-lg bg-muted/40 p-4")}>
      <h3 className="text-sm font-semibold">{copilotSectionTitle(section.title)}</h3>
      <div className="mt-2 space-y-2 break-words text-sm leading-6">
        {section.paragraphs.map((paragraph, index) => (
          <p key={`${paragraph}-${index}`}>{copilotUserText(paragraph)}</p>
        ))}
        {section.items.length > 0 && checklist && (
          <ol className="list-decimal space-y-2 pl-5 marker:font-medium">
            {section.items.map((item, index) => (
              <li key={`${item}-${index}`} className="pl-1">{copilotUserText(item)}</li>
            ))}
          </ol>
        )}
        {section.items.length > 0 && !checklist && (
          <ul className="list-disc space-y-2 pl-5">
            {section.items.map((item, index) => (
              <li key={`${item}-${index}`} className="pl-1">{copilotUserText(item)}</li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function StatusCallout({ status }: { status: { title: string; description: string; tone: "amber" | "red" | "blue" } }) {
  return (
    <div className={cn(
      "rounded-lg border p-3 text-sm",
      status.tone === "red" && "border-red-200 bg-red-50 text-red-950",
      status.tone === "amber" && "border-amber-200 bg-amber-50 text-amber-950",
      status.tone === "blue" && "border-blue-100 bg-blue-50/50 text-blue-950",
    )}>
      <p className="font-semibold">{status.title}</p>
      <p className="mt-1 text-xs leading-5">{status.description}</p>
    </div>
  );
}

export function RequestFailure({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const apiError = error instanceof UserSafeApiError ? error : null;
  const invalidAsset = apiError?.code === "not_found";
  return (
    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-950">
      <p className="font-semibold">{invalidAsset ? "Thiết bị đã chọn không còn hợp lệ" : "Chưa nhận được câu trả lời"}</p>
      <p className="mt-1 leading-5">{getApiErrorMessage(error)}</p>
      <p className="mt-1 text-xs">Câu hỏi vẫn được giữ trong ô nhập để bạn kiểm tra hoặc gửi lại.</p>
      {(apiError?.retryable ?? true) && (
        <Button type="button" variant="outline" size="sm" className="mt-3 bg-white" onClick={onRetry}>
          <RefreshCw aria-hidden="true" />Thử lại
        </Button>
      )}
    </div>
  );
}

export function ContextRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="max-w-[65%] break-words text-right font-medium">{value}</span>
    </div>
  );
}
