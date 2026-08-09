export class ApiConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiConfigurationError";
  }
}

export function normalizeApiBaseUrl(value: string | undefined): string {
  const candidate = value?.trim();
  if (!candidate) {
    throw new ApiConfigurationError(
      "Chưa cấu hình địa chỉ API. Hãy đặt NEXT_PUBLIC_API_BASE_URL rồi khởi động lại frontend.",
    );
  }

  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new ApiConfigurationError(
      "NEXT_PUBLIC_API_BASE_URL không phải là một URL hợp lệ.",
    );
  }

  if (!(["http:", "https:"] as string[]).includes(parsed.protocol)) {
    throw new ApiConfigurationError(
      "NEXT_PUBLIC_API_BASE_URL phải sử dụng giao thức http hoặc https.",
    );
  }
  if (parsed.search || parsed.hash) {
    throw new ApiConfigurationError(
      "NEXT_PUBLIC_API_BASE_URL không được chứa query string hoặc fragment.",
    );
  }

  return `${parsed.origin}${parsed.pathname.replace(/\/+$/, "")}`;
}

export function getApiBaseUrl(): string {
  return normalizeApiBaseUrl(process.env.NEXT_PUBLIC_API_BASE_URL);
}
