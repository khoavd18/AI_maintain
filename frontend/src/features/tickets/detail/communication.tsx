"use client";

import { type FormEvent, useState } from "react";
import { Loader2, MessageSquarePlus, Send } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useTicketCommentMutation } from "@/hooks/use-ticketing";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { TicketDetail } from "@/lib/api/ticketing-schemas";
import { permissions } from "@/lib/auth";
import { formatTimestamp } from "@/lib/formatters";

export function TicketCommunication({ ticket }: { ticket: TicketDetail }) {
  const auth = useAuth();
  const mutation = useTicketCommentMutation(ticket.ticket_id);
  const canInternal = auth.can(permissions.ticketCommentsInternal);
  const canRequester = auth.can(permissions.ticketCommentsRequester);
  const [visibility, setVisibility] = useState<"internal" | "requester">(
    canInternal ? "internal" : "requester",
  );
  const [body, setBody] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await mutation.mutateAsync({
        visibility,
        body,
        asset_attachment_ids: [],
        work_order_attachment_ids: [],
      });
      setBody("");
    } catch {
      // Safe error rendered below.
    }
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
      <section className="rounded-lg border bg-white">
        <header className="border-b p-4">
          <h2 className="text-sm font-semibold">Lịch sử trao đổi</h2>
        </header>
        {ticket.comments.length ? (
          <div className="divide-y">
            {[...ticket.comments].reverse().map((comment) => (
              <article key={comment.id} className="p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold">{comment.author_name}</span>
                    <span className="rounded bg-muted px-2 py-0.5 text-xs">
                      {comment.visibility === "internal" ? "Nội bộ" : "Hiển thị cho requester"}
                    </span>
                  </div>
                  <time className="text-xs text-muted-foreground">{formatTimestamp(comment.created_at)}</time>
                </div>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-6">{comment.body}</p>
              </article>
            ))}
          </div>
        ) : (
          <p className="p-6 text-sm text-muted-foreground">Chưa có comment cho ticket này.</p>
        )}
      </section>

      {(canInternal || canRequester) && !["closed", "cancelled"].includes(ticket.status) && (
        <form onSubmit={submit} className="h-fit rounded-lg border bg-white p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <MessageSquarePlus className="size-4" aria-hidden="true" />
            Thêm cập nhật
          </h2>
          {canInternal && canRequester && (
            <Select value={visibility} onValueChange={(value) => setVisibility(value as "internal" | "requester")}>
              <SelectTrigger aria-label="Phạm vi comment" className="mt-3 w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="internal">Ghi chú nội bộ</SelectItem>
                <SelectItem value="requester">Cập nhật cho requester</SelectItem>
              </SelectContent>
            </Select>
          )}
          <Textarea className="mt-3" aria-label="Nội dung comment" rows={6} value={body} onChange={(event) => setBody(event.target.value)} placeholder="Ghi nhận thông tin mới, không chỉnh sửa lịch sử cũ." />
          {mutation.isError && <p role="alert" className="mt-3 text-sm text-red-700">{getApiErrorMessage(mutation.error)}</p>}
          <Button type="submit" className="mt-3" disabled={mutation.isPending || !body.trim()}>
            {mutation.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Send aria-hidden="true" />}
            Gửi cập nhật
          </Button>
        </form>
      )}
    </div>
  );
}
