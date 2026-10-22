// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

test.skip(process.env.E2E_ASSISTANT_FIXTURES !== '1', 'Use the guarded --assistant-fixtures disposable runner.');

async function start(page, info, {width = 1440, theme = 'light', language = 'en', motion = 'no-preference'} = {}) {
    await page.setViewportSize({width, height: 844});
    await page.emulateMedia({reducedMotion: motion});
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    const response = await page.request.get('/accounts/signup/');
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const username = `rich-${info.workerIndex}-${Date.now()}`;
    const created = await page.request.post('/accounts/signup/', {form: {
        csrfmiddlewaretoken: token, username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!',
    }, headers: {Referer: response.url()}, maxRedirects: 0});
    expect(created.status(), await created.text()).toBe(302);
    await page.context().addCookies([{name: 'django_language', value: language, url: info.project.use.baseURL}]);
    await page.goto('/assistant/');
    const form = page.locator('[data-assistant-send]');
    await form.locator('[data-assistant-settings] > summary').press('Enter');
    await form.locator('select[name="model"]').selectOption('mock-standard');
    await form.locator('textarea').focus();
    return form;
}

for (const theme of ['light', 'dark']) for (const width of [1440, 390]) {
    const language = width === 390 ? 'pt-br' : 'en';
    test(`Reply progress and Markdown (${theme}, ${width}, ${language})`, async ({page}, info) => {
        const errors = [], external = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('request', request => { if (!['127.0.0.1', 'localhost'].includes(new URL(request.url()).hostname)) external.push(request.url()); });
        let form = await start(page, info, {width, theme, language});
        await form.locator('textarea').fill('[thinking]');
        await form.locator('textarea').press('Enter');
        const pending = page.locator('[data-assistant-progress]');
        await expect(pending).toHaveText(language === 'en' ? 'Thinking…' : 'Pensando…');
        await expect(pending).toBeInViewport();
        const stop = form.locator('[data-assistant-stop]');
        await expect(stop).toBeVisible();
        const bounds = await stop.boundingBox();
        expect(bounds.width).toBeGreaterThanOrEqual(44); expect(bounds.height).toBeGreaterThanOrEqual(44);
        await page.screenshot({path: info.outputPath(`thinking-${theme}-${width}.png`)});
        await expect(page.locator('.assistant-message--assistant strong')).toHaveText('value');
        await expect(pending).toHaveCount(0);
        await expect(form.locator('[data-assistant-send-status]')).toHaveText(language === 'en' ? 'Writing a response…' : 'Escrevendo uma resposta…');
        await expect(page.locator('[data-assistant-send]')).not.toHaveAttribute('aria-busy');
        form = page.locator('[data-assistant-send]');
        await form.locator('textarea').fill('[markdown]'); await form.locator('textarea').press('Enter');
        await expect(page.locator('[data-assistant-send]')).not.toHaveAttribute('aria-busy');
        const answer = page.locator('.assistant-message--assistant').last();
        await expect(answer.locator('h3')).toHaveText('Resumo');
        await expect(answer.locator('strong')).toHaveText(['Valor', '10,00']);
        await expect(answer.locator('em')).toHaveText('estimativa');
        await expect(answer.locator('ul li')).toHaveText(['Receita', 'Despesa']);
        await expect(answer.locator('blockquote')).toContainText('Dados sintéticos.');
        await expect(answer.locator('table tbody td')).toHaveText(['Previsto', '10,00']);
        await expect(answer.locator('pre code')).toContainText('<img src=x');
        // Copy/download actions are deliberate application links outside the
        // renderer. Model Markdown itself must never create executable nodes.
        await expect(answer.locator('.assistant-message-text').locator('img, script, iframe, a')).toHaveCount(0);
        expect(await page.evaluate(() => window.__assistantInjected)).toBeUndefined();
        const transcript = page.locator('[data-assistant-transcript]');
        expect(await transcript.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
        await answer.locator('h3').scrollIntoViewIfNeeded();
        await page.screenshot({path: info.outputPath(`markdown-${theme}-${width}.png`)});
        await page.reload();
        await expect(page.locator('.assistant-message--assistant').last().locator('strong')).toHaveText(['Valor', '10,00']);
        expect(errors).toEqual([]); expect(external).toEqual([]);
    });
}

test('Waiting can be cancelled with the keyboard, errors clear it and reduced motion stops decoration', async ({page}, info) => {
    let form = await start(page, info, {width: 390, theme: 'dark', motion: 'reduce'});
    await form.locator('textarea').fill('[thinking]'); await form.locator('textarea').press('Enter');
    const waiting = page.locator('[data-assistant-progress]');
    await expect(waiting).toBeVisible();
    expect(await waiting.locator('i').first().evaluate(node => getComputedStyle(node).animationName)).toBe('none');
    const stop = form.locator('[data-assistant-stop]');
    await stop.focus(); await expect(stop).toBeInViewport(); await stop.press('Enter');
    await expect(waiting).toHaveCount(0);
    await expect(form).not.toHaveAttribute('aria-busy');
    await expect(form.locator('[data-assistant-send-status]')).toContainText('Response stopped.');
    await form.locator('textarea').fill('[error]'); await form.locator('textarea').press('Enter');
    await expect(form).not.toHaveAttribute('aria-busy');
    await expect(waiting).toHaveCount(0);
    await expect(form.locator('[data-assistant-send-status]')).toContainText('could not be completed');
    await page.screenshot({path: info.outputPath('thinking-error-reduced-phone.png')});
});

async function expectVerifiedReferences(answer) {
    const body = answer.locator('.assistant-message-text');
    await expect(body).toContainText('Premissas sintéticas:');
    await expect(body).toContainText('desconto em folha BRL 700,00');
    await expect(body).toContainText('<estimativa>');
    await expect(body).not.toContainText('/sandbox/');
    await expect(body).not.toContainText('/planning/');
    await expect(body.locator('img, script, iframe, a, estimativa')).toHaveCount(0);
    const links = answer.locator('.assistant-references a');
    await expect(links).toHaveCount(2);
    const destinations = await links.evaluateAll(nodes => nodes.map(link => new URL(link.href).pathname + new URL(link.href).search));
    expect(destinations).toEqual(['/sandbox/', '/planning/?month=2026-10']);
    for (const link of await links.all()) {
        const label = (await link.textContent()).replace('↗', '').trim();
        await expect(body).not.toContainText(label);
        await expect(link).toHaveAccessibleName(new RegExp(label));
    }
    await links.first().focus(); await links.first().press('Tab');
    await expect(links.nth(1)).toBeFocused();
    await expect(links.nth(1)).toBeInViewport();
    await links.nth(1).press('Shift+Tab'); await expect(links.first()).toBeFocused();
}

for (const theme of ['light', 'dark']) for (const width of [1440, 390]) {
    const language = width === 390 ? 'pt-br' : 'en';
    test(`Verified reference footer is not repeated in Markdown (${theme}, ${width}, ${language})`, async ({page}, info) => {
        const errors = [], external = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('request', request => { if (!['127.0.0.1', 'localhost'].includes(new URL(request.url()).hostname)) external.push(request.url()); });
        await start(page, info, {theme, width, language});
        await page.goto('/planning/');
        await page.getByRole('button', {name: language === 'en' ? 'Open Tuxedo assistant' : 'Abrir assistente Tuxedo', exact: true}).press('Enter');
        const panel = page.locator('#assistant-panel');
        const form = panel.locator('[data-assistant-send]');
        await expect(form).toBeVisible();
        await form.locator('[data-assistant-settings] > summary').press('Enter');
        await form.locator('select[name="model"]').selectOption('mock-standard');
        let release, captured;
        const gate = new Promise(resolve => { release = resolve; });
        const pending = new Promise(resolve => { captured = resolve; });
        await page.route(/\/assistant\/[a-f0-9-]{36}\/(?:\?.*)?$/, async route => {
            if (route.request().method() !== 'GET') return route.continue();
            captured(); await gate; await route.continue().catch(() => {});
        }, {times: 1});
        await form.locator('textarea').fill('[references]'); await form.locator('textarea').press('Enter');
        await pending;
        const answer = panel.locator('.assistant-message--assistant').last();
        // The server reload is still blocked. The SSE done event itself must
        // replace the raw citation footer with the two authoritative links.
        try {
            await expectVerifiedReferences(answer);
            await page.screenshot({path: info.outputPath(`references-stream-done-${theme}-${width}.png`)});
        } finally { release(); }
        await expect(panel.locator('[data-assistant-send]')).not.toHaveAttribute('aria-busy');
        await expectVerifiedReferences(answer);
        const exported = await page.request.get(await answer.locator('[data-assistant-copy]').getAttribute('href'));
        const markdown = await exported.text();
        expect(markdown).toContain('](/sandbox/)');
        expect(markdown).toContain('](/planning/?month=2026-10)');
        expect(markdown).toContain('**desconto em folha BRL 700,00**');
        const conversation = await panel.locator('[data-conversation-id]').getAttribute('data-conversation-id');
        const detail = `/assistant/${conversation}/`;
        await page.goto(detail); await page.reload();
        await expectVerifiedReferences(page.locator('.assistant-message--assistant').last());
        const navigation = page.locator(`[data-app-navigation="${width >= 1024 ? 'desktop' : 'mobile'}"] a[href="/planning/"]`);
        const navigated = page.waitForResponse(response => response.request().resourceType() === 'xhr'
            && new URL(response.url()).pathname === '/planning/');
        await navigation.press('Enter'); expect((await navigated).ok()).toBe(true);
        await expect(page).toHaveURL(/\/planning\/$/);
        await page.goBack(); await expect(page).toHaveURL(new RegExp(detail + '$'));
        await expectVerifiedReferences(page.locator('.assistant-message--assistant').last());
        await page.screenshot({path: info.outputPath(`references-restored-${theme}-${width}.png`)});
        expect(errors).toEqual([]); expect(external).toEqual([]);
    });
}

test('Native reference replies retain escaped Markdown and authoritative source links without JavaScript', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, baseURL: info.project.use.baseURL,
        viewport: {width: 390, height: 844}, locale: 'en'});
    try {
        const page = await context.newPage();
        const form = await start(page, info, {width: 390});
        await form.locator('textarea').fill('[references]');
        await form.getByRole('button', {name: 'Send message', exact: true}).click();
        const answer = page.locator('.assistant-message--assistant').last();
        const body = answer.locator('.assistant-message-text');
        await expect(body).toContainText('**desconto em folha BRL 700,00**');
        await expect(body).toContainText('<estimativa>');
        await expect(body).toContainText('](/sandbox/)');
        await expect(body).toContainText('](/planning/?month=2026-10)');
        await expect(body.locator('a, img, script, estimativa')).toHaveCount(0);
        await expect(answer.locator('.assistant-references a')).toHaveCount(2);
        expect(await answer.locator('.assistant-references a').evaluateAll(nodes => nodes.map(link => new URL(link.href).pathname + new URL(link.href).search)))
            .toEqual(['/sandbox/', '/planning/?month=2026-10']);
        const response = await page.request.get(page.url());
        expect(await response.text()).toContain('&lt;estimativa&gt;');
        await page.screenshot({path: info.outputPath('references-native-phone.png')});
    } finally { await context.close(); }
});
