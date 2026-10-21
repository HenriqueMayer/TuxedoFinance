// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const fs = require('node:fs/promises');

test.skip(process.env.E2E_ASSISTANT_FIXTURES !== '1', 'Use the guarded --assistant-fixtures disposable runner.');

async function post(page, path, values = {}, source = path) {
    const response = await page.request.get(source);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...values},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(saved.status(), await saved.text()).toBe(302);
    return saved;
}

async function signup(page, info, suffix = '') {
    const username = `copy-${info.workerIndex}-${Date.now()}${suffix}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
}

async function open(page, info, {width = 1440, theme = 'light', language = 'en'} = {}) {
    await page.addInitScript(value => {
        localStorage.setItem('theme', value);
        // Keep the workstation clipboard untouched. Only the browser's narrow
        // writeText boundary is simulated; keyboard, auth GETs and exports are real.
        Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {
            async writeText(text) { window.__syntheticMarkdownClipboard = text; },
        }});
    }, theme);
    await page.setViewportSize({width, height: 900});
    await signup(page, info);
    await page.context().addCookies([{name: 'django_language', value: language, url: info.project.use.baseURL}]);
    await page.goto('/transactions/create/');
    await page.locator('#id_title').fill('Financial draft preserved by copying');
    await page.getByRole('button', {name: language === 'en' ? 'Open Tuxedo assistant' : 'Abrir assistente Tuxedo', exact: true}).press('Enter');
    const panel = page.locator('#assistant-panel');
    await expect(panel.locator('[data-assistant-send]')).toBeVisible();
    await panel.locator('[data-assistant-settings] > summary').press('Enter');
    await panel.locator('select[name="model"]').selectOption('mock-standard');
    await panel.locator('[data-assistant-settings] > summary').press('Escape');
    return panel;
}

async function send(panel, text) {
    await panel.locator('[data-assistant-send] textarea').fill(text);
    await panel.locator('[data-assistant-send] textarea').press('Enter');
    await expect(panel.locator('[data-assistant-send]')).not.toHaveAttribute('aria-busy');
}

async function copied(page, control, expected) {
    await control.focus(); await control.press('Enter');
    await expect.poll(() => page.evaluate(() => window.__syntheticMarkdownClipboard)).toEqual(expected);
    await expect(control.locator('..').locator('[data-assistant-copy-status]')).not.toBeEmpty();
}

for (const theme of ['light', 'dark']) for (const width of [1440, 390]) {
    const language = width === 390 ? 'pt-br' : 'en';
    test(`Copy message and conversation Markdown (${theme}, ${width}, ${language})`, async ({page}, info) => {
        const errors = [], external = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('request', request => { if (!['127.0.0.1', 'localhost'].includes(new URL(request.url()).hostname)) external.push(request.url()); });
        const panel = await open(page, info, {width, theme, language});
        await send(panel, '[markdown]');
        const answer = panel.locator('.assistant-message--assistant').last();
        const copyAnswer = answer.locator('[data-assistant-copy]');
        const response = await page.request.get(await copyAnswer.getAttribute('href'));
        const raw = await response.text();
        expect(raw).toContain('**Valor**'); expect(raw).toContain('```html');
        expect(raw).toContain('[Conta](/banking/123/)');
        await panel.locator('[data-assistant-send] textarea').fill('Unsent chat draft preserved');
        const scroll = await panel.locator('[data-assistant-transcript]').evaluate(node => node.scrollTop);
        await copied(page, copyAnswer, raw);
        await expect(copyAnswer).toBeFocused();
        const bounds = await copyAnswer.boundingBox();
        expect(bounds.width).toBeGreaterThanOrEqual(44); expect(bounds.height).toBeGreaterThanOrEqual(44);
        await expect(panel.locator('[data-assistant-send] textarea')).toHaveValue('Unsent chat draft preserved');
        await expect(page.locator('#id_title')).toHaveValue('Financial draft preserved by copying');
        expect(await panel.locator('[data-assistant-transcript]').evaluate(node => node.scrollTop)).toBeGreaterThanOrEqual(scroll - 1);
        const copyUser = panel.locator('.assistant-message--user').last().locator('[data-assistant-copy]');
        await copied(page, copyUser, '[markdown]');
        await panel.locator('.assistant-delete > summary').press('Enter');
        const whole = panel.locator('.assistant-conversation-menu [data-assistant-copy]');
        const full = await page.request.get(await whole.getAttribute('href'));
        const fullMarkdown = await full.text();
        expect(fullMarkdown).toContain('[markdown]'); expect(fullMarkdown).toContain(raw);
        await copied(page, whole, fullMarkdown);
        await page.screenshot({path: info.outputPath(`copy-menu-${theme}-${width}.png`)});
        await panel.locator('.assistant-delete > summary').press('Escape');
        const history = panel.locator('.assistant-history > summary');
        await history.focus(); await history.press('Enter');
        const disclosure = panel.locator('.assistant-history-popover');
        const privacy = disclosure.locator('.assistant-history-footer p');
        await expect(privacy).toHaveText(language === 'en'
            ? 'The assistant can consult relevant saved financial records to answer. Your question, necessary history and consulted records are sent to OpenAI; history stays on this installation.'
            : 'O assistente pode consultar registros financeiros salvos relevantes para responder. Sua pergunta, o histórico necessário e os registros consultados são enviados à OpenAI; o histórico fica nesta instalação.');
        await expect(disclosure).toBeVisible();
        const privacyBounds = await privacy.boundingBox();
        expect(privacyBounds.x).toBeGreaterThanOrEqual(0);
        expect(privacyBounds.y).toBeGreaterThanOrEqual(0);
        expect(privacyBounds.x + privacyBounds.width).toBeLessThanOrEqual(width);
        expect(privacyBounds.y + privacyBounds.height).toBeLessThanOrEqual(900);
        await page.screenshot({path: info.outputPath(`history-disclosure-${theme}-${width}.png`)});
        await history.press('Escape');
        await expect(panel.locator('.assistant-history')).not.toHaveAttribute('open', '');
        await expect(history).toBeFocused();
        await expect(panel.locator('[data-assistant-send] textarea')).toHaveValue('Unsent chat draft preserved');
        await expect(page.locator('#departure-confirm')).toBeHidden();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
        expect(errors).toEqual([]); expect(external).toEqual([]);
    });
}

