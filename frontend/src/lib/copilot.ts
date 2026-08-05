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
  const separatelyPresentedSections = [
    "nguồn tài liệu",
    "nguồn tham khảo",
    "lưu ý an toàn",
    "cảnh báo an toàn",
    "source",
    "safety warning",
    "chi tiết kỹ thuật",
    "technical details",
  ];
  return !separatelyPresentedSections.some((section) => normalized.includes(section));
}

export function isCopilotSummarySection(title: string): boolean {
  return copilotSectionKind(title) === "summary";
}

export function copilotSectionTitle(title: string): string {
  const labels: Record<Exclude<CopilotSectionKind, "other">, string> = {
    summary: "Tóm tắt",
    causes: "Nguyên nhân có thể",
    checks: "Các bước nên kiểm tra",
    escalation: "Khi nào cần chuyển chuyên gia",
  };
  const kind = copilotSectionKind(title);
  return kind === "other" ? title : labels[kind];
}

export function orderCopilotAnswerSections(
  sections: CopilotAnswerSection[],
): CopilotAnswerSection[] {
  const priority: Record<CopilotSectionKind, number> = {
    summary: 0,
    causes: 1,
    checks: 2,
    other: 3,
    escalation: 4,
  };
  return sections
    .map((section, index) => ({ section, index }))
    .sort((left, right) => {
      const difference = priority[copilotSectionKind(left.section.title)]
        - priority[copilotSectionKind(right.section.title)];
      return difference || left.index - right.index;
    })
    .map(({ section }) => section);
}

export function copilotUserText(value: string): string {
  const replacements: Array<[RegExp, string]> = [
    [/\brisk context\b/gi, "tình trạng hiện tại"],
    [/\basset context\b/gi, "thông tin thiết bị"],
    [/\bretrieval\b/gi, "tra cứu tài liệu"],
    [/\bqdrant\b/gi, "kho tài liệu"],
    [/\bllm\b/gi, "hệ thống hỗ trợ"],
    [/\bprovider\b/gi, "dịch vụ hỗ trợ"],
    [/\bchunks?\b/gi, "đoạn tài liệu"],
    [/\bcollection\b/gi, "kho tài liệu"],
  ];
  return replacements.reduce(
    (result, [pattern, replacement]) => result.replace(pattern, replacement),
    value,
  );
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
    conversation: {
      title: "Trợ lý bảo trì đang sẵn sàng",
      description: "Bạn có thể hỏi về phạm vi hỗ trợ hoặc gửi một câu hỏi bảo trì cụ thể.",
      tone: "blue",
    },
    empty: {
      title: "Không đủ tài liệu để kết luận",
      description: "Kho tài liệu hiện chưa có nội dung phù hợp. Hãy mô tả rõ hiện tượng hoặc nhờ kỹ sư chuyên môn kiểm tra.",
      tone: "amber",
    },
    low_relevance: {
      title: "Không đủ tài liệu để kết luận",
      description: "Các tài liệu tìm được chưa đủ sát với tình trạng đã mô tả nên chưa thể đưa ra bước kỹ thuật cụ thể.",
      tone: "amber",
    },
    unsupported_asset_type: {
      title: "Chưa có hướng dẫn cho loại thiết bị này",
      description: "Kho tài liệu chưa có quy trình phù hợp. Cần kỹ sư chuyên môn kiểm tra trước khi thao tác.",
      tone: "amber",
    },
    unrelated: {
      title: "Câu hỏi nằm ngoài phạm vi bảo trì",
      description: "Hãy đặt câu hỏi về tình trạng thiết bị, kiểm tra hiện trường, SOP hoặc checklist bảo trì.",
      tone: "amber",
    },
    missing_asset_context: {
      title: "Cần chọn thiết bị",
      description: "Hãy chọn thiết bị để hệ thống dùng đúng tài liệu bảo trì và tránh hướng dẫn nhầm.",
      tone: "amber",
    },
    unavailable: {
      title: "Chưa thể tra cứu tài liệu",
      description: "Kho tài liệu đang tạm thời không truy cập được. Không thực hiện thao tác kỹ thuật chỉ dựa trên câu trả lời này; hãy thử lại sau.",
      tone: "red",
    },
    asset_context_mismatch: {
      title: "Cần xác nhận lại thiết bị",
      description: "Thiết bị nêu trong câu hỏi không khớp với thiết bị đang chọn. Hãy kiểm tra lại lựa chọn trước khi gửi câu hỏi.",
      tone: "amber",
    },
    prompt_injection: {
      title: "Không thể xử lý yêu cầu này",
      description: "Câu hỏi có nội dung yêu cầu bỏ qua quy tắc an toàn hoặc truy cập thông tin hệ thống. Hãy chỉ hỏi về công việc bảo trì.",
      tone: "amber",
    },
    unsafe_operation: {
      title: "Yêu cầu thao tác đã bị từ chối",
      description: "Trợ lý chỉ tra cứu tài liệu và không thực thi lệnh, điều khiển thiết bị hoặc thay đổi ticket/lệnh công việc.",
      tone: "amber",
    },
    unsafe_conversation: {
      title: "Không thể dùng ngữ cảnh trước",
      description: "Tóm tắt lượt trước có chỉ thị không an toàn nên đã bị loại. Hãy đặt lại câu hỏi bảo trì độc lập.",
      tone: "amber",
    },
    unsafe_context: {
      title: "Không thể dùng tài liệu này",
      description: "Một số nội dung có dấu hiệu không an toàn nên đã được loại khỏi câu trả lời. Không làm theo chỉ dẫn chưa được kiểm chứng.",
      tone: "amber",
    },
    insufficient_evidence: {
      title: "Không đủ tài liệu để kết luận",
      description: "Tài liệu hiện có chưa đủ để đưa ra hướng dẫn kỹ thuật cụ thể. Cần kỹ sư chuyên môn kiểm tra tại hiện trường.",
      tone: "amber",
    },
    conflicting_evidence: {
      title: "Tài liệu có chỉ dẫn mâu thuẫn",
      description: "Các nguồn truy xuất đưa ra chỉ dẫn đối nghịch. Cần người có thẩm quyền kiểm tra tài liệu hiện hành trước khi thao tác.",
      tone: "amber",
    },
  };
  return messages[status];
}

