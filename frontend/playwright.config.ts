import { defineConfig } from "@playwright/test";

import { browserEnvironment } from "./e2e/support/environment";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  timeout: 180_000,
  expect: { timeout: 20_000 },
  reporter: [["line"]],
  outputDir: "test-results/playwright",
  preserveOutput: "never",
  use: {
    baseURL: browserEnvironment.frontendUrl,
    actionTimeout: 20_000,
    navigationTimeout: 30_000,
    locale: "vi-VN",
    timezoneId: "Asia/Ho_Chi_Minh",
    trace: "off",
    screenshot: "off",
    video: "off",
  },
  projects: [
    {
      name: "desktop-chromium",
      testMatch: /desktop\/.*\.spec\.ts/,
      use: {
        browserName: "chromium",
        viewport: { width: 1366, height: 768 },
      },
    },
    {
      name: "mobile-chromium",
      testMatch: /mobile\/.*\.spec\.ts/,
      use: {
        browserName: "chromium",
        viewport: { width: 390, height: 844 },
        hasTouch: true,
        isMobile: true,
      },
    },
  ],
});
