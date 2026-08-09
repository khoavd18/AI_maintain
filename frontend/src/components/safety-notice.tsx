import { ShieldAlert } from "lucide-react";

interface SafetyNoticeProps {
  compact?: boolean;
}

export function SafetyNotice({ compact = false }: SafetyNoticeProps) {
  return (
    <div role="note" className="flex gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-amber-950">
      <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div>
        <p className="text-sm font-semibold">Lưu ý an toàn</p>
        <p className="mt-0.5 text-xs leading-5">
          {compact
            ? "Kỹ thuật viên phải xác minh hiện trường trước khi thao tác."
            : "Nội dung chỉ hỗ trợ tra cứu. Kỹ thuật viên phải tuân thủ quy trình an toàn, xác minh hiện trường và chịu trách nhiệm cho quyết định cuối cùng."}
        </p>
      </div>
    </div>
  );
}
