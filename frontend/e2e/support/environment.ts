import { createHash, timingSafeEqual } from "node:crypto";

export type DemoRole = "manager" | "technician" | "storekeeper";

const defaultUsernames: Record<DemoRole, string> = {
  manager: "manager.demo",
  technician: "technician.demo",
  storekeeper: "storekeeper.demo",
};

function requiredEnvironmentValue(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required for the live Playwright suite.`);
  return value;
}

function requiredSecret(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required for the live Playwright suite.`);
  return value;
}

function loopbackUrl(name: string, fallback: string): string {
  const value = process.env[name]?.trim() || fallback;
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${name} must be a valid loopback HTTP(S) URL.`);
  }
  if (
    !["http:", "https:"].includes(parsed.protocol) ||
    !["127.0.0.1", "localhost", "[::1]"].includes(parsed.hostname) ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash ||
    !["", "/"].includes(parsed.pathname)
  ) {
    throw new Error(`${name} must be an explicit credential-free loopback origin.`);
  }
  return parsed.origin;
}

function expectedDatabaseFingerprint(): string {
  const value = requiredEnvironmentValue("PLAYWRIGHT_TEST_DATABASE_URL");
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error("PLAYWRIGHT_TEST_DATABASE_URL must be a valid PostgreSQL URL.");
  }
  const databaseName = decodeURIComponent(parsed.pathname.replace(/^\//, ""));
  if (
    parsed.protocol !== "postgresql+psycopg:" ||
    !parsed.hostname ||
    !parsed.username ||
    !databaseName.endsWith("_test")
  ) {
    throw new Error(
      "PLAYWRIGHT_TEST_DATABASE_URL must use postgresql+psycopg and name a database ending in _test.",
    );
  }
  return createHash("sha256")
    .update(`pm9-test-database:${databaseName}`, "utf8")
    .digest("hex");
}

export const browserEnvironment = {
  frontendUrl: loopbackUrl("PLAYWRIGHT_BASE_URL", "http://127.0.0.1:3000"),
  apiUrl: loopbackUrl("PLAYWRIGHT_API_URL", "http://127.0.0.1:8000"),
  expectedDatabaseFingerprint: expectedDatabaseFingerprint(),
};

export function credentialsFor(role: DemoRole): { identifier: string; password: string } {
  const prefix = `PLAYWRIGHT_${role.toUpperCase()}`;
  const identifier = process.env[`${prefix}_USERNAME`]?.trim() || defaultUsernames[role];
  const password =
    process.env[`${prefix}_PASSWORD`] || requiredSecret("PLAYWRIGHT_DEMO_PASSWORD");
  return { identifier, password };
}

export function fingerprintsMatch(actual: unknown): boolean {
  if (typeof actual !== "string") return false;
  const expectedBuffer = Buffer.from(browserEnvironment.expectedDatabaseFingerprint, "utf8");
  const actualBuffer = Buffer.from(actual, "utf8");
  return (
    actualBuffer.length === expectedBuffer.length &&
    timingSafeEqual(actualBuffer, expectedBuffer)
  );
}
