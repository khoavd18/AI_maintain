import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CopilotWorkspace } from "@/components/copilot-workspace";
import {
  assetsFixture,
  copilotResponseFixture,
  copilotUnavailableFixture,
  ticketsFixture,
} from "@/test/fixtures";
import { mockApi, renderWithQuery } from "@/test/test-utils";

const replaceRoute = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/copilot",
  useRouter: () => ({ replace: replaceRoute }),
}));

describe("live Copilot workspace", () => {
  beforeEach(() => replaceRoute.mockReset());

  it("supports standalone mode and asset/ticket context from stable IDs", async () => {
    mockContextApi();
    const standalone = renderWithQuery(<CopilotWorkspace />);
    expect(await screen.findByText("Chọn thiết bị để thêm asset context vào câu hỏi.")).toBeInTheDocument();
    expect(screen.getByLabelText("Thiết bị")).toBeInTheDocument();
    standalone.unmount();

    mockContextApi();
    renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" initialTicketId="TCK-000041" />);
    expect(await screen.findByText("Máy phát điện dự phòng 002")).toBeInTheDocument();
    expect(screen.getByText("Thiết bị đã quá hạn bảo trì 159 ngày.")).toBeInTheDocument();
    expect(screen.getByText(ticketsFixture[0].issue_description)).toBeInTheDocument();
    expect(screen.getByText("Lỗi điện")).toBeInTheDocument();
  });

  it("submits the exact context, renders checklist, sources and safety, then clears the question", async () => {
    const fetchMock = mockContextApi(copilotResponseFixture);
    renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" initialTicketId="TCK-000041" />);
    const textarea = await screen.findByLabelText("Câu hỏi cho Copilot");

    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });

    expect(await screen.findByText("Đã tìm thấy tài liệu liên quan")).toBeInTheDocument();
    expect(screen.getByText("Checklist hoặc bước kiểm tra được tìm thấy")).toBeInTheDocument();
    expect(screen.getByText("SOP kiểm tra máy phát điện dự phòng")).toBeInTheDocument();
    expect(screen.getByText(/lockout\/tagout/)).toBeInTheDocument();
    expect(screen.queryByText("SOP-GEN-001-0")).not.toBeInTheDocument();
    expect(screen.queryByText("91%")).not.toBeInTheDocument();
    expect(textarea).toHaveValue("");

    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(postCall?.[1]?.body))).toEqual({
      question: "Vì sao GENERATOR_002 đang có mức rủi ro hiện tại và cần kiểm tra gì?",
      asset_id: "GENERATOR_002",
      top_k: 5,
      failure_category: "Lỗi điện",
    });
  });

  it("renders a confirmed unavailable fallback without treating it as a transport error", async () => {
    mockContextApi(copilotUnavailableFixture);
    renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" />);
    const textarea = await screen.findByLabelText("Câu hỏi cho Copilot");
    fireEvent.keyDown(textarea, { key: "Enter" });

    expect(await screen.findByText("RAG tạm thời chưa sẵn sàng")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thử lại câu hỏi này" })).toBeEnabled();
    expect(screen.queryByText("Chưa nhận được phản hồi từ Copilot")).not.toBeInTheDocument();
  });

  it("submits a standalone question and shows an unrelated safe fallback", async () => {
    mockContextApi({
      ...copilotUnavailableFixture,
      answer: "### Tóm tắt tình trạng thiết bị\nCâu hỏi không thuộc phạm vi bảo trì.",
      retrieval_status: "unrelated",
    });
    renderWithQuery(<CopilotWorkspace />);
    const textarea = await screen.findByLabelText("Câu hỏi cho Copilot");
    fireEvent.change(textarea, { target: { value: "Hôm nay thời tiết thế nào?" } });
    fireEvent.keyDown(textarea, { key: "Enter" });

    expect(await screen.findByText("Câu hỏi nằm ngoài phạm vi bảo trì")).toBeInTheDocument();
    expect(screen.queryByText("SOP kiểm tra máy phát điện dự phòng")).not.toBeInTheDocument();
  });

  it("shows unsupported equipment as a safe fallback rather than a crash", async () => {
    mockContextApi({
      ...copilotUnavailableFixture,
      answer: "### Tóm tắt tình trạng thiết bị\nLoại thiết bị này chưa được hỗ trợ.",
      retrieval_status: "unsupported_asset_type",
    });
    renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" />);
    const textarea = await screen.findByLabelText("Câu hỏi cho Copilot");
    fireEvent.change(textarea, { target: { value: "Checklist cho thang máy là gì?" } });
    fireEvent.keyDown(textarea, { key: "Enter" });

    expect(await screen.findByText("Loại thiết bị chưa được hỗ trợ")).toBeInTheDocument();
    expect(screen.queryByText("Chưa nhận được phản hồi từ Copilot")).not.toBeInTheDocument();
  });

  it("preserves the question on HTTP failure and validates an empty question", async () => {
    mockContextApi({ body: { detail: "Qdrant unavailable" }, status: 503 });
    renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" />);
    const textarea = await screen.findByLabelText("Câu hỏi cho Copilot");
    const originalQuestion = (textarea as HTMLTextAreaElement).value;
    fireEvent.keyDown(textarea, { key: "Enter" });

    expect(await screen.findByText("Chưa nhận được phản hồi từ Copilot")).toBeInTheDocument();
    expect(textarea).toHaveValue(originalQuestion);

    fireEvent.change(textarea, { target: { value: "   " } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(screen.getByText("Hãy nhập câu hỏi trước khi gửi.")).toBeInTheDocument();
  });

  it("prevents duplicate submissions while pending", async () => {
    let resolveCopilot!: (value: unknown) => void;
    const fetchMock = mockContextApi(() => new Promise((resolve) => { resolveCopilot = resolve; }));
    renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" />);
    const textarea = await screen.findByLabelText("Câu hỏi cho Copilot");

    fireEvent.keyDown(textarea, { key: "Enter" });
    fireEvent.keyDown(textarea, { key: "Enter" });
    await waitFor(() => {
      expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
    });
    resolveCopilot(copilotResponseFixture);
    expect(await screen.findByText("Đã tìm thấy tài liệu liên quan")).toBeInTheDocument();
  });

  it("renders backend text as text rather than executable HTML", async () => {
    mockContextApi({
      ...copilotResponseFixture,
      answer: "### Tóm tắt tình trạng thiết bị\n<img src=x onerror=alert(1)> Nội dung cần kiểm tra.",
    });
    const view = renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" />);
    const textarea = await screen.findByLabelText("Câu hỏi cho Copilot");
    fireEvent.keyDown(textarea, { key: "Enter" });

    expect(await screen.findByText(/<img src=x onerror=alert\(1\)>/)).toBeInTheDocument();
    expect(view.container.querySelector("img")).toBeNull();
  });
});

function mockContextApi(copilotResponse?: unknown) {
  const routes: Record<string, unknown> = {
    "/assets?limit=1000": assetsFixture,
    "/tickets?limit=1000": ticketsFixture,
  };
  if (copilotResponse !== undefined) routes["POST /copilot/ask"] = copilotResponse;
  return mockApi(routes);
}