test('Clipboard failure keeps native Markdown download, focus and financial drafts', async ({page}, info) => {
    const panel = await open(page, info, {width: 390, theme: 'dark'});
    await send(panel, '[markdown]');
    await page.evaluate(() => { navigator.clipboard.writeText = async () => { throw new DOMException('Synthetic refusal', 'NotAllowedError'); }; });
    const article = panel.locator('.assistant-message--assistant').last();
    const copy = article.locator('[data-assistant-copy]');
    await copy.focus(); await copy.press('Enter');
    const fallback = article.locator('[data-assistant-copy-download]');
    await expect(fallback).toBeVisible();
    await expect(article.locator('[data-assistant-copy-status]')).toContainText('Could not copy.');
    const downloaded = page.waitForEvent('download');
    await fallback.press('Enter');
    const file = await downloaded;
    expect(file.suggestedFilename()).toMatch(/^tuxedo-message-[a-f0-9-]+\.md$/);
    expect(await fs.readFile(await file.path(), 'utf8')).toContain('**Valor**');
    await expect(page.locator('#id_title')).toHaveValue('Financial draft preserved by copying');
    await expect(page.locator('#departure-confirm')).toBeHidden();
    await page.screenshot({path: info.outputPath('copy-download-fallback-phone.png')});
});

