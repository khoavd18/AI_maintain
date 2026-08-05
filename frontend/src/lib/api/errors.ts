export type ApiErrorCode =
  | "configuration"
  | "unauthenticated"
  | "forbidden"
  | "not_found"
  | "validation"
  | "analytics_unavailable"
  | "rag_unavailable"
  | "network"
  | "timeout"
  | "invalid_response"
  | "business_rule"
  | "conflict"
  | "rate_limited"
  | "write_unavailable"
  | "server";

interface ApiErrorOptions {
  code: ApiErrorCode;
  message: string;
  status?: number;
  retryable?: boolean;
  ambiguousWrite?: boolean;
  fieldErrors?: Record<string, string>;
}

export class UserSafeApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status?: number;
  readonly retryable: boolean;
  readonly ambiguousWrite: boolean;
  readonly fieldErrors: Record<string, string>;

  constructor({
    code,
    message,
    status,
    retryable = false,
    ambiguousWrite = false,
    fieldErrors = {},
  }: ApiErrorOptions) {
    super(message);
    this.name = "UserSafeApiError";
    this.code = code;
    this.status = status;
    this.retryable = retryable;
    this.ambiguousWrite = ambiguousWrite;
    this.fieldErrors = fieldErrors;
  }
}

export function getApiErrorMessage(error: unknown): string {
  if (error instanceof UserSafeApiError) {
    return error.message;
  }
  return "Không thể tải dữ liệu lúc này. Vui lòng thử lại.";
}
