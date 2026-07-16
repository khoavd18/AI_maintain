"use client";

import { AlertCircle, Bot, CheckCircle2, Send, Sparkles, UserRound, Wrench } from "lucide-react";
import { FormEvent, useState } from "react";

import { SafetyNotice } from "@/components/safety-notice";
import { SourceCard } from "@/components/source-card";
import { MaintenanceBadge, PriorityBadge, RiskBadge, TicketStatusBadge } from "@/components/status-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { assets, copilotSources, tickets } from "@/lib/mock-data";

const demoAsset = assets.find((asset) => asset.id === "GENERATOR_002")!;
const demoTicket = tickets.find((ticket) => ticket.id === "TCK-000041")!;
const defaultQuestion = "Vì sao GENERATOR_002 đang rủi ro cao và cần kiểm tra gì?";

export function CopilotWorkspace() {
  const [question, setQuestion] = useState("");
  const [displayedQuestion, setDisplayedQuestion] = useState(defaultQuestion);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextQuestion = question.trim();
    if (!nextQuestion) return;
    setDisplayedQuestion(nextQuestion);
    setQuestion("");
  }

  return (
    <div className="grid items-start gap-4 xl:grid-cols-[340px_minmax(0,1fr)]">
      <aside aria-label="Ngữ cảnh Copilot" className="space-y-4 xl:sticky xl:top-20">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <CardTitle>Ngữ cảnh thiết bị</CardTitle>
              <Badge variant="outline">Mock</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <ContextRow label="Asset ID" value={demoAsset.id} mono />
            <ContextRow label="Loại" value={demoAsset.type} />
            <ContextRow label="Vị trí" value={demoAsset.location} />
            <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
              <span className="text-sm text-muted-foreground">Risk</span>
              <div className="flex items-center gap-2">
                <span className="font-semibold tabular-nums">{demoAsset.riskScore.toFixed(2)}</span>
                <RiskBadge level={demoAsset.riskLevel} />
              </div>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm text-muted-foreground">Bảo trì</span>
              <MaintenanceBadge status={demoAsset.maintenanceStatus} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Ticket đang chọn</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs font-medium text-primary">{demoTicket.id}</span>
              <TicketStatusBadge status={demoTicket.status} />
              <PriorityBadge priority={demoTicket.priority} />
            </div>
            <p className="text-sm font-medium leading-5">{demoTicket.summary}</p>
            <ContextRow label="Nhóm lỗi" value={demoTicket.failureCategory} />
            <ContextRow label="Kỹ thuật viên" value={demoTicket.technician} />
          </CardContent>
        </Card>

        <SafetyNotice compact />
      </aside>

      <section aria-labelledby="copilot-conversation" className="overflow-hidden rounded-lg border bg-white">
        <header className="flex items-center justify-between gap-3 border-b px-4 py-3 sm:px-5">
          <div className="flex items-center gap-3">
            <span className="flex size-9 items-center justify-center rounded-lg bg-blue-50 text-blue-700">
              <Bot className="size-4" aria-hidden="true" />
            </span>
            <div>
              <h2 id="copilot-conversation" className="text-sm font-semibold">Trợ lý bảo trì</h2>
              <p className="text-xs text-muted-foreground">Giao diện phản hồi mô phỏng, chưa gọi Qdrant</p>
            </div>
          </div>
          <Badge className="bg-green-50 text-green-700 ring-1 ring-green-200 hover:bg-green-50">Sẵn sàng</Badge>
        </header>

        <ScrollArea className="h-[560px]">
          <div className="space-y-5 p-4 sm:p-6">
            <div className="flex justify-end gap-3">
              <div className="max-w-[85%] rounded-lg bg-primary px-4 py-3 text-sm leading-6 text-primary-foreground">
                {displayedQuestion}
              </div>
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-neutral-100 text-neutral-700">
                <UserRound className="size-4" aria-hidden="true" />
              </span>
            </div>

            <div className="flex gap-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-700">
                <Sparkles className="size-4" aria-hidden="true" />
              </span>
              <div className="min-w-0 flex-1 space-y-4">
                <div className="rounded-lg border border-blue-100 bg-blue-50/50 p-4">
                  <p className="text-xs font-semibold uppercase text-blue-800">Phản hồi mô phỏng</p>
                  <p className="mt-2 text-sm leading-6 text-foreground">
                    GENERATOR_002 được ưu tiên ở mức Cao do nhiều tín hiệu cùng xuất hiện: bảo trì quá hạn 159 ngày, hai ticket chưa hoàn tất và bất thường liên quan điện áp ắc quy cùng runtime.
                  </p>
                  <h3 className="mt-4 text-sm font-semibold">Checklist đề xuất</h3>
                  <ol className="mt-2 space-y-2">
                    {[
                      "Cô lập khu vực và xác nhận điều kiện an toàn trước khi kiểm tra.",
                      "Đo điện áp ắc quy, kiểm tra đầu cực và bộ sạc.",
                      "Kiểm tra mức dầu, nước làm mát, nhiên liệu và dấu hiệu rò rỉ.",
                      "Chạy thử theo SOP; chỉ thử có tải khi đủ điều kiện an toàn.",
                      "Ghi nhận kết quả vào ticket và đánh dấu theo dõi nếu chưa xử lý dứt điểm.",
                    ].map((step, index) => (
                      <li key={step} className="flex gap-2 text-sm leading-6">
                        <CheckCircle2 className="mt-1 size-4 shrink-0 text-green-600" aria-hidden="true" />
                        <span><strong className="font-medium">Bước {index + 1}:</strong> {step}</span>
                      </li>
                    ))}
                  </ol>
                </div>

                <div>
                  <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Nguồn được truy xuất</h3>
                  <div className="grid gap-3 lg:grid-cols-2">
                    {copilotSources.map((source) => <SourceCard key={source.title} source={source} />)}
                  </div>
                </div>

                <SafetyNotice />

                <div role="note" className="flex gap-3 rounded-lg border border-dashed p-3">
                  <AlertCircle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <div>
                    <p className="text-sm font-medium">Ví dụ fallback</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      Không tìm thấy tài liệu đủ liên quan. Hãy kiểm tra SOP được phê duyệt hoặc liên hệ người phụ trách kỹ thuật.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </ScrollArea>

        <form onSubmit={handleSubmit} className="border-t bg-white p-4 sm:p-5">
          <Label htmlFor="copilot-question">Câu hỏi cho Copilot</Label>
          <div className="mt-2 flex items-end gap-2">
            <Textarea
              id="copilot-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Hỏi về nguyên nhân, checklist hoặc SOP liên quan..."
              rows={2}
              className="min-h-16 resize-none"
            />
            <Button type="submit" size="icon-lg" disabled={!question.trim()} aria-label="Gửi câu hỏi mô phỏng">
              <Send aria-hidden="true" />
            </Button>
          </div>
          <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Wrench className="size-3.5" aria-hidden="true" />
            Milestone này chỉ thay đổi câu hỏi hiển thị; không thực hiện retrieval.
          </p>
        </form>
      </section>
    </div>
  );
}

function ContextRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={`max-w-[65%] text-right font-medium ${mono ? "font-mono" : ""}`}>{value}</span>
    </div>
  );
}
