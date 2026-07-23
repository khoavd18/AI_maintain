"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  CircleHelp,
  Loader2,
  RefreshCw,
  Send,
  Sparkles,
  Trash2,
  UserRound,
} from "lucide-react";
import { FormEvent, KeyboardEvent, useMemo, useRef, useState } from "react";

import { useCopilotStatus } from "@/components/copilot-status-provider";
import { SafetyNotice } from "@/components/safety-notice";
import { SourceCard } from "@/components/source-card";
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
  parseCopilotAnswer,
  ragStatusFromResponse,
  retrievalStatusMessage,
  shouldShowSection,
} from "@/lib/copilot";
import { cn } from "@/lib/utils";

const noSelection = "__none__";
const maximumHistory = 8;

interface ConversationTurn {
  id: number;
  question: string;
  response: CopilotAskResponse;
}

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
    initialAssetId ? `Vì sao ${initialAssetId} đang có mức rủi ro hiện tại và cần kiểm tra gì?` : "",
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
      const response = await mutation.mutateAsync({
        question: normalizedQuestion,
        asset_id: selectedAsset?.id,
        top_k: 5,
        failure_category: selectedTicket?.failureCategory,
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
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submitQuestion();
    }
  }

  if (assetsQuery.isPending || ticketsQuery.isPending) return <LoadingSkeleton />;
  if (assetsQuery.isError || ticketsQuery.isError) {
    const failed = assetsQuery.isError ? assetsQuery : ticketsQuery;
    return (
      <ErrorState
        title="Chưa tải được ngữ cảnh Copilot"
        description={getApiErrorMessage(failed.error)}
        action={<RetryButton onClick={() => void failed.refetch()} />}
      />
    );
  }

  return (
    <div className="grid min-w-0 items-start gap-4 xl:grid-cols-[350px_minmax(0,1fr)]">
      <aside aria-label="Ngữ cảnh Copilot" className="min-w-0 space-y-4 xl:sticky xl:top-20">
        <Card>
          <CardHeader><CardTitle>Ngữ cảnh truy xuất</CardTitle></CardHeader>
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
                    <SelectItem key={asset.id} value={asset.id}>{asset.id} · {asset.type}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="copilot-ticket">Ticket liên quan</Label>
              <Select
                disabled={!selectedAsset}
                value={selectedTicketId || noSelection}
                onValueChange={(value) => updateContext(selectedAssetId, value === noSelection ? "" : value)}
              >
                <SelectTrigger id="copilot-ticket" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={noSelection}>Không chọn ticket</SelectItem>
                  {relatedTickets.map((ticket) => (
                    <SelectItem key={ticket.id} value={ticket.id}>{ticket.id} · {ticket.failureCategory}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {contextInvalid && (
              <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-950">
                Asset hoặc ticket từ đường dẫn không tồn tại hoặc không cùng quan hệ. Hãy chọn lại ngữ cảnh.
              </div>
            )}
            <ContextRow
              label="Nguồn ngữ cảnh"
              value={initialAssetId || initialTicketId ? "Stable ID từ URL" : "Chọn tại trang Copilot"}
            />
          </CardContent>
        </Card>

        {selectedAsset ? (
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <div><CardTitle>{selectedAsset.id}</CardTitle><p className="mt-1 text-xs text-muted-foreground">{selectedAsset.name}</p></div>
                {selectedAsset.riskLevel && <RiskBadge level={selectedAsset.riskLevel} />}
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs font-semibold uppercase text-muted-foreground">A. Dữ liệu thiết bị thực tế</p>
              <ContextRow label="Loại" value={selectedAsset.type} />
              <ContextRow label="Vị trí" value={selectedAsset.location} />
              <ContextRow label="Risk score" value={selectedAsset.riskScore?.toFixed(2) ?? "Chưa có"} mono />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm text-muted-foreground">Bảo trì</span>
                {selectedAsset.maintenanceStatus ? <MaintenanceBadge status={selectedAsset.maintenanceStatus} /> : <span className="text-sm">Chưa có</span>}
              </div>
              <div className="border-t pt-3">
                <p className="text-xs font-semibold uppercase text-muted-foreground">Giải thích analytics</p>
                <p className="mt-2 text-sm leading-6">{selectedAsset.contributingFactors}</p>
              </div>
              <div className="rounded-lg border border-blue-100 bg-blue-50/50 p-3">
                <p className="text-xs font-semibold uppercase text-blue-800">Khuyến nghị tham khảo</p>
                <p className="mt-1 text-sm leading-5">{selectedAsset.recommendedAction}</p>
              </div>
              <Button asChild variant="outline" className="w-full">
                <Link href={`/assets/${selectedAsset.id}`}>Mở hồ sơ thiết bị</Link>
              </Button>
            </CardContent>
          </Card>
        ) : (
          <Card><CardContent className="py-5 text-sm text-muted-foreground">Chọn thiết bị để thêm asset context vào câu hỏi.</CardContent></Card>
        )}

        {selectedTicket && (
          <Card>
            <CardHeader><CardTitle>Ticket được chọn</CardTitle></CardHeader>
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
              <h2 id="copilot-conversation" className="text-sm font-semibold">Trợ lý bảo trì RAG</h2>
              <p className="truncate text-xs text-muted-foreground">Phản hồi có nguồn từ SOP/checklist trong Qdrant</p>
            </div>
          </div>
          <Badge variant="outline" className={cn("shrink-0", mutation.isPending && "animate-pulse")}>
            {mutation.isPending ? "Đang truy xuất" : "Sẵn sàng"}
          </Badge>
        </header>

        <div className="border-b bg-muted/30 px-4 py-3 sm:px-5">
          <p className="text-xs font-semibold text-muted-foreground">Câu hỏi gợi ý theo loại thiết bị</p>
          <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
            {suggestions.map((suggestion) => (
              <Button
                key={suggestion}
                type="button"
                variant="outline"
                size="sm"
                className="shrink-0 bg-white"
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

        <ScrollArea className="h-[min(58vh,620px)] min-h-[360px]">
          <div className="space-y-6 p-4 sm:p-6" aria-live="polite" aria-busy={mutation.isPending}>
            {history.length === 0 && !mutation.isPending && (
              <div className="flex min-h-48 flex-col items-center justify-center rounded-lg border border-dashed p-6 text-center">
                <CircleHelp className="size-7 text-blue-700" aria-hidden="true" />
                <h3 className="mt-3 text-sm font-semibold">Đặt câu hỏi theo ngữ cảnh hiện trường</h3>
                <p className="mt-1 max-w-md text-xs leading-5 text-muted-foreground">Copilot chỉ sử dụng tài liệu đạt ngưỡng retrieval hiện có và luôn hiển thị nguồn khi tìm thấy.</p>
              </div>
            )}

            {history.map((turn) => <ConversationResponse key={turn.id} turn={turn} onRetry={submitQuestion} />)}

            {mutation.isPending && (
              <div role="status" className="flex items-center gap-3 rounded-lg border bg-muted/30 p-4 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                Đang truy xuất SOP/checklist và kiểm tra mức liên quan...
              </div>
            )}

            {mutation.isError && (
              <RequestFailure error={mutation.error} onRetry={() => void submitQuestion()} />
            )}
          </div>
        </ScrollArea>

        <form onSubmit={handleSubmit} className="border-t bg-white p-4 sm:p-5">
          <div className="flex items-center justify-between gap-3">
            <Label htmlFor="copilot-question">Câu hỏi cho Copilot</Label>
            {history.length > 0 && (
              <Button type="button" variant="ghost" size="sm" onClick={() => setHistory([])}>
                <Trash2 aria-hidden="true" />Xóa phiên
              </Button>
            )}
          </div>
          <div className="mt-2 flex items-end gap-2">
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
              placeholder="Hỏi về nguyên nhân, checklist hoặc SOP liên quan..."
              rows={2}
              maxLength={1000}
              aria-describedby="copilot-question-help copilot-question-error"
              aria-invalid={Boolean(validationError)}
              className="min-h-16 resize-none"
            />
            <Button type="submit" size="icon-lg" disabled={!question.trim() || mutation.isPending} aria-label="Gửi câu hỏi">
              {mutation.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Send aria-hidden="true" />}
            </Button>
          </div>
          <div className="mt-2 flex items-start justify-between gap-3 text-xs">
            <p id="copilot-question-help" className="text-muted-foreground">Enter để gửi · Shift+Enter để xuống dòng</p>
            <span className="tabular-nums text-muted-foreground">{question.length}/1.000</span>
          </div>
          {validationError && <p id="copilot-question-error" role="alert" className="mt-2 text-xs font-medium text-red-700">{validationError}</p>}
        </form>
      </section>
    </div>
  );
}

function ConversationResponse({
  turn,
  onRetry,
}: {
  turn: ConversationTurn;
  onRetry: (question: string) => Promise<void>;
}) {
  const status = retrievalStatusMessage(turn.response.retrieval_status);
  const sections = parseCopilotAnswer(turn.response.answer).filter((section) => shouldShowSection(section.title));
  const retryableFallback = turn.response.retrieval_status === "unavailable";

  return (
    <article className="space-y-4">
      <div className="flex justify-end gap-3">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-primary px-4 py-3 text-sm leading-6 text-primary-foreground">{turn.question}</div>
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-neutral-100 text-neutral-700"><UserRound className="size-4" aria-hidden="true" /></span>
      </div>
      <div className="flex gap-3">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-700"><Sparkles className="size-4" aria-hidden="true" /></span>
        <div className="min-w-0 flex-1 space-y-4">
          <StatusCallout status={status} />
          <p className="text-xs font-semibold uppercase text-muted-foreground">B. Hướng dẫn được truy xuất từ SOP</p>
          {sections.map((section, sectionIndex) => (
            <section key={`${section.title}-${sectionIndex}`} className="rounded-lg border bg-white p-4">
              <h3 className="text-sm font-semibold">
                {section.title.toLocaleLowerCase("vi").includes("giới hạn") ? `D. ${section.title}` : section.title}
              </h3>
              <div className="mt-2 space-y-2 text-sm leading-6">
                {section.paragraphs.map((paragraph, index) => <p key={`${paragraph}-${index}`}>{paragraph}</p>)}
                {section.items.length > 0 && (
                  <ol className="space-y-2">
                    {section.items.map((item, index) => (
                      <li key={`${item}-${index}`} className="flex gap-2">
                        <CheckCircle2 className="mt-1 size-4 shrink-0 text-green-600" aria-hidden="true" />
                        <span>
                          {isChecklistSection(section.title) && <strong className="font-medium">Bước {index + 1}: </strong>}
                          {item}
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </section>
          ))}

          {turn.response.sources.length > 0 && (
            <section aria-label="Nguồn tài liệu được truy xuất">
              <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Nguồn tài liệu</h3>
              <div className="grid gap-3 lg:grid-cols-2">
                {turn.response.sources.map((source) => <SourceCard key={`${source.doc_id}-${source.title}`} source={source} />)}
              </div>
            </section>
          )}

          {turn.response.safety_notice && (
            <div role="note" className="flex gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">
              <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <div><p className="font-semibold">C. Lưu ý an toàn</p><p className="mt-1 leading-5">{turn.response.safety_notice}</p></div>
            </div>
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

function isChecklistSection(title: string) {
  const normalized = title.toLocaleLowerCase("vi");
  return normalized.includes("checklist") || normalized.includes("bước kiểm tra");
}

function StatusCallout({ status }: { status: ReturnType<typeof retrievalStatusMessage> }) {
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

function RequestFailure({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const apiError = error instanceof UserSafeApiError ? error : null;
  const invalidAsset = apiError?.code === "not_found";
  return (
    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-950">
      <p className="font-semibold">{invalidAsset ? "Asset context không hợp lệ" : "Chưa nhận được phản hồi từ Copilot"}</p>
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

function ContextRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn("max-w-[65%] break-words text-right font-medium", mono && "font-mono")}>{value}</span>
    </div>
  );
}
