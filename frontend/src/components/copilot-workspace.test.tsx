import { act, fireEvent, screen, waitFor } from "@testing-library/react";
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
    expect(await screen.findByText(/Bạn vẫn có thể hỏi chung/)).toBeInTheDocument();
    expect(screen.getByLabelText("Thiết bị")).toBeInTheDocument();
    expect(screen.getByLabelText("Sự cố liên quan (không bắt buộc)")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Gửi câu hỏi" })).toBeDisabled();
    standalone.unmount();

    mockContextApi();
    renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" initialTicketId="TCK-000041" />);
    expect(await screen.findByRole("heading", { name: "Máy phát điện dự phòng 002", level: 3 })).toBeInTheDocument();
    expect(screen.getByText("Thiết bị đã quá hạn bảo trì 159 ngày.")).toBeInTheDocument();
    expect(screen.getByText(ticketsFixture[0].issue_description)).toBeInTheDocument();
    expect(screen.getByText("Lỗi điện")).toBeInTheDocument();
  });

  it("submits the exact context, renders checklist, sources and safety, then clears the question", async () => {
    const fetchMock = mockContextApi(copilotResponseFixture);
    renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" initialTicketId="TCK-000041" />);
    const textarea = await screen.findByLabelText("Câu hỏi bảo trì");

    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });

    expect(await screen.findByText("Câu trả lời có nguồn tham khảo")).toBeInTheDocument();
    expect(screen.getByText("Bằng chứng tốt")).toBeInTheDocument();
    expect(screen.getByText("Trích dẫn [S1]")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tóm tắt" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Cảnh báo an toàn" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Các bước nên kiểm tra" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Khi nào cần chuyển chuyên gia" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Nguồn tham khảo" })).toBeInTheDocument();
    expect(screen.getByText("SOP kiểm tra máy phát điện dự phòng")).toBeInTheDocument();
    expect(screen.getByText(/lockout\/tagout/)).toBeInTheDocument();
    expect(screen.getByText("Cô lập thiết bị trước khi kiểm tra.")).toBeInTheDocument();
    expect(screen.getByText(/tình trạng hiện tại/)).toBeInTheDocument();
    expect(screen.queryByText("SOP-GEN-001-0")).not.toBeInTheDocument();
    expect(screen.queryByText("SOP-GEN-001")).not.toBeInTheDocument();
    expect(screen.queryByText(/data\/documents\/sop_generator\.md/)).not.toBeInTheDocument();
    expect(screen.queryByText(/ollama/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/demo-model/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/risk context/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Qdrant|LLM|Provider|chunk|retrieval/i)).not.toBeInTheDocument();
    expect(screen.queryByText("91%")).not.toBeInTheDocument();
    expect(textarea).toHaveValue("");

    const summaryHeading = screen.getByRole("heading", { name: "Tóm tắt" });
    const safetyHeading = screen.getByRole("heading", { name: "Cảnh báo an toàn" });
    const checksHeading = screen.getByRole("heading", { name: "Các bước nên kiểm tra" });
    const sourcesHeading = screen.getByRole("heading", { name: "Nguồn tham khảo" });
    expect(summaryHeading.compareDocumentPosition(safetyHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(safetyHeading.compareDocumentPosition(checksHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(checksHeading.compareDocumentPosition(sourcesHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    fireEvent.click(screen.getByText("Phạm vi tài liệu"));
    expect(screen.getByText("15/01/2026")).toBeInTheDocument();

    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(postCall?.[1]?.body))).toEqual({
      question: "Vì sao thiết bị này đang có mức rủi ro hiện tại và cần kiểm tra gì?",
      asset_id: "GENERATOR_002",
      top_k: 5,
      failure_category: "Lỗi điện",
    });

    fireEvent.change(textarea, { target: { value: "Cảnh báo trước áp dụng thế nào?" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    await waitFor(() => {
      expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(2);
    });
    const followUpCall = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")[1];
    expect(JSON.parse(String(followUpCall?.[1]?.body))).toMatchObject({
      question: "Cảnh báo trước áp dụng thế nào?",
      conversation_context: {
        resolved_asset_type: "Máy phát điện dự phòng",
        resolved_failure_category: "Lỗi điện",
        previous_source_ids: ["S1"],
        previous_answer_summary: "Tóm tắt lượt trước do backend xác nhận.",
      },
    });
  });

  it("renders a confirmed unavailable fallback without treating it as a transport error", async () => {
    mockContextApi(copilotUnavailableFixture);
    renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" />);
    const textarea = await screen.findByLabelText("Câu hỏi bảo trì");
    fireEvent.keyDown(textarea, { key: "Enter" });

    expect(await screen.findByText("Chưa thể tra cứu tài liệu")).toBeInTheDocument();
    expect(screen.getByText("Câu trả lời dự phòng")).toBeInTheDocument();
    expect(screen.getByText("Không đủ bằng chứng")).toBeInTheDocument();
    expect(screen.queryByText(/RAG|Qdrant|collection|retrieval/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thử lại câu hỏi này" })).toBeEnabled();
    expect(screen.queryByText("Chưa nhận được phản hồi từ Copilot")).not.toBeInTheDocument();
  });

  it("renders an asset mismatch as a safe confirmation state", async () => {
    mockContextApi({
      ...copilotUnavailableFixture,
      answer: "### Tóm tắt tình trạng thiết bị\nLoại thiết bị trong câu hỏi không khớp thiết bị đã chọn.",
      retrieval_status: "asset_context_mismatch",
      fallback_reason: "asset_context_mismatch",
    });
    renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" />);
    const textarea = await screen.findByLabelText("Câu hỏi bảo trì");
    fireEvent.change(textarea, { target: { value: "Máy bơm nước bị rung cần kiểm tra gì?" } });
    fireEvent.keyDown(textarea, { key: "Enter" });

    expect(await screen.findByText("Cần xác nhận lại thiết bị")).toBeInTheDocument();
    expect(screen.getByText(/Hãy kiểm tra lại lựa chọn/)).toBeInTheDocument();
    expect(screen.getByText("Câu trả lời dự phòng")).toBeInTheDocument();
    expect(screen.queryByText("Trích dẫn [S1]")).not.toBeInTheDocument();
  });

  it("explains insufficient evidence without exposing retrieval internals", async () => {
    mockContextApi({
      ...copilotUnavailableFixture,
      answer: "### Tóm tắt tình trạng thiết bị\nBằng chứng truy xuất chưa đạt ngưỡng.",
      retrieval_status: "insufficient_evidence",
      fallback_reason: "insufficient_evidence",
    });
    renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" />);
    const textarea = await screen.findByLabelText("Câu hỏi bảo trì");
    fireEvent.keyDown(textarea, { key: "Enter" });

    expect(await screen.findByText("Không đủ tài liệu để kết luận")).toBeInTheDocument();
    expect(screen.getByText(/Cần kỹ sư chuyên môn kiểm tra tại hiện trường/)).toBeInTheDocument();
    expect(screen.getByText("Câu trả lời dự phòng")).toBeInTheDocument();
    expect(screen.getByText("Không đủ bằng chứng")).toBeInTheDocument();
    expect(screen.queryByText(/truy xuất|ngưỡng|retrieval|chunk/i)).not.toBeInTheDocument();
  });

  it("shows a deterministic fallback when LLM generation times out", async () => {
    mockContextApi({
      ...copilotResponseFixture,
      response_mode: "deterministic_fallback",
      fallback_reason: "llm_timeout",
      structured_answer: null,
      llm_provider: null,
      llm_model: null,
      evidence_status: "limited",
      citation_validation: null,
    });
    renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" />);
    const textarea = await screen.findByLabelText("Câu hỏi bảo trì");
    fireEvent.keyDown(textarea, { key: "Enter" });

    expect(await screen.findByText("Câu trả lời dự phòng")).toBeInTheDocument();
    expect(screen.getByText("Bằng chứng hạn chế")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thử lại câu hỏi này" })).toBeEnabled();
  });

  it("submits a standalone question and shows an unrelated safe fallback", async () => {
    mockContextApi({
      ...copilotUnavailableFixture,
      answer: "### Tóm tắt tình trạng thiết bị\nCâu hỏi không thuộc phạm vi bảo trì.",
      retrieval_status: "unrelated",
    });
    renderWithQuery(<CopilotWorkspace />);
    const textarea = await screen.findByLabelText("Câu hỏi bảo trì");
    fireEvent.change(textarea, { target: { value: "Hôm nay thời tiết thế nào?" } });
    fireEvent.keyDown(textarea, { key: "Enter" });

    expect(await screen.findByText("Câu hỏi nằm ngoài phạm vi bảo trì")).toBeInTheDocument();
    expect(screen.queryByText("SOP kiểm tra máy phát điện dự phòng")).not.toBeInTheDocument();
  });

  it("renders a bounded LLM conversation without maintenance evidence warnings", async () => {
    mockContextApi({
      ...copilotUnavailableFixture,
      answer: "Xin chào! Tôi là Trợ lý bảo trì AI.",
      retrieval_status: "conversation",
      relevance_status: "not_applicable",
      response_mode: "llm_conversation",
      fallback_reason: null,
      llm_provider: "ollama",
      llm_model: "qwen2.5-coder:7b",
      evidence_status: "not_applicable",
      confidence: "not_applicable",
      safety_notice: "",
    });
    renderWithQuery(<CopilotWorkspace />);
    const textarea = await screen.findByLabelText("Câu hỏi bảo trì");
    fireEvent.change(textarea, { target: { value: "xin chào" } });
    fireEvent.keyDown(textarea, { key: "Enter" });

    expect(await screen.findByText("Xin chào! Tôi là Trợ lý bảo trì AI.")).toBeInTheDocument();
    expect(screen.getByText("Hội thoại bằng LLM")).toBeInTheDocument();
    expect(screen.getByText("Không cần tài liệu")).toBeInTheDocument();
    expect(screen.queryByText("Cảnh báo an toàn")).not.toBeInTheDocument();
  });

  it("shows unsupported equipment as a safe fallback rather than a crash", async () => {
    mockContextApi({
      ...copilotUnavailableFixture,
      answer: "### Tóm tắt tình trạng thiết bị\nLoại thiết bị này chưa được hỗ trợ.",
      retrieval_status: "unsupported_asset_type",
    });
    renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" />);
    const textarea = await screen.findByLabelText("Câu hỏi bảo trì");
    fireEvent.change(textarea, { target: { value: "Checklist cho thang máy là gì?" } });
    fireEvent.keyDown(textarea, { key: "Enter" });

    expect(await screen.findByText("Chưa có hướng dẫn cho loại thiết bị này")).toBeInTheDocument();
    expect(screen.queryByText("Chưa nhận được phản hồi từ Copilot")).not.toBeInTheDocument();
  });

  it("preserves the question on HTTP failure and validates an empty question", async () => {
    mockContextApi({ body: { detail: "Qdrant unavailable" }, status: 503 });
    renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" />);
    const textarea = await screen.findByLabelText("Câu hỏi bảo trì");
    const originalQuestion = (textarea as HTMLTextAreaElement).value;
    fireEvent.keyDown(textarea, { key: "Enter" });

    expect(await screen.findByText("Chưa nhận được câu trả lời")).toBeInTheDocument();
    expect(screen.queryByText(/Qdrant unavailable/i)).not.toBeInTheDocument();
    expect(textarea).toHaveValue(originalQuestion);

    fireEvent.change(textarea, { target: { value: "   " } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(screen.getByText("Hãy nhập câu hỏi trước khi gửi.")).toBeInTheDocument();
  });

  it("prevents duplicate submissions while pending", async () => {
    let resolveCopilot!: (value: unknown) => void;
    const fetchMock = mockContextApi(() => new Promise((resolve) => { resolveCopilot = resolve; }));
    renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" />);
    const textarea = await screen.findByLabelText("Câu hỏi bảo trì");

    fireEvent.keyDown(textarea, { key: "Enter" });
    fireEvent.keyDown(textarea, { key: "Enter" });
    await waitFor(() => {
      expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
    });
    resolveCopilot(copilotResponseFixture);
    expect(await screen.findByText("Câu trả lời có nguồn tham khảo")).toBeInTheDocument();
  });

  it("does not restore cleared history or hidden context from a delayed response", async () => {
    const pending = deferred<unknown>();
    let postCount = 0;
    const fetchMock = mockContextApi(() => {
      postCount += 1;
      if (postCount === 1) return copilotResponseFixture;
      if (postCount === 2) return pending.promise;
      return responseWithSummary("Phản hồi mới hợp lệ");
    });
    renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" initialTicketId="TCK-000041" />);
    const textarea = await screen.findByLabelText("Câu hỏi bảo trì");

    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(await screen.findByText("Câu trả lời có nguồn tham khảo")).toBeInTheDocument();
    fireEvent.change(textarea, { target: { value: "Cảnh báo trước thì sao?" } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    await waitFor(() => expect(postRequests(fetchMock)).toHaveLength(2));
    fireEvent.click(screen.getByRole("button", { name: "Xóa cuộc trò chuyện" }));

    await act(async () => pending.resolve(responseWithSummary("PHẢN HỒI CŨ KHÔNG ĐƯỢC HIỆN")));
    fireEvent.change(textarea, { target: { value: "Máy phát không khởi động cần kiểm tra gì?" } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    await waitFor(() => expect(postRequests(fetchMock)).toHaveLength(3));

    expect(screen.queryByText("PHẢN HỒI CŨ KHÔNG ĐƯỢC HIỆN")).not.toBeInTheDocument();
    expect(await screen.findByText("Phản hồi mới hợp lệ")).toBeInTheDocument();
    expect(JSON.parse(String(postRequests(fetchMock)[2]?.[1]?.body))).not.toHaveProperty(
      "conversation_context",
    );
  });

  it("ignores a delayed success after the selected ticket changes", async () => {
    const pending = deferred<unknown>();
    let postCount = 0;
    const fetchMock = mockContextApi(() => {
      postCount += 1;
      return postCount === 1
        ? pending.promise
        : responseWithSummary("Phản hồi sau khi bỏ chọn ticket");
    });
    renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" initialTicketId="TCK-000041" />);
    const textarea = await screen.findByLabelText("Câu hỏi bảo trì");

    fireEvent.keyDown(textarea, { key: "Enter" });
    await waitFor(() => expect(postRequests(fetchMock)).toHaveLength(1));
    chooseSelectOption("Sự cố liên quan (không bắt buộc)", "Không chọn sự cố");
    await act(async () => pending.resolve(responseWithSummary("TICKET CŨ KHÔNG ĐƯỢC HIỆN")));
    fireEvent.change(textarea, { target: { value: "Máy phát không khởi động cần kiểm tra gì?" } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    await waitFor(() => expect(postRequests(fetchMock)).toHaveLength(2));

    const currentRequest = JSON.parse(String(postRequests(fetchMock)[1]?.[1]?.body));
    expect(currentRequest).not.toHaveProperty("failure_category");
    expect(currentRequest).not.toHaveProperty("conversation_context");
    expect(screen.queryByText("TICKET CŨ KHÔNG ĐƯỢC HIỆN")).not.toBeInTheDocument();
    expect(await screen.findByText("Phản hồi sau khi bỏ chọn ticket")).toBeInTheDocument();
  });

  it("ignores a delayed success after the selected asset changes", async () => {
    const pending = deferred<unknown>();
    let postCount = 0;
    const fetchMock = mockContextApi(() => {
      postCount += 1;
      return postCount === 1 ? pending.promise : responseWithSummary("Phản hồi cho máy lạnh");
    });
    renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" />);
    const textarea = await screen.findByLabelText("Câu hỏi bảo trì");

    fireEvent.keyDown(textarea, { key: "Enter" });
    await waitFor(() => expect(postRequests(fetchMock)).toHaveLength(1));
    chooseSelectOption("Thiết bị", "Máy lạnh 001 · Sân thượng phía Tây");
    await screen.findByRole("heading", { name: "Máy lạnh 001", level: 3 });
    await act(async () => pending.resolve(responseWithSummary("ASSET CŨ KHÔNG ĐƯỢC HIỆN")));
    fireEvent.change(textarea, { target: { value: "Máy lạnh chảy nước là sao?" } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    await waitFor(() => expect(postRequests(fetchMock)).toHaveLength(2));

    const currentRequest = JSON.parse(String(postRequests(fetchMock)[1]?.[1]?.body));
    expect(currentRequest).toMatchObject({ asset_id: "HVAC_001" });
    expect(currentRequest).not.toHaveProperty("conversation_context");
    expect(screen.queryByText("ASSET CŨ KHÔNG ĐƯỢC HIỆN")).not.toBeInTheDocument();
    expect(await screen.findByText("Phản hồi cho máy lạnh")).toBeInTheDocument();
  });

  it("ignores a delayed failure after a new asset context is active", async () => {
    const pending = deferred<unknown>();
    let postCount = 0;
    const fetchMock = mockContextApi(() => {
      postCount += 1;
      return postCount === 1 ? pending.promise : responseWithSummary("Ngữ cảnh mới thành công");
    });
    renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" />);
    const textarea = await screen.findByLabelText("Câu hỏi bảo trì");

    fireEvent.keyDown(textarea, { key: "Enter" });
    await waitFor(() => expect(postRequests(fetchMock)).toHaveLength(1));
    chooseSelectOption("Thiết bị", "Máy lạnh 001 · Sân thượng phía Tây");
    await act(async () => pending.reject(new Error("old request failed")));
    fireEvent.change(textarea, { target: { value: "Máy lạnh chảy nước là sao?" } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    await waitFor(() => expect(postRequests(fetchMock)).toHaveLength(2));

    expect(screen.queryByText("Chưa nhận được câu trả lời")).not.toBeInTheDocument();
    expect(await screen.findByText("Ngữ cảnh mới thành công")).toBeInTheDocument();
  });

  it("renders backend text as text rather than executable HTML", async () => {
    mockContextApi({
      ...copilotResponseFixture,
      answer: "### Tóm tắt tình trạng thiết bị\n<img src=x onerror=alert(1)> Nội dung cần kiểm tra.",
    });
    const view = renderWithQuery(<CopilotWorkspace initialAssetId="GENERATOR_002" />);
    const textarea = await screen.findByLabelText("Câu hỏi bảo trì");
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

function chooseSelectOption(label: string, option: string) {
  fireEvent.click(screen.getByRole("combobox", { name: label }));
  fireEvent.click(screen.getByRole("option", { name: option }));
}

function postRequests(fetchMock: ReturnType<typeof mockApi>) {
  return fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
}

function responseWithSummary(summary: string) {
  return {
    ...copilotResponseFixture,
    answer: `### Tóm tắt tình trạng thiết bị\n${summary}`,
    structured_answer: {
      ...copilotResponseFixture.structured_answer,
      summary,
    },
    conversation_state: {
      ...copilotResponseFixture.conversation_state,
      previous_answer_summary: summary,
    },
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}
