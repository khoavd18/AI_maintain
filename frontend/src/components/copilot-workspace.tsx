"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Bot,
  CircleHelp,
  Loader2,
  Send,
  Trash2,
} from "lucide-react";
import { FormEvent, KeyboardEvent, useMemo, useRef, useState } from "react";

import { useCopilotStatus } from "@/components/copilot-status-provider";
import { SafetyNotice } from "@/components/safety-notice";
import { ContextRow, ConversationResponse, RequestFailure, type ConversationTurn } from "@/components/copilot/response-view";
import {
  MaintenanceBadge,
  PriorityBadge,
  RiskBadge,
  TicketStatusBadge,
} from "@/components/status-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import { useAskCopilot } from "@/hooks/use-api-mutations";
import { useAssetsQuery, useTicketsQuery } from "@/hooks/use-api-queries";
import { adaptAsset, adaptTicket } from "@/lib/adapters";
import { getApiErrorMessage, UserSafeApiError } from "@/lib/api/errors";
import type { CopilotAskResponse } from "@/lib/api/schemas";
import {
  getCopilotSuggestions,
  isCopilotSummarySection,
  parseCopilotAnswer,
  ragStatusFromResponse,
} from "@/lib/copilot";
import { cn } from "@/lib/utils";

const noSelection = "__none__";
const maximumHistory = 8;

