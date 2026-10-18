const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {randomBytes} = require('node:crypto');
const { defineConfig, devices } = require('@playwright/test');

const projectRoot = path.resolve(__dirname, '../..');
// Workers reload the configuration; inherit the coordinator's owned endpoint.
const port = Number(process.env.TUXEDO_PREVIEW_TEST_PORT || execFileSync('uv', ['run', 'python', '-c',
    'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'],
    {cwd: projectRoot, encoding: 'utf8'}).trim());
const baseURL = `http://127.0.0.1:${port}`;
const readyToken = process.env.TUXEDO_PREVIEW_TEST_TOKEN || randomBytes(16).toString('hex');
if (!Number.isInteger(port) || port < 1 || port > 65535 || !/^[a-f0-9]{32}$/.test(readyToken)) {
    throw new Error('Invalid internal preview test endpoint.');
}
process.env.TUXEDO_PREVIEW_TEST_PORT = String(port);
process.env.TUXEDO_PREVIEW_TEST_TOKEN = readyToken;

module.exports = defineConfig({
    testDir: path.join(projectRoot, 'tests/preview'),
    fullyParallel: false,
    workers: 1,
    reporter: process.env.CI ? [['line'], ['html', { open: 'never', outputFolder: path.join(projectRoot, '.local/playwright-report/preview') }]] : 'line',
    use: {
        baseURL,
        screenshot: 'only-on-failure',
        trace: 'retain-on-failure',
        ...devices['Desktop Chrome'],
    },
    webServer: {
        command: `uv run python scripts/preview/serve.py --static --port ${port} --ready-token ${readyToken}`,
        cwd: projectRoot,
        url: `${baseURL}/__preview_ready__/${readyToken}`,
        reuseExistingServer: false,
        timeout: 30_000,
    },
    outputDir: path.join(projectRoot, '.local/test-results/preview'),
});
