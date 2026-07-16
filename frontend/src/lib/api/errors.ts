export type ApiErrorCode =
  | "configuration"
  | "not_found"
  | "validation"
  | "analytics_unavailable"
  | "network"
  | "timeout"
  | "invalid_response"
  | "server";

interface ApiErrorOptions {
  code: ApiErrorCode;
  message: string;
  status?: number;
  retryable?: boolean;
}

export class UserSafeApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status?: number;
  readonly retryable: boolean;

  constructor({ code, message, status, retryable = false }: ApiErrorOptions) {
    super(message);
    this.name = "UserSafeApiError";
    this.code = code;
    this.status = status;
    this.retryable = retryable;
  }
}

export function getApiErrorMessage(error: unknown): string {
  if (error instanceof UserSafeApiError) {
    return error.message;
  }
  return "Không thể tải dữ liệu lúc này. Vui lòng thử lại.";
}
