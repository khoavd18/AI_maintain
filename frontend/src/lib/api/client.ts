import type { ZodType } from "zod";

import { ApiConfigurationError, getApiBaseUrl } from "@/lib/api/config";
import {
  getAccessToken,
  getCsrfToken,
  notifySessionExpired,
  refreshAccessSession,
} from "@/lib/api/auth-session";
import { UserSafeApiError } from "@/lib/api/errors";
import {
  backendErrorResponseSchema,
  backendValidationIssueSchema,
} from "@/lib/api/schemas";

const defaultTimeoutMs = 10_000;

export interface RequestOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
  idempotencyKey?: string;
  operation?: "write" | "copilot" | "auth";
  skipAuth?: boolean;
  skipRefresh?: boolean;
  csrf?: boolean;
}

type WriteMethod = "POST" | "PATCH" | "DELETE";

export async function getJson<T>(
  path: string,
  schema: ZodType<T>,
  options: RequestOptions = {},
): Promise<T> {
  return requestJson(path, "GET", schema, undefined, options);
}

export async function postJson<TRequest, TResponse>(
  path: string,
  body: TRequest,
  requestSchema: ZodType<TRequest>,
  responseSchema: ZodType<TResponse>,
  options: RequestOptions = {},
): Promise<TResponse> {
  return writeJson(path, "POST", body, requestSchema, responseSchema, options);
}

export async function patchJson<TRequest, TResponse>(
  path: string,
  body: TRequest,
  requestSchema: ZodType<TRequest>,
  responseSchema: ZodType<TResponse>,
  options: RequestOptions = {},
): Promise<TResponse> {
  return writeJson(path, "PATCH", body, requestSchema, responseSchema, options);
}

export async function deleteJson<T>(
  path: string,
  responseSchema: ZodType<T>,
  options: RequestOptions = {},
): Promise<T> {
  return requestJson(path, "DELETE", responseSchema, undefined, options);
}

export async function postForm<T>(
  path: string,
  body: FormData,
  responseSchema: ZodType<T>,
  options: RequestOptions = {},
): Promise<T> {
  return requestJson(path, "POST", responseSchema, body, options);
}

export async function getBinary(
  path: string,
  options: RequestOptions = {},
): Promise<Blob> {
  const response = await request(path, "GET", undefined, options, false);
  return response.blob();
}

export async function postNoContent(
  path: string,
  options: RequestOptions = {},
): Promise<void> {
  await request(path, "POST", undefined, { ...options, operation: "auth" }, true);
}

async function writeJson<TRequest, TResponse>(
  path: string,
  method: WriteMethod,
  body: TRequest,
  requestSchema: ZodType<TRequest>,
  responseSchema: ZodType<TResponse>,
  options: RequestOptions,
): Promise<TResponse> {
  const parsedRequest = requestSchema.safeParse(body);
  if (!parsedRequest.success) {
    throw new UserSafeApiError({
      code: "validation",
      message: "Biểu mẫu chưa hợp lệ. Hãy kiểm tra các trường được đánh dấu.",
      fieldErrors: zodFieldErrors(parsedRequest.error.issues),
    });
  }
  return requestJson(path, method, responseSchema, parsedRequest.data, options);
}

async function requestJson<T>(
  path: string,
  method: "GET" | WriteMethod,
  schema: ZodType<T>,
  body: unknown,
  options: RequestOptions,
): Promise<T> {
  const response = await request(path, method, body, options, false);
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    const isWrite =
      method !== "GET" &&
      options.operation !== "auth" &&
      options.operation !== "copilot";
    throw new UserSafeApiError({
      code: "invalid_response",
      message: isWrite
        ? "Yêu cầu có thể đã được ghi nhưng phản hồi API không hợp lệ. Hãy kiểm tra danh sách trước khi gửi lại."
        : "API trả về dữ liệu không đúng định dạng JSON.",
      ambiguousWrite: isWrite,
    });
  }

  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    const isWrite =
      method !== "GET" &&
      options.operation !== "auth" &&
      options.operation !== "copilot";
    throw new UserSafeApiError({
      code: "invalid_response",
      message: isWrite
        ? "Yêu cầu có thể đã được ghi nhưng phản hồi không khớp hợp đồng. Hãy kiểm tra dữ liệu trước khi gửi lại."
        : "Dữ liệu API không khớp hợp đồng đã xác định.",
      ambiguousWrite: isWrite,
    });
  }
  return parsed.data;
}

