import type {
  CopilotAskResponse,
  CopilotRetrievalStatus,
} from "@/lib/api/schemas";

export interface CopilotAnswerSection {
  title: string;
  paragraphs: string[];
  items: string[];
}

const genericSuggestions = [
  "Tôi nên bắt đầu kiểm tra thiết bị từ đâu?",
  "Có checklist an toàn nào phù hợp?",
  "SOP nào liên quan đến tình trạng hiện tại?",
];

const suggestionsByAssetType: Record<string, string[]> = {
  "Máy phát điện dự phòng": [
    "Vì sao thiết bị này đang có mức rủi ro hiện tại?",
    "Checklist kiểm tra ắc quy và hệ thống khởi động gồm những gì?",
    "Cần xác minh gì trước khi chạy thử có tải?",
  ],
  "Máy lạnh": [
    "Cần kiểm tra gì khi hiệu suất làm lạnh suy giảm?",
    "Checklist kiểm tra nhiệt độ và hệ thống làm lạnh gồm những gì?",
    "Lưu ý an toàn nào áp dụng trước khi kiểm tra điện?",
  ],
  "Máy bơm nước": [
    "Cần kiểm tra gì khi máy bơm rung hoặc áp suất bất thường?",
    "Checklist kiểm tra cơ khí và đường ống gồm những gì?",
    "Lưu ý an toàn nào áp dụng trước khi chạy thử máy bơm?",
  ],
};

export function getCopilotSuggestions(assetType?: string): string[] {
  return (assetType && suggestionsByAssetType[assetType]) || genericSuggestions;
}

export function parseCopilotAnswer(answer: string): CopilotAnswerSection[] {
  const sections: CopilotAnswerSection[] = [];
  let current: CopilotAnswerSection = {
    title: "Phản hồi",
    paragraphs: [],
    items: [],
  };

  const commit = () => {
    if (current.paragraphs.length || current.items.length) sections.push(current);
  };

  answer.split(/\r?\n/).forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) return;
    const heading = line.match(/^#{1,6}\s+(.+)$/);
    if (heading) {
      commit();
      current = { title: stripInlineMarkdown(heading[1]), paragraphs: [], items: [] };
      return;
    }
    const listItem = line.match(/^(?:[-*]|\d+[.)])\s+(.+)$/);
    if (listItem) {
      current.items.push(stripInlineMarkdown(listItem[1]));
      return;
    }
    current.paragraphs.push(stripInlineMarkdown(line));
  });
  commit();
  return sections;
}

export function shouldShowSection(title: string): boolean {
  const normalized = title.toLocaleLowerCase("vi");
  return !normalized.includes("nguồn tài liệu") && !normalized.includes("lưu ý an toàn");
}

export function retrievalStatusMessage(status: CopilotRetrievalStatus) {
  const messages: Record<CopilotRetrievalStatus, { title: string; description: string; tone: "amber" | "red" | "blue" }> = {
    success: {
      title: "Đã tìm thấy tài liệu liên quan",
      description: "Câu trả lời được tổng hợp từ các SOP/checklist hiển thị bên dưới.",
      tone: "blue",
    },
    relevant: {
      title: "Đã tìm thấy tài liệu liên quan",
      description: "Câu trả lời được tổng hợp từ các SOP/checklist hiển thị bên dưới.",
      tone: "blue",
    },
    empty: {
      title: "Kho tài liệu chưa có nội dung phù hợp",
      description: "Collection hiện không trả về chunk tài liệu. Hãy kiểm tra trạng thái index trước khi thử lại.",
      tone: "amber",
    },
    low_relevance: {
      title: "Chưa tìm thấy nguồn đủ liên quan",
      description: "Copilot không dùng kết quả có độ liên quan thấp để đưa ra hướng dẫn kỹ thuật cụ thể.",
      tone: "amber",
    },
    unsupported_asset_type: {
      title: "Loại thiết bị chưa được hỗ trợ",
      description: "Copilot hiện chỉ truy xuất tài liệu cho các loại thiết bị đã có SOP/checklist được kiểm soát.",
      tone: "amber",
    },
    unrelated: {
      title: "Câu hỏi nằm ngoài phạm vi bảo trì",
      description: "Hãy đặt câu hỏi về tình trạng thiết bị, kiểm tra hiện trường, SOP hoặc checklist bảo trì.",
      tone: "amber",
    },
    missing_asset_context: {
      title: "Cần chọn thiết bị",
      description: "Câu hỏi này cần asset context để áp dụng đúng loại thiết bị và tài liệu liên quan.",
      tone: "amber",
    },
    unavailable: {
      title: "RAG tạm thời chưa sẵn sàng",
      description: "Qdrant hoặc collection tài liệu có thể đang ngoại tuyến, thiếu hoặc trống. Analytics và API khác không bị đánh dấu ngoại tuyến.",
      tone: "red",
    },
  };
  return messages[status];
}

export function ragStatusFromResponse(
  response: CopilotAskResponse,
): "available" | "unavailable" | null {
  if (response.retrieval_status === "unavailable") return "unavailable";
  if (["success", "relevant", "empty", "low_relevance"].includes(response.retrieval_status)) {
    return "available";
  }
  return null;
}

function stripInlineMarkdown(value: string): string {
  return value.replace(/\*\*([^*]+)\*\*/g, "$1").replace(/`([^`]+)`/g, "$1").trim();
}
