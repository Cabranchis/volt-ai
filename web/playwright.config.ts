import { defineConfig, devices } from "@playwright/test";

const PORT = 3100;

/**
 * End-to-end tests run against the production build, on JSON fixtures (no database, no API keys).
 * Locally, PW_CHANNEL=msedge reuses the installed Edge instead of downloading Chromium.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://localhost:${PORT}`,
    channel: process.env.PW_CHANNEL || undefined,
    trace: "retain-on-failure",
    // Entrance animations are covered by the reduced-motion rule, so axe never sees a half-faded page.
    reducedMotion: "reduce",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], channel: process.env.PW_CHANNEL || undefined } }],
  webServer: {
    command: `npx next start -p ${PORT}`,
    port: PORT,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    // Empty values beat web/.env.local, so tests never read the real database or spend the Gemini quota.
    env: { VOLTIA_DATA_SOURCE: "fixtures", GOOGLE_GENERATIVE_AI_API_KEY: "", DATABASE_URL_READONLY: "" },
  },
});
