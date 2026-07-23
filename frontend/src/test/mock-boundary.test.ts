import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const liveFiles = [
  "src/app/page.tsx",
  "src/app/assets/page.tsx",
  "src/app/assets/[assetId]/page.tsx",
  "src/app/tickets/page.tsx",
  "src/app/anomalies/page.tsx",
  "src/app/copilot/page.tsx",
  "src/components/asset-browser.tsx",
  "src/components/asset-detail-view.tsx",
  "src/components/asset-detail-tabs.tsx",
  "src/components/ticket-workspace.tsx",
  "src/components/anomaly-workspace.tsx",
  "src/components/dashboard-charts.tsx",
  "src/components/copilot-workspace.tsx",
  "src/components/source-card.tsx",
  "src/components/inventory-workspace.tsx",
  "src/components/part-catalogue.tsx",
  "src/components/part-detail.tsx",
  "src/components/inventory-action-form.tsx",
  "src/components/work-order-parts-panel.tsx",
];

describe("mock data boundary", () => {
  it("keeps live production screens independent from runtime mock data", () => {
    liveFiles.forEach((relativePath) => {
      const contents = readFileSync(resolve(process.cwd(), relativePath), "utf8");
      expect(contents, relativePath).not.toContain("@/lib/mock-data");
    });
  });
});
