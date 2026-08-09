"use client";

import { ErrorState, RetryButton } from "@/components/ui-states";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <ErrorState
      title="Không thể hiển thị trang"
      description="Đã xảy ra lỗi khi dựng giao diện. Hãy thử tải lại nội dung."
      action={<RetryButton onClick={reset} />}
    />
  );
}