async function request(
  path: string,
  method: "GET" | WriteMethod,
  body: unknown,
  options: RequestOptions,
  expectNoContent: boolean,
): Promise<Response> {
  const hasBody = method !== "GET" && body !== undefined;
  const isFormBody = typeof FormData !== "undefined" && body instanceof FormData;
  const operation = method === "GET" ? "read" : (options.operation ?? "write");
  const isWrite = operation === "write";
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
    const url = `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
    const execute = () =>
      fetch(url, {
        method,
        headers: requestHeaders({
          hasBody,
          jsonBody: hasBody && !isFormBody,
          skipAuth: options.skipAuth,
          csrf: options.csrf,
          idempotencyKey: options.idempotencyKey,
        }),
        body: hasBody
          ? (isFormBody ? (body as FormData) : JSON.stringify(body))
          : undefined,
        credentials: "include",
        signal,
      });
    let response = await execute();

    if (response.status === 401 && !options.skipRefresh && !path.startsWith("/auth/")) {
      const refreshed = await refreshAccessSession();
      if (refreshed) response = await execute();
      if (response.status === 401) notifySessionExpired();
    }

    if (!response.ok) {
      const errorPayload = await readErrorPayload(response);
      throw mapHttpError(response.status, errorPayload, operation);
    }

    if (expectNoContent && response.status !== 204) {
      throw new UserSafeApiError({
        code: "invalid_response",
        message: "API không xác nhận hoàn tất yêu cầu phiên đăng nhập.",
      });
    }
    return response;
  } catch (error) {
    if (error instanceof UserSafeApiError) {
      throw error;
    }
    if (timeoutController.signal.aborted) {
      throw new UserSafeApiError({
        code: "timeout",
        message: isWrite
          ? "Không xác định được yêu cầu đã được ghi hay chưa do API hết thời gian phản hồi. Hãy kiểm tra dữ liệu trước khi gửi lại."
          : "API phản hồi quá chậm. Vui lòng thử lại.",
        retryable: !isWrite,
        ambiguousWrite: isWrite,
      });
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new UserSafeApiError({
      code: "network",
      message: isWrite
        ? "Mất kết nối trong khi gửi yêu cầu. Hãy kiểm tra ticket hoặc log trước khi gửi lại để tránh trùng dữ liệu."
        : "Không thể kết nối tới FastAPI. Hãy kiểm tra API và cấu hình kết nối.",
      retryable: !isWrite,
      ambiguousWrite: isWrite,
    });
  } finally {
    clearTimeout(timeout);
  }
}

function mapHttpError(
  status: number,
  payload: ReturnType<typeof backendErrorResponseSchema.safeParse>,
  operation: "read" | "write" | "copilot" | "auth",
): UserSafeApiError {
  const isWrite = operation === "write";
  const parsedPayload = payload.success ? payload.data : null;
  const businessDetail = safeBusinessDetail(parsedPayload?.detail);
  const fieldErrors = validationFieldErrors(parsedPayload?.detail);

  if (status === 401) {
    return new UserSafeApiError({
      code: "unauthenticated",
      status,
      message: businessDetail ?? "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
    });
  }
  if (status === 403) {
    return new UserSafeApiError({
      code: "forbidden",
      status,
      message: businessDetail ?? "Bạn không có quyền thực hiện thao tác này.",
    });
  }

  if (status === 400) {
    return new UserSafeApiError({
      code: "business_rule",
      status,
      message: businessDetail ?? "Yêu cầu không đáp ứng quy tắc nghiệp vụ hiện tại.",
    });
  }
  if (status === 404) {
    return new UserSafeApiError({
      code: "not_found",
      status,
      message: businessDetail ?? "Không tìm thấy thiết bị hoặc ticket được yêu cầu.",
    });
  }
  if (status === 410) {
    return new UserSafeApiError({
      code: "not_found",
      status,
      message: businessDetail ?? "Asset từ QR không còn ở trạng thái hoạt động.",
    });
  }
  if (status === 409) {
    return new UserSafeApiError({
      code: "conflict",
      status,
      message: businessDetail ?? "Dữ liệu đã tồn tại hoặc trạng thái vừa thay đổi.",
    });
  }
  if (status === 429) {
    return new UserSafeApiError({
      code: "rate_limited",
      status,
      message: businessDetail ?? "Bạn đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau.",
      retryable: true,
    });
  }
  if (status === 422) {
    return new UserSafeApiError({
      code: "validation",
      status,
      message: "API từ chối một hoặc nhiều trường trong biểu mẫu.",
      fieldErrors,
    });
  }
  if (status === 503) {
    if (operation === "copilot") {
      return new UserSafeApiError({
        code: "rag_unavailable",
        status,
        message: "Kho tài liệu RAG tạm thời chưa sẵn sàng. Dữ liệu analytics và các chức năng khác vẫn có thể sử dụng.",
        retryable: true,
      });
    }
    return new UserSafeApiError({
      code: isWrite ? "write_unavailable" : "analytics_unavailable",
      status,
      message: isWrite
        ? "Kho dữ liệu giao dịch tạm thời không ghi được. Yêu cầu đã bị từ chối và có thể thử lại sau khi kiểm tra dịch vụ."
        : "Dữ liệu analytics đang thiếu hoặc chưa đồng bộ. Hãy chạy lại batch analytics.",
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

async function readErrorPayload(response: Response) {
  try {
    return backendErrorResponseSchema.safeParse(await response.json());
  } catch {
    return backendErrorResponseSchema.safeParse(null);
  }
}

function safeBusinessDetail(detail: unknown): string | null {
  if (typeof detail !== "string" || !detail.trim() || detail.length > 500) return null;
  if (/[A-Za-z]:\\|[/\\][^\s]*\.csv\b/i.test(detail)) return null;
  return detail.trim();
}

function validationFieldErrors(detail: unknown): Record<string, string> {
  if (!Array.isArray(detail)) return {};
  const errors: Record<string, string> = {};
  detail.forEach((issue) => {
    const parsed = backendValidationIssueSchema.safeParse(issue);
    if (parsed.success) {
      errors[String(parsed.data.loc.at(-1) ?? "form")] = parsed.data.msg;
    }
  });
  return errors;
}

function zodFieldErrors(issues: { path: PropertyKey[]; message: string }[]) {
  return Object.fromEntries(
    issues.map((issue) => [String(issue.path[0] ?? "form"), issue.message]),
  );
}

function combineSignals(primary: AbortSignal | undefined, timeout: AbortSignal): AbortSignal {
  if (!primary) return timeout;
  return AbortSignal.any([primary, timeout]);
}

function requestHeaders(options: {
  hasBody: boolean;
  jsonBody: boolean;
  skipAuth?: boolean;
  csrf?: boolean;
  idempotencyKey?: string;
}) {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.jsonBody) headers["Content-Type"] = "application/json";
  if (options.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  }
  const token = options.skipAuth ? null : getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.csrf) {
    const csrfToken = getCsrfToken();
    if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  }
  return headers;
}
