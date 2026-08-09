let accessToken: string | null = null;
let refreshHandler: (() => Promise<boolean>) | null = null;
let sessionExpiredHandler: (() => void) | null = null;
let refreshInFlight: Promise<boolean> | null = null;

export function getAccessToken() {
  return accessToken;
}

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function clearAccessToken() {
  accessToken = null;
}

export function registerAuthHandlers(handlers: {
  refresh: () => Promise<boolean>;
  expired: () => void;
}) {
  refreshHandler = handlers.refresh;
  sessionExpiredHandler = handlers.expired;
  return () => {
    if (refreshHandler === handlers.refresh) refreshHandler = null;
    if (sessionExpiredHandler === handlers.expired) sessionExpiredHandler = null;
  };
}

export async function refreshAccessSession() {
  if (!refreshHandler) return false;
  if (!refreshInFlight) {
    refreshInFlight = refreshHandler().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

export function notifySessionExpired() {
  clearAccessToken();
  sessionExpiredHandler?.();
}

export function getCsrfToken() {
  if (typeof document === "undefined") return null;
  const configuredName =
    process.env.NEXT_PUBLIC_CSRF_COOKIE_NAME?.trim() || "maintenance_csrf";
  const prefix = `${encodeURIComponent(configuredName)}=`;
  const cookie = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null;
}

export function resetAuthSessionForTests() {
  accessToken = null;
  refreshHandler = null;
  sessionExpiredHandler = null;
  refreshInFlight = null;
}