test('A streamed partial copies its original Markdown after fresh authorization', async ({page}, info) => {
    const panel = await open(page, info);
    await panel.locator('[data-assistant-send] textarea').fill('[thinking]');
    await panel.locator('[data-assistant-send] textarea').press('Enter');
    const answer = panel.locator('.assistant-message--assistant').last();
    await expect(answer.locator('strong')).toHaveText('value');
    const live = answer.locator('[data-assistant-copy-live]');
    await copied(page, live, 'Synthetic **value**');
    await expect(panel.locator('[data-assistant-send]')).not.toHaveAttribute('aria-busy');
    await expect(panel.locator('.assistant-message--assistant [data-assistant-copy]')).toHaveAttribute('href', /\/messages\/[a-f0-9-]+\/export\/$/);
});

test('Stale account/session cannot copy a hidden or old transcript', async ({page}, info) => {
    const panel = await open(page, info);
    await send(panel, 'Synthetic private message');
    const copy = panel.locator('.assistant-message--user').last().locator('[data-assistant-copy]');
    await copied(page, copy, 'Synthetic private message');
    await post(page, '/accounts/logout/', {}, '/assistant/');
    await signup(page, info, '-other');
    await page.evaluate(() => { window.__syntheticMarkdownClipboard = 'unchanged'; });
    await copy.press('Enter');
    await expect(copy.locator('..').locator('[data-assistant-copy-status]')).toContainText('Could not copy.');
    expect(await page.evaluate(() => window.__syntheticMarkdownClipboard)).toBe('unchanged');
});

test('An in-flight transcript is reauthorized before copying after another tab signs out', async ({page}, info) => {
    const panel = await open(page, info);
    await send(panel, 'Synthetic old-session response');
    const copy = panel.locator('.assistant-message--assistant').last().locator('[data-assistant-copy]');
    const url = await copy.getAttribute('href');
    let release, captured;
    const gate = new Promise(resolve => { release = resolve; });
    const ready = new Promise(resolve => { captured = resolve; });
    await page.route(new RegExp(url + '$'), async route => {
        if (route.request().method() !== 'GET') return route.continue();
        const response = await route.fetch(); const body = await response.body();
        captured(); await gate; await route.fulfill({response, body});
    }, {times: 1});
    await copy.press('Enter'); await ready;
    try { await post(page, '/accounts/logout/', {}, '/assistant/'); }
    finally { release(); }
    await expect(copy.locator('..').locator('[data-assistant-copy-status]')).toContainText('Could not copy.');
    expect(await page.evaluate(() => window.__syntheticMarkdownClipboard)).toBeUndefined();
});

test('Native chat offers owned message and conversation Markdown downloads without JavaScript', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, baseURL: info.project.use.baseURL,
        viewport: {width: 390, height: 844}, locale: 'en'});
    try {
        const page = await context.newPage(); await signup(page, info);
        await page.goto('/assistant/');
        const form = page.locator('[data-assistant-send]');
        await form.locator('[data-assistant-settings] > summary').press('Enter');
        await form.locator('select[name="model"]').selectOption('mock-standard');
        await form.locator('textarea').fill('[markdown]');
        await form.getByRole('button', {name: 'Send message', exact: true}).click();
        const url = page.url();
        let pending = page.waitForEvent('download');
        await page.locator('.assistant-message--assistant [data-assistant-copy]').click();
        let download = await pending;
        expect(await fs.readFile(await download.path(), 'utf8')).toContain('**Valor**');
        await page.locator('.assistant-delete > summary').click();
        pending = page.waitForEvent('download');
        await page.locator('.assistant-conversation-menu [data-assistant-copy]').click();
        download = await pending;
        const full = await fs.readFile(await download.path(), 'utf8');
        expect(full).toContain('## You'); expect(full).toContain('**Valor**');
        expect(page.url()).toBe(url);
        await page.screenshot({path: info.outputPath('copy-native-phone.png')});
    } finally { await context.close(); }
});
