const { defineConfig, devices } = require('@playwright/test');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');

module.exports = defineConfig({
    testDir: path.join(ROOT, 'tests/e2e'),
    fullyParallel: false,
    workers: 1,
    reporter: process.env.CI
        ? [['line'], ['html', { open: 'never', outputFolder: path.join(ROOT, '.local/playwright-report') }]]
        : 'line',
    use: {
        baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:8765',
        screenshot: 'only-on-failure',
        trace: 'retain-on-failure',
        video: 'retain-on-failure',
        ...devices['Desktop Chrome'],
    },
    // Playwright clears this directory; keep active runner data and logs beside it.
    outputDir: path.join(ROOT, '.local/test-results/browser'),
});
