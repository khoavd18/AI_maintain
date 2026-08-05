import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MaintenanceResultSheet } from "@/components/maintenance-result-sheet";
import { TicketCreateSheet } from "@/components/ticket-create-sheet";
import { TicketDetailSheet } from "@/components/ticket-detail-sheet";
import { adaptAsset, adaptMaintenanceLog, adaptTicket } from "@/lib/adapters";
import { addDays, todayInVietnam } from "@/lib/workflow";
import { assetsFixture, logFixture, ticketsFixture } from "@/test/fixtures";
import { mockApi, renderWithQuery } from "@/test/test-utils";

const asset = adaptAsset(assetsFixture[0]);
const newTicket = adaptTicket(ticketsFixture[0]);
const inProgressRecord = { ...ticketsFixture[0], status: "Đang xử lý" as const };
const inProgressTicket = adaptTicket(inProgressRecord);

describe("live maintenance workflow forms", () => {
  it("prefills asset context, validates locally, prevents double submit, and confirms the ticket ID", async () => {
    let release!: () => void;
    const created = { ...ticketsFixture[0], ticket_id: "TCK-000043", created_at: "2026-07-16T07:00:00+00:00" };
    const fetchMock = mockApi({
      "POST /tickets": async () => {
        await new Promise<void>((resolve) => { release = resolve; });
        return { body: created, status: 201 };
      },
    });
    const onCreated = vi.fn();
    renderWithQuery(<TicketCreateSheet asset={asset} latestAnomaly="Điện áp ắc quy thấp." open onOpenChange={vi.fn()} onCreated={onCreated} />);

    expect(screen.getByLabelText("Asset ID")).toHaveValue("GENERATOR_002");
    expect((screen.getByLabelText("Mô tả vấn đề") as HTMLTextAreaElement).value).toContain("Risk 63.89");
    expect(screen.getByText("Anomaly: Điện áp ắc quy thấp.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Tạo ticket" }));
    expect(await screen.findByText("Mã kỹ thuật viên là bắt buộc.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Mã kỹ thuật viên"), { target: { value: "TECH_003" } });
    const submit = screen.getByRole("button", { name: "Tạo ticket" });
    fireEvent.click(submit);
    fireEvent.click(submit);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: "Đang gửi..." })).toBeDisabled();
    release();

    expect(await screen.findByText("Đã tạo ticket TCK-000043")).toBeInTheDocument();
    expect(onCreated).toHaveBeenCalledWith("TCK-000043");
    expect(screen.getByRole("link", { name: "Mở ticket vừa tạo" })).toHaveAttribute("href", "/tickets?ticket=TCK-000043");
  });

  it("shows an ambiguous offline write without encouraging blind resubmission", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("offline"); }));
    renderWithQuery(<TicketCreateSheet asset={asset} open onOpenChange={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Mã kỹ thuật viên"), { target: { value: "TECH_003" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo ticket" }));

    expect(await screen.findByText("Chưa xác định trạng thái ghi")).toBeInTheDocument();
    expect(screen.getByText(/kiểm tra ticket hoặc log trước khi gửi lại/i)).toBeInTheDocument();
  });

  it("updates assignment and exposes only the valid transition for a new ticket", async () => {
    const onWrite = vi.fn();
    const fetchMock = mockApi({
      "GET /tickets/TCK-000041/work-orders": [],
      "PATCH /tickets/TCK-000041": async (
        _input: string | URL | Request,
        init?: RequestInit,
      ) => {
        const request = JSON.parse(String(init?.body));
        return { body: { ...ticketsFixture[0], ...request }, status: 200 };
      },
    });
    renderWithQuery(<TicketDetailSheet ticket={newTicket} asset={asset} linkedLogs={[]} onClose={vi.fn()} onRefreshState={vi.fn()} onWriteConfirmed={onWrite} />);

    expect(screen.getByRole("button", { name: /Chuyển sang Đang xử lý/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ghi kết quả bảo trì" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Mã kỹ thuật viên"), { target: { value: "TECH_009" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu phân công" }));
    await waitFor(() => expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(1));
    expect(onWrite).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /Chuyển sang Đang xử lý/ }));
    await waitFor(() => expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(2));
    await waitFor(() => expect(screen.queryByRole("button", { name: /Chuyển sang Đang xử lý/ })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Ghi kết quả bảo trì" })).toBeInTheDocument();
  });

  it("derives IDs, chronology and follow-up, then shows the next-batch notice", async () => {
    const onSaved = vi.fn();
    const fetchMock = mockApi({
      "POST /maintenance/logs": async (
        _input: string | URL | Request,
        init?: RequestInit,
      ) => {
        const request = JSON.parse(String(init?.body));
        return {
          body: {
            log_id: "LOG-000087",
            ...request,
            maintenance_type: "Bảo trì sửa chữa",
            technician_id: inProgressTicket.technician,
          },
          status: 201,
        };
      },
    });
    renderWithQuery(<MaintenanceResultSheet ticket={inProgressTicket} asset={asset} open onOpenChange={vi.fn()} onSaved={onSaved} />);

    expect(screen.getByText(/ID được khóa theo ticket đang chọn/)).toBeInTheDocument();
    expect(screen.getByLabelText("Ngày bảo trì kế tiếp")).toHaveValue(addDays(todayInVietnam(), 120));
    fireEvent.change(screen.getByLabelText("Kết quả kiểm tra"), { target: { value: "Ắc quy cần vệ sinh đầu cực." } });
    fireEvent.change(screen.getByLabelText("Hành động đã thực hiện"), { target: { value: "Vệ sinh đầu cực và đo lại điện áp." } });
    fireEvent.change(screen.getByLabelText("Ghi chú kỹ thuật viên"), { target: { value: "Điện áp ổn định sau kiểm tra." } });
    fireEvent.click(screen.getByLabelText("Kết quả bảo trì"));
    fireEvent.click(await screen.findByRole("option", { name: "Cần theo dõi" }));
    expect(screen.getByText("Theo dõi tiếp: Có")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Ghi kết quả" }));

    expect(await screen.findByText("Đã tạo maintenance log LOG-000087")).toBeInTheDocument();
    expect(screen.getByText(/Risk Score và KPI sẽ được cập nhật trong lần chạy analytics tiếp theo/)).toBeInTheDocument();
    expect(onSaved).toHaveBeenCalledWith("LOG-000087");
    const request = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(request).toMatchObject({ ticket_id: "TCK-000041", asset_id: "GENERATOR_002", maintenance_result: "Cần theo dõi", follow_up_required: true });
  });

  it("refreshes log state, confirms resolution, and displays backend rejection safely", async () => {
    const linkedLog = { ...adaptMaintenanceLog({ ...logFixture, ticket_id: inProgressTicket.id }), followUp: true };
    const resolvedRecord = { ...inProgressRecord, status: "Đã xử lý" as const, resolved_at: "2026-07-16T08:00:00+00:00" };
    const refreshState = vi.fn(async () => ({ ticket: inProgressTicket, linkedLogCount: 1 }));
    const firstFetch = mockApi({ "GET /tickets/TCK-000041/work-orders": [], "PATCH /tickets/TCK-000041": { body: resolvedRecord, status: 200 } });
    const first = renderWithQuery(<TicketDetailSheet ticket={inProgressTicket} asset={asset} linkedLogs={[linkedLog]} onClose={vi.fn()} onRefreshState={refreshState} />);

    expect(screen.getByText(/vẫn yêu cầu theo dõi/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Resolve ticket" }));
    expect(screen.getByRole("alertdialog", { name: "Xác nhận resolve ticket" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Kiểm tra và resolve" }));
    expect(await screen.findByText("Ticket đã xử lý")).toBeInTheDocument();
    expect(screen.getByText(/maintenance result gần nhất vẫn yêu cầu theo dõi/)).toBeInTheDocument();
    expect(refreshState).toHaveBeenCalledOnce();
    expect(firstFetch.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(1);
    first.unmount();

    mockApi({ "GET /tickets/TCK-000041/work-orders": [], "PATCH /tickets/TCK-000041": { body: { detail: "Cần maintenance log hợp lệ trước khi resolve ticket." }, status: 400 } });
    renderWithQuery(<TicketDetailSheet ticket={inProgressTicket} asset={asset} linkedLogs={[linkedLog]} onClose={vi.fn()} onRefreshState={refreshState} />);
    fireEvent.click(screen.getByRole("button", { name: "Resolve ticket" }));
    fireEvent.click(screen.getByRole("button", { name: "Kiểm tra và resolve" }));
    expect(await screen.findByText("Cần maintenance log hợp lệ trước khi resolve ticket.")).toBeInTheDocument();
  });

  it("keeps resolved tickets read-only", () => {
    const resolved = adaptTicket(ticketsFixture[1]);
    renderWithQuery(<TicketDetailSheet ticket={resolved} asset={adaptAsset(assetsFixture[1])} linkedLogs={[]} onClose={vi.fn()} onRefreshState={vi.fn()} />);
    expect(screen.getByText("Trạng thái vận hành chỉ đọc; API không hỗ trợ mở lại ticket.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Lưu phân công" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Resolve ticket" })).not.toBeInTheDocument();
  });
});
