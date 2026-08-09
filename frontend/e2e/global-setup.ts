import { request } from "@playwright/test";

import {
  browserEnvironment,
  credentialsFor,
  fingerprintsMatch,
  type DemoRole,
} from "./support/environment";

interface LiveHealth {
  status?: unknown;
  test_database_fingerprint?: unknown;
}

export default async function globalSetup() {
  const api = await request.newContext({ baseURL: browserEnvironment.apiUrl });
  try {
    const response = await api.get("/health/live");
    if (!response.ok()) {
      throw new Error("The loopback API live-health probe did not return success.");
    }
    const health = (await response.json()) as LiveHealth;
    if (health.status !== "alive" || !fingerprintsMatch(health.test_database_fingerprint)) {
      throw new Error(
        "The loopback API did not attest to the supplied PostgreSQL _test database.",
      );
    }
  } finally {
    await api.dispose();
  }

  for (const role of ["manager", "technician", "storekeeper"] satisfies DemoRole[]) {
    credentialsFor(role);
  }

  const frontend = await request.newContext({ baseURL: browserEnvironment.frontendUrl });
  try {
    const response = await frontend.get("/login");
    if (!response.ok() || !response.headers()["content-type"]?.includes("text/html")) {
      throw new Error("The loopback frontend login page is not ready.");
    }
  } finally {
    await frontend.dispose();
  }
}