export function copilotProvenanceMessage(response: CopilotAskResponse) {
  if (response.response_mode === "llm_conversation") {
    return {
      title: "Hội thoại bằng LLM",
      description: "Đây là phản hồi xã giao ngắn; câu hỏi kỹ thuật vẫn cần tra cứu tài liệu bảo trì.",
      tone: "blue" as const,
    };
  }
  if (response.response_mode === "llm_grounded") {
    return {
      title: "Câu trả lời có nguồn tham khảo",
      description: "Nội dung được tổng hợp từ các tài liệu bảo trì hiển thị bên dưới và các trích dẫn đã được đối chiếu.",
      tone: "blue" as const,
    };
  }
  return {
    title: "Câu trả lời dự phòng",
    description: response.sources.length > 0
      ? "Nội dung chỉ gồm hướng dẫn có thể đối chiếu trực tiếp từ tài liệu. Hãy xác minh tại hiện trường trước khi thao tác."
      : "Chưa có đủ tài liệu để đưa ra hướng dẫn cụ thể. Hãy kiểm tra trực tiếp hoặc nhờ kỹ sư chuyên môn.",
    tone: "amber" as const,
  };
}

export function copilotEvidenceLabel(response: CopilotAskResponse) {
  const labels = {
    sufficient: "Bằng chứng tốt",
    limited: "Bằng chứng hạn chế",
    insufficient: "Không đủ bằng chứng",
    not_applicable: "Không cần tài liệu",
  };
  return labels[response.evidence_status];
}

export function copilotEvidenceMessage(response: CopilotAskResponse) {
  const messages = {
    sufficient: "Tài liệu đủ để định hướng bước kiểm tra; đây không phải kết luận tự động về hư hỏng.",
    limited: "Tài liệu chỉ hỗ trợ một phần. Cần kỹ sư chuyên môn kiểm tra và xác minh tại hiện trường.",
    insufficient: "Không đủ tài liệu để kết luận hoặc đưa ra bước kỹ thuật cụ thể. Cần kiểm tra trực tiếp.",
    not_applicable: "Câu hỏi xã giao không cần tra cứu SOP hoặc checklist.",
  };
  return messages[response.evidence_status];
}

export function copilotConfidenceLabel(response: CopilotAskResponse): string {
  const confidence = response.confidence
    ?? response.structured_answer?.confidence
    ?? (response.evidence_status === "insufficient" ? "insufficient_evidence" : "low");
  return {
    high: "Độ tin cậy bằng chứng: cao",
    medium: "Độ tin cậy bằng chứng: trung bình",
    low: "Độ tin cậy bằng chứng: thấp",
    insufficient_evidence: "Độ tin cậy: không đủ bằng chứng",
    not_applicable: "Phản hồi hội thoại",
  }[confidence];
}

export function ragStatusFromResponse(
  response: CopilotAskResponse,
): "available" | "unavailable" | null {
  if (response.retrieval_status === "unavailable") return "unavailable";
  if ([
    "success",
    "relevant",
    "empty",
    "low_relevance",
    "unsafe_context",
    "conflicting_evidence",
    "insufficient_evidence",
  ].includes(response.retrieval_status)) {
    return "available";
  }
  return null;
}

function stripInlineMarkdown(value: string): string {
  return value.replace(/\*\*([^*]+)\*\*/g, "$1").replace(/`([^`]+)`/g, "$1").trim();
}

type CopilotSectionKind = "summary" | "causes" | "checks" | "escalation" | "other";

function copilotSectionKind(title: string): CopilotSectionKind {
  const normalized = title.toLocaleLowerCase("vi");
  if (
    normalized.includes("tóm tắt")
    || normalized.includes("tình trạng thiết bị")
    || normalized.includes("summary")
  ) return "summary";
  if (normalized.includes("nguyên nhân") || normalized.includes("possible cause")) return "causes";
  if (
    normalized.includes("checklist")
    || normalized.includes("bước kiểm tra")
    || normalized.includes("nên kiểm tra")
    || normalized.includes("recommended check")
  ) return "checks";
  if (
    normalized.includes("giới hạn")
    || normalized.includes("chuyển chuyên gia")
    || normalized.includes("escalat")
  ) return "escalation";
  return "other";
}
