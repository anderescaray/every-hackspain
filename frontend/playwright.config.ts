import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",
  fullyParallel: true,
  use: { baseURL: "http://127.0.0.1:3106", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" } },
  ],
  webServer: [
    {
      command: "npx tsx scripts/fixtureServer.ts start --hostname 127.0.0.1 --port 3106",
      url: "http://127.0.0.1:3106/companies/COMP_0356",
      reuseExistingServer: false,
      timeout: 120000,
    },
    {
      command: "npx tsx scripts/fixtureServer.ts empty --hostname 127.0.0.1 --port 3108",
      url: "http://127.0.0.1:3108/companies/COMP_0356",
      reuseExistingServer: false,
      timeout: 120000,
    },
  ],
});
