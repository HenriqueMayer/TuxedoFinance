import { defineConfig, devices } from "@playwright/test";

/**
 * Checks of the built site: the pages and the demonstration run from static
 * files. Build first (`npm run build`); the server only serves `dist/`.
 */
const PORT = 4323;

export default defineConfig({
  testDir: "tests",
  outputDir: "test-results",
  reporter: [["list"]],
  workers: 1,
  use: { baseURL: `http://127.0.0.1:${PORT}/TuxedoFinance/` },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `node tests/serve.mjs ${PORT}`,
    url: `http://127.0.0.1:${PORT}/TuxedoFinance/`,
    reuseExistingServer: false,
  },
});
