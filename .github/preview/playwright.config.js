const path = require('node:path');
const { defineConfig, devices } = require('@playwright/test');

const projectRoot = path.resolve(__dirname, '../..');

module.exports = defineConfig({
    testDir: path.join(projectRoot, 'tests/preview'),
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
        cwd: projectRoot,
        url: 'http://127.0.0.1:4173/',
        reuseExistingServer: !process.env.CI,
        timeout: 30_000,
    },
    outputDir: path.join(projectRoot, 'test-results/preview'),
});
