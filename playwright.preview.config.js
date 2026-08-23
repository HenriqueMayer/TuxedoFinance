const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
    testDir: './tests/preview',
    fullyParallel: false,
    workers: 1,
    reporter: process.env.CI ? [['line'], ['html', { open: 'never' }]] : 'line',
    use: {
        baseURL: 'http://127.0.0.1:4173',
        screenshot: 'only-on-failure',
        trace: 'retain-on-failure',
        ...devices['Desktop Chrome'],
    },
    webServer: {
        command: 'uv run python -m http.server 4173 --bind 127.0.0.1 --directory preview',
        url: 'http://127.0.0.1:4173/',
        reuseExistingServer: !process.env.CI,
        timeout: 30_000,
    },
    outputDir: 'test-results/preview',
});