export function CopilotWorkspace({
  initialAssetId = "",
  initialTicketId = "",
}: {
  initialAssetId?: string;
  initialTicketId?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const assetsQuery = useAssetsQuery({ limit: 1000 });
  const ticketsQuery = useTicketsQuery({ limit: 1000 });
  const mutation = useAskCopilot();
  const { setRagStatus } = useCopilotStatus();
  const [selectedAssetId, setSelectedAssetId] = useState(initialAssetId);
  const [selectedTicketId, setSelectedTicketId] = useState(initialTicketId);
  const [question, setQuestion] = useState(
    initialAssetId ? "Vì sao thiết bị này đang có mức rủi ro hiện tại và cần kiểm tra gì?" : "",
  );
  const [validationError, setValidationError] = useState<string | null>(null);
  const [history, setHistory] = useState<ConversationTurn[]>([]);
  const turnSequence = useRef(0);
  const submitting = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const assets = useMemo(() => (assetsQuery.data ?? []).map(adaptAsset), [assetsQuery.data]);
  const tickets = useMemo(() => (ticketsQuery.data ?? []).map(adaptTicket), [ticketsQuery.data]);
  const selectedAsset = assets.find((asset) => asset.id === selectedAssetId);
  const selectedTicket = tickets.find(
    (ticket) => ticket.id === selectedTicketId && ticket.assetId === selectedAssetId,
  );
  const relatedTickets = tickets.filter((ticket) => ticket.assetId === selectedAssetId);
  const suggestions = getCopilotSuggestions(selectedAsset?.type);
  const contextInvalid =
    (!assetsQuery.isPending && Boolean(selectedAssetId) && !selectedAsset) ||
    (!ticketsQuery.isPending && Boolean(selectedTicketId) && !selectedTicket);

  function updateContext(assetId: string, ticketId = "") {
    setSelectedAssetId(assetId);
    setSelectedTicketId(ticketId);
    setHistory([]);
    mutation.reset();
    setValidationError(null);
    const params = new URLSearchParams();
    if (assetId) params.set("asset", assetId);
    if (ticketId) params.set("ticket", ticketId);
    router.replace(params.size ? `${pathname}?${params}` : pathname, { scroll: false });
  }

  async function submitQuestion(nextQuestion = question) {
    const normalizedQuestion = nextQuestion.trim();
    if (submitting.current || mutation.isPending) return;
    if (!normalizedQuestion) {
      setValidationError("Hãy nhập câu hỏi trước khi gửi.");
      textareaRef.current?.focus();
      return;
    }
    if (normalizedQuestion.length > 1000) {
      setValidationError("Câu hỏi không được vượt quá 1.000 ký tự.");
      textareaRef.current?.focus();
      return;
    }

    setValidationError(null);
    mutation.reset();
    submitting.current = true;
    try {
      const previousTurn = history.at(-1);
      const conversationContext = previousTurn
        ? buildConversationContext(previousTurn.response, selectedAsset?.type, selectedTicket?.failureCategory)
        : null;
      const response = await mutation.mutateAsync({
        question: normalizedQuestion,
        asset_id: selectedAsset?.id,
        top_k: 5,
        failure_category: selectedTicket?.failureCategory,
        ...(conversationContext ? { conversation_context: conversationContext } : {}),
      });
      turnSequence.current += 1;
      setHistory((current) => [
        ...current,
        { id: turnSequence.current, question: normalizedQuestion, response },
      ].slice(-maximumHistory));
      setQuestion("");
      const nextRagStatus = ragStatusFromResponse(response);
      if (nextRagStatus) setRagStatus(nextRagStatus);
    } catch (error) {
      if (error instanceof UserSafeApiError && error.code === "rag_unavailable") {
        setRagStatus("unavailable");
      }
    } finally {
      submitting.current = false;
      window.setTimeout(() => textareaRef.current?.focus(), 0);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitQuestion();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submitQuestion();
    }
  }

  if (assetsQuery.isPending || ticketsQuery.isPending) return <LoadingSkeleton />;
  if (assetsQuery.isError || ticketsQuery.isError) {
    const failed = assetsQuery.isError ? assetsQuery : ticketsQuery;
    return (
      <ErrorState
        title="Chưa tải được thông tin cho Trợ lý bảo trì"
        description={getApiErrorMessage(failed.error)}
        action={<RetryButton onClick={() => void failed.refetch()} />}
      />
    );
  }

  return (
    <div className="grid min-w-0 items-start gap-4 xl:grid-cols-[350px_minmax(0,1fr)]">
      <aside aria-label="Thiết bị và sự cố đã chọn" className="min-w-0 space-y-4 xl:sticky xl:top-20">
        <Card>
          <CardHeader><CardTitle role="heading" aria-level={2}>Thiết bị cần hỗ trợ</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="copilot-asset">Thiết bị</Label>
              <Select
                value={selectedAssetId || noSelection}
                onValueChange={(value) => updateContext(value === noSelection ? "" : value)}
              >
                <SelectTrigger id="copilot-asset" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={noSelection}>Chưa chọn thiết bị</SelectItem>
                  {assets.map((asset) => (
                    <SelectItem key={asset.id} value={asset.id}>{asset.name} · {asset.location}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="copilot-ticket">Sự cố liên quan (không bắt buộc)</Label>
              <Select
                disabled={!selectedAsset}
                value={selectedTicketId || noSelection}
                onValueChange={(value) => updateContext(selectedAssetId, value === noSelection ? "" : value)}
              >
                <SelectTrigger id="copilot-ticket" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={noSelection}>Không chọn sự cố</SelectItem>
                  {relatedTickets.map((ticket) => (
                    <SelectItem key={ticket.id} value={ticket.id}>{ticket.id} · {ticket.failureCategory}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {contextInvalid && (
              <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-950">
                Thiết bị hoặc sự cố trong đường dẫn không còn phù hợp. Hãy chọn lại trước khi đặt câu hỏi.
              </div>
            )}
            {!selectedAsset && (
              <p className="text-sm leading-5 text-muted-foreground">
                Bạn vẫn có thể hỏi chung, nhưng chọn thiết bị sẽ giúp tìm đúng tài liệu hơn.
              </p>
            )}
          </CardContent>
        </Card>

        {selectedAsset && (
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase text-muted-foreground">Thiết bị đã chọn</p>
                  <CardTitle role="heading" aria-level={3} className="mt-1 break-words">
                    {selectedAsset.name}
                  </CardTitle>
                  <p className="mt-1 text-xs text-muted-foreground">Mã thiết bị: {selectedAsset.id}</p>
                </div>
                {selectedAsset.riskLevel && <RiskBadge level={selectedAsset.riskLevel} />}
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <ContextRow label="Loại" value={selectedAsset.type} />
              <ContextRow label="Vị trí" value={selectedAsset.location} />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm text-muted-foreground">Kế hoạch bảo trì</span>
                {selectedAsset.maintenanceStatus ? <MaintenanceBadge status={selectedAsset.maintenanceStatus} /> : <span className="text-sm">Chưa có</span>}
              </div>
              <div className="border-t pt-3">
                <p className="text-xs font-semibold uppercase text-muted-foreground">Tình trạng cần lưu ý</p>
                <p className="mt-2 text-sm leading-6">{selectedAsset.contributingFactors}</p>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase text-muted-foreground">Gợi ý tiếp theo</p>
                <p className="mt-1 text-sm leading-5">{selectedAsset.recommendedAction}</p>
              </div>
              <Button asChild variant="outline" className="w-full">
                <Link href={`/assets/${selectedAsset.id}`}>Mở hồ sơ thiết bị</Link>
              </Button>
            </CardContent>
          </Card>
        )}

        {selectedTicket && (
          <Card>
            <CardHeader><CardTitle role="heading" aria-level={3}>Sự cố liên quan</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs font-medium text-primary">{selectedTicket.id}</span>
                <TicketStatusBadge status={selectedTicket.status} />
                <PriorityBadge priority={selectedTicket.priority} />
              </div>
              <p className="text-sm font-medium leading-5">{selectedTicket.description}</p>
              <ContextRow label="Nhóm lỗi" value={selectedTicket.failureCategory} />
              <ContextRow label="Kỹ thuật viên" value={selectedTicket.technician} />
            </CardContent>
          </Card>
        )}

        <SafetyNotice compact />
      </aside>

      <section aria-labelledby="copilot-conversation" className="min-w-0 overflow-hidden rounded-lg border bg-white">
        <header className="flex items-center justify-between gap-3 border-b px-4 py-3 sm:px-5">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-700"><Bot className="size-4" aria-hidden="true" /></span>
            <div className="min-w-0">
              <h2 id="copilot-conversation" className="text-sm font-semibold">Trợ lý bảo trì</h2>
              <p className="text-xs leading-5 text-muted-foreground">Hướng dẫn dựa trên tài liệu bảo trì đã kiểm soát</p>
            </div>
          </div>
          <Badge
            variant="outline"
            role="status"
            className={cn("shrink-0", mutation.isPending && "animate-pulse motion-reduce:animate-none")}
          >
            {mutation.isPending ? "Đang chuẩn bị" : "Sẵn sàng"}
          </Badge>
        </header>

        <div className="border-b bg-muted/30 px-4 py-3 sm:px-5">
          <p className="text-xs font-semibold text-muted-foreground">Câu hỏi gợi ý</p>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            {suggestions.map((suggestion) => (
              <Button
                key={suggestion}
                type="button"
                variant="outline"
                size="sm"
                className="h-auto min-h-9 justify-start whitespace-normal bg-white px-3 py-2 text-left leading-5"
                disabled={mutation.isPending}
                onClick={() => {
                  setQuestion(suggestion);
                  void submitQuestion(suggestion);
                }}
              >
                {suggestion}
              </Button>
            ))}
          </div>
        </div>

        <ScrollArea className="h-[min(54dvh,620px)] min-h-[320px] sm:min-h-[360px]">
          <div className="space-y-6 p-4 sm:p-6" aria-live="polite" aria-busy={mutation.isPending}>
            {history.length === 0 && !mutation.isPending && (
              <div className="flex min-h-48 flex-col items-center justify-center rounded-lg border border-dashed p-6 text-center">
                <CircleHelp className="size-7 text-blue-700" aria-hidden="true" />
                <h3 className="mt-3 text-sm font-semibold">Bạn cần hỗ trợ việc gì?</h3>
                <p className="mt-1 max-w-md text-xs leading-5 text-muted-foreground">
                  Hỏi về nguyên nhân, lưu ý an toàn hoặc các bước nên kiểm tra. Nguồn tham khảo sẽ được hiển thị khi có tài liệu phù hợp.
                </p>
              </div>
            )}

            {history.map((turn) => <ConversationResponse key={turn.id} turn={turn} onRetry={submitQuestion} />)}

            {mutation.isPending && (
              <div role="status" className="flex items-center gap-3 rounded-lg border bg-muted/30 p-4 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                Đang đối chiếu tài liệu và chuẩn bị câu trả lời...
              </div>
            )}

            {mutation.isError && (
              <RequestFailure error={mutation.error} onRetry={() => void submitQuestion()} />
            )}
          </div>
        </ScrollArea>

        <form onSubmit={handleSubmit} className="border-t bg-white p-4 sm:p-5">
          <div className="flex items-center justify-between gap-3">
            <Label htmlFor="copilot-question">Câu hỏi bảo trì</Label>
            {history.length > 0 && (
              <Button type="button" variant="ghost" size="sm" onClick={() => setHistory([])}>
                <Trash2 aria-hidden="true" />Xóa cuộc trò chuyện
              </Button>
            )}
          </div>
          <div className="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
            <Textarea
              ref={textareaRef}
              id="copilot-question"
              value={question}
              onChange={(event) => {
                setQuestion(event.target.value);
                setValidationError(null);
                if (mutation.isError) mutation.reset();
              }}
              onKeyDown={handleKeyDown}
              placeholder="Ví dụ: Tôi nên kiểm tra gì trước tiên?"
              rows={2}
              maxLength={1000}
              aria-describedby={validationError ? "copilot-question-help copilot-question-error" : "copilot-question-help"}
              aria-invalid={Boolean(validationError)}
              className="min-h-16 resize-none"
            />
            <Button type="submit" className="w-full sm:w-auto" disabled={!question.trim() || mutation.isPending}>
              {mutation.isPending
                ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
                : <Send aria-hidden="true" />}
              {mutation.isPending ? "Đang gửi" : "Gửi câu hỏi"}
            </Button>
          </div>
          <div className="mt-2 flex items-start justify-between gap-3 text-xs">
            <p id="copilot-question-help" className="text-muted-foreground">Enter để gửi · Shift+Enter để xuống dòng</p>
            <span className="tabular-nums text-muted-foreground" aria-label={`${question.length} trên 1.000 ký tự`}>
              {question.length}/1.000
            </span>
          </div>
          {validationError && <p id="copilot-question-error" role="alert" className="mt-2 text-xs font-medium text-red-700">{validationError}</p>}
        </form>
      </section>
    </div>
  );
}

function buildConversationContext(
  response: CopilotAskResponse,
  selectedAssetType?: string,
  selectedFailureCategory?: string,
) {
  const citationIds = Array.from(new Set(
    response.sources.flatMap((source) => source.citation_ids),
  )).slice(0, 10);
  const parsedSummary = parseCopilotAnswer(response.answer)
    .find((section) => isCopilotSummarySection(section.title));
  const summary = response.structured_answer?.summary
    ?? [...(parsedSummary?.paragraphs ?? []), ...(parsedSummary?.items ?? [])].join(" ");
  return {
    resolved_asset_type: selectedAssetType ?? response.sources[0]?.asset_type ?? undefined,
    resolved_failure_category: selectedFailureCategory
      ?? response.sources[0]?.failure_category
      ?? undefined,
    previous_source_ids: citationIds,
    previous_answer_summary: summary.slice(0, 600),
  };
}
