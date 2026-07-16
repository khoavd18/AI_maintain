import type { ZodType } from "zod";

import { ApiConfigurationError, getApiBaseUrl } from "@/lib/api/config";
import { UserSafeApiError } from "@/lib/api/errors";

const defaultTimeoutMs = 10_000;

interface RequestOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
}

export async function getJson<T>(
  path: string,
  schema: ZodType<T>,
  options: RequestOptions = {},
): Promise<T> {
  let baseUrl: string;
  try {
    baseUrl = getApiBaseUrl();
  } catch (error) {
    if (error instanceof ApiConfigurationError) {
      throw new UserSafeApiError({ code: "configuration", message: error.message });
    }
    throw error;
  }

  const timeoutController = new AbortController();
  const timeout = setTimeout(
    () => timeoutController.abort("timeout"),
    options.timeoutMs ?? defaultTimeoutMs,
  );
  const signal = combineSignals(options.signal, timeoutController.signal);

  try {
    const response = await fetch(`${baseUrl}${path.startsWith("/") ? path : `/${path}`}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal,
    });

    if (!response.ok) {
      throw mapHttpError(response.status);
    }

    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      throw new UserSafeApiError({
        code: "invalid_response",
        message: "API trả về dữ liệu không đúng định dạng JSON.",
      });
    }

    const parsed = schema.safeParse(payload);
    if (!parsed.success) {
      throw new UserSafeApiError({
        code: "invalid_response",
        message: "Dữ liệu API không khớp hợp đồng đã xác định.",
      });
    }
    return parsed.data;
  } catch (error) {
    if (error instanceof UserSafeApiError) {
      throw error;
    }
    if (timeoutController.signal.aborted) {
      throw new UserSafeApiError({
        code: "timeout",
        message: "API phản hồi quá chậm. Vui lòng thử lại.",
        retryable: true,
      });
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new UserSafeApiError({
      code: "network",
      message: "Không thể kết nối tới FastAPI. Hãy kiểm tra API và cấu hình kết nối.",
      retryable: true,
    });
  } finally {
    clearTimeout(timeout);
  }
}

function mapHttpError(status: number): UserSafeApiError {
  if (status === 404) {
    return new UserSafeApiError({
      code: "not_found",
      status,
      message: "Không tìm thấy dữ liệu được yêu cầu.",
    });
  }
  if (status === 422) {
    return new UserSafeApiError({
      code: "validation",
      status,
      message: "Bộ lọc hoặc tham số gửi tới API không hợp lệ.",
    });
  }
  if (status === 503) {
    return new UserSafeApiError({
      code: "analytics_unavailable",
      status,
      message: "Dữ liệu analytics đang thiếu hoặc chưa đồng bộ. Hãy chạy lại batch analytics.",
      retryable: true,
    });
  }
  return new UserSafeApiError({
    code: "server",
    status,
    message: "API gặp lỗi khi xử lý yêu cầu. Vui lòng thử lại.",
    retryable: status >= 500,
  });
}

function combineSignals(primary: AbortSignal | undefined, timeout: AbortSignal): AbortSignal {
  if (!primary) {
    return timeout;
  }
  return AbortSignal.any([primary, timeout]);
}
