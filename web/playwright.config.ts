import { defineConfig, devices } from "@playwright/test";

/**
 * Browser journeys: complete tasks of the owner against the real backend.
 * The server uses a temporary data directory and the built client, so a run
 * never reads or writes an installation database.
 */
const PORT = 8765;

export default defineConfig({
  testDir: "tests/journeys",
  outputDir: "var/journeys/results",
  reporter: [["list"], ["html", { outputFolder: "var/journeys/report", open: "never" }]],
  fullyParallel: false,
  workers: 1, // The journeys share one database.
  retries: 0,
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `bash tests/journeys/serve.sh ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
