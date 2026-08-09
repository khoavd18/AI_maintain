import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { InventoryStatusBadge, StockStateBadge } from "@/components/inventory-badges";
import { WorkOrderStatusBadge } from "@/components/status-badges";
import { TicketOperationsStatusBadge } from "@/components/ticket-operations-badges";
import {
  resolveStatusPresentation,
  ticketStatusCatalog,
} from "@/lib/status-terminology";

describe("centralized Vietnamese status terminology", () => {
  it("uses the canonical ticket label instead of a conflicting API display string", () => {
    render(
      <TicketOperationsStatusBadge
        status="in_progress"
        label="IN_PROGRESS"
      />,
    );

    const badge = screen.getByText("Đang xử lý").closest("span");
    expect(badge).toHaveAttribute(
      "title",
      "Người phụ trách đang xử lý sự cố.",
    );
    expect(screen.queryByText("IN_PROGRESS")).not.toBeInTheDocument();
  });

  it("makes the independent verification step clear for completed work", () => {
    const { rerender } = render(
      <WorkOrderStatusBadge status="completed" label="Đã hoàn thành" />,
    );

    expect(screen.getByText("Chờ xác nhận")).toBeInTheDocument();
    expect(screen.queryByText("Đã hoàn thành")).not.toBeInTheDocument();

    rerender(<WorkOrderStatusBadge status="verified" label="VERIFIED" />);
    expect(screen.getByText("Đã xác nhận")).toBeInTheDocument();
    expect(screen.queryByText("VERIFIED")).not.toBeInTheDocument();
  });

  it("uses concise stock and reservation wording", () => {
    render(
      <>
        <StockStateBadge state="at_reorder_point" label="Đến điểm đặt lại" />
        <InventoryStatusBadge status="active" label="Đang giữ" />
        <InventoryStatusBadge
          status="active"
          label="Đang hoạt động"
          context="lifecycle"
        />
      </>,
    );

    expect(screen.getByText("Sắp hết")).toBeInTheDocument();
    expect(screen.getByText("Đã đặt trước")).toBeInTheDocument();
    expect(screen.getByText("Đang hoạt động")).toBeInTheDocument();
  });

  it("never falls back to a raw enum value", () => {
    expect(
      resolveStatusPresentation(
        ticketStatusCatalog,
        "future_status",
        "FUTURE_STATUS",
      ),
    ).toMatchObject({ label: "Chưa xác định", tone: "neutral" });
  });
});
