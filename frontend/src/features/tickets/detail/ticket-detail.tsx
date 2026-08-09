"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import { useAssetDetailsQuery } from "@/hooks/use-api-queries";
import { useTicketDetailQuery, useTicketingOptionsQuery } from "@/hooks/use-ticketing";
import { adaptAssetDetails } from "@/lib/adapters";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { TicketPriority } from "@/lib/types";
import { TicketWorkOrdersPanel } from "@/components/ticket-work-orders-panel";

import { TicketActionPanel } from "./actions/ticket-action-panel";
import { TicketCommunication } from "./communication";
import { TicketFacts, TicketSummary } from "./components/facts";
import { TicketTimeline } from "./timeline";

export function TicketOperationsDetail({ ticketId }: { ticketId: string }) {
  const ticket = useTicketDetailQuery(ticketId);
  const options = useTicketingOptionsQuery();
  const assetDetails = useAssetDetailsQuery(ticket.data?.asset_id ?? "", 10);

  if (ticket.isPending || options.isPending) return <LoadingSkeleton />;
  if (ticket.isError || options.isError) {
    return (
      <ErrorState
        title="Chưa tải được ticket"
        description={getApiErrorMessage(ticket.error ?? options.error)}
        action={
          <RetryButton
            onClick={() => {
              void ticket.refetch();
              void options.refetch();
            }}
          />
        }
      />
    );
  }

  const asset = assetDetails.data ? adaptAssetDetails(assetDetails.data) : null;
  return (
    <div className="space-y-5">
      <TicketSummary ticket={ticket.data} />

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Tổng quan</TabsTrigger>
          <TabsTrigger value="communication">
            Trao đổi ({ticket.data.comments.length})
          </TabsTrigger>
          <TabsTrigger value="timeline">Lịch sử</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4 space-y-5">
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
            <div className="space-y-5">
              <TicketFacts ticket={ticket.data} />
              <TicketWorkOrdersPanel
                ticket={{
                  id: ticket.data.ticket_id,
                  assetId: ticket.data.asset_id,
                  summary: ticket.data.issue_description,
                  description: ticket.data.issue_description,
                  priority: ticket.data.priority_display as TicketPriority,
                  priorityCode: ticket.data.priority,
                  status: ticket.data.status,
                }}
              />
            </div>
            <TicketActionPanel
              key={`${ticket.data.ticket_id}-${ticket.data.version}`}
              ticket={ticket.data}
              options={options.data}
              onRefresh={() => void ticket.refetch()}
              asset={asset}
            />
          </div>
        </TabsContent>

        <TabsContent value="communication" className="mt-4">
          <TicketCommunication
            key={`${ticket.data.ticket_id}-${ticket.data.comments.length}`}
            ticket={ticket.data}
          />
        </TabsContent>

        <TabsContent value="timeline" className="mt-4">
          <TicketTimeline ticket={ticket.data} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
