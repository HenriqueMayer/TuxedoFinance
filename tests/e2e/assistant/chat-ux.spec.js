// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

test.skip(process.env.E2E_ASSISTANT_FIXTURES !== '1', 'Use the guarded --assistant-fixtures disposable runner.');

async function signup(page, info) {
    const response = await page.request.get('/accounts/signup/');
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const username = `chat-ux-${info.workerIndex}-${Date.now()}`;
    const created = await page.request.post('/accounts/signup/', {form: {
        csrfmiddlewaretoken: token, username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!',
    }, headers: {Referer: response.url()}, maxRedirects: 0});
    expect(created.status(), await created.text()).toBe(302);
}

async function openChat(page, info, {theme = 'light', width = 1440, height = 900, language = 'en'} = {}) {
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    await page.setViewportSize({width, height});
    await signup(page, info);
    if (language !== 'en') await page.context().addCookies([{name: 'django_language', value: language, url: info.project.use.baseURL}]);
    await page.goto('/banking/');
    await page.getByRole('button', {name: language === 'pt-br' ? 'Abrir assistente Tuxedo' : 'Open Tuxedo assistant', exact: true}).press('Enter');
    const panel = page.locator('#assistant-panel');
    await expect(panel.locator('[data-assistant-send]')).toBeVisible();
    await selectModel(panel, 'mock-standard');
    return panel;
}

async function selectModel(panel, value) {
    const settings = panel.locator('[data-assistant-settings]');
    const summary = settings.locator(':scope > summary');
    if (!await settings.evaluate(node => node.open)) await summary.press('Enter');
    await settings.locator('select[name="model"]').selectOption(value);
    await summary.press('Escape');
    await expect(settings).not.toHaveAttribute('open');
}

async function send(page, panel, text) {
    await panel.locator('[data-assistant-send] textarea').fill(text);
    await panel.locator('[data-assistant-send] textarea').press('Enter');
    await expect(panel.locator('.assistant-message--assistant')).not.toHaveCount(0);
    if (text.includes('[long]')) await expect(panel.locator('.assistant-message--assistant').last()).toContainText('Paragraph 52.');
    await expect(panel.locator('[data-assistant-send]')).not.toHaveAttribute('aria-busy');
    await expect(panel.locator('[data-assistant-send-status]')).not.toHaveClass(/assistant-send-status--error/);
}

async function tailDistance(transcript) {
    return transcript.evaluate(node => node.scrollHeight - node.clientHeight - node.scrollTop);
}

async function expectInsideViewport(locator, viewport) {
    await expect(locator).toBeInViewport();
    const bounds = await locator.boundingBox();
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.y).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(viewport.width + 1);
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(viewport.height + 1);
}

async function expectMinimumTarget(locator) {
    const bounds = await locator.boundingBox();
    // Browser transforms can report 43.999998 for a stationary 44px box.
    expect(bounds.width).toBeGreaterThanOrEqual(43.99);
    expect(bounds.height).toBeGreaterThanOrEqual(43.99);
}

async function expectSeparateControls(...controls) {
    const bounds = await Promise.all(controls.map(control => control.boundingBox()));
    for (let index = 0; index < bounds.length; index += 1) for (const other of bounds.slice(index + 1)) {
        const current = bounds[index];
        // Small screens may put consent on a second row. Either axis must
        // separate the actual targets, even with a long native model label.
        expect(current.x + current.width <= other.x + 1 || other.x + other.width <= current.x + 1
            || current.y + current.height <= other.y + 1 || other.y + other.height <= current.y + 1).toBe(true);
    }
}

async function expectSavedSettings(page, model, effort) {
    // An authorized fresh GET proves settings were saved on the server rather
    // than merely retained in a hidden panel or browser storage.
    await expect.poll(async () => {
        const response = await page.request.get('/assistant/');
        const html = await response.text();
        return ['model', 'reasoning_effort'].map(name => {
            const select = html.match(new RegExp(`<select[^>]*name="${name}"[^>]*>([\\s\\S]*?)<\\/select>`))?.[1] || '';
            return select.match(/<option[^>]*value="([^"]*)"[^>]*selected[^>]*>/)?.[1] || '';
        });
    }).toEqual([model, effort]);
}

async function expectSettingsGear(summary) {
    await expectMinimumTarget(summary);
    const geometry = await summary.locator('svg').evaluate(svg => {
        const rect = svg.getBoundingClientRect();
        const circle = svg.querySelector('circle, path:last-child').getBoundingClientRect();
        return {width: rect.width, height: rect.height, x: circle.x + circle.width / 2, y: circle.y + circle.height / 2,
            centerX: rect.x + rect.width / 2, centerY: rect.y + rect.height / 2,
            ratio: getComputedStyle(svg).flexShrink};
    });
    expect(geometry.width).toBeCloseTo(16, 1);
    expect(geometry.height).toBeCloseTo(16, 1);
    expect(geometry.ratio).toBe('0');
    // The gear's hole and outer path share a square coordinate system; a
    // crowded model caption must not compress the glyph into an oval.
    expect(geometry.x).toBeCloseTo(geometry.centerX, 1);
    expect(geometry.y).toBeCloseTo(geometry.centerY, 1);
}

async function expectCompactChat(panel) {
    // Compact chrome must release room for the conversation without shrinking
    // its native activation targets or introducing another context toolbar.
    const chrome = await panel.evaluate(node => {
        const header = node.querySelector('.assistant-panel-header').getBoundingClientRect();
        const toolbar = node.querySelector('.assistant-content-toolbar').getBoundingClientRect();
        const context = node.querySelector('[data-assistant-context-link]').getBoundingClientRect();
        const transcript = node.querySelector('[data-assistant-transcript]').getBoundingClientRect();
        const frame = node.querySelector('.assistant-composer-frame').getBoundingClientRect();
        const caption = node.querySelector('.assistant-model-caption');
        return {header: header.height, toolbar: toolbar.height, contextY: context.y,
            toolbarY: toolbar.y, chrome: transcript.y - header.y, composer: frame.height,
            captionHeight: caption.getBoundingClientRect().height,
            captionLine: parseFloat(getComputedStyle(caption).lineHeight)};
    });
    expect(chrome.header).toBeLessThanOrEqual(58);
    expect(chrome.toolbar).toBeLessThanOrEqual(46);
    expect(chrome.chrome).toBeLessThanOrEqual(106);
    expect(Math.abs(chrome.contextY - chrome.toolbarY)).toBeLessThanOrEqual(1);
    expect(chrome.composer).toBeLessThanOrEqual(100);
    expect(chrome.captionHeight).toBeLessThanOrEqual(chrome.captionLine + 1);
    for (const button of [panel.locator('.assistant-new'), panel.locator('.assistant-delete > summary')]) {
        if (!await button.count()) continue;
        const paintedBorder = await button.evaluate(node => {
            const style = getComputedStyle(node);
            return parseFloat(style.borderTopWidth) > 0 && !/rgba\([^)]*,\s*0\)$/.test(style.borderTopColor)
                && style.borderTopColor !== 'transparent';
        });
        expect(paintedBorder).toBe(false);
        const glyph = await button.locator('svg').boundingBox();
        expect(glyph.width).toBeLessThanOrEqual(16);
        expect(glyph.height).toBeLessThanOrEqual(16);
    }
    await expect(panel.locator('.assistant-heading img')).toHaveCSS('width', '28px');
    await expect(panel.locator('.assistant-heading .assistant-mark > svg')).toHaveCSS('width', '48px');
}

for (const theme of ['light', 'dark']) for (const viewport of [
    {width: 1440, height: 900}, {width: 390, height: 844}, {width: 320, height: 480},
]) {
    test(`Chat transcript scrolls while the composer stays available (${theme}, ${viewport.width}x${viewport.height})`, async ({page}, info) => {
        const errors = [], external = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('request', request => {
            if (!['localhost', '127.0.0.1'].includes(new URL(request.url()).hostname)) external.push(request.url());
        });
        const panel = await openChat(page, info, {...viewport, theme});
        await expect(panel.locator('.assistant-history')).not.toHaveAttribute('open');
        // Read both rectangles in the same frame while the opening animation
        // may still translate the fixed panel as a whole.
        const center = await panel.locator('.assistant-empty').evaluate(node => {
            const empty = node.getBoundingClientRect();
            const viewport = node.closest('[data-assistant-transcript]').getBoundingClientRect();
            return {x: Math.abs(empty.x + empty.width / 2 - viewport.x - viewport.width / 2),
                y: Math.abs(empty.y + empty.height / 2 - viewport.y - viewport.height / 2)};
        });
        expect(center.x).toBeLessThanOrEqual(8);
        expect(center.y).toBeLessThanOrEqual(3);
        const initialComposer = panel.locator('[data-assistant-send]');
        for (const control of [panel.locator('[data-assistant-minimize]'), panel.locator('[data-assistant-close]'), panel.locator('.assistant-history > summary'),
            panel.locator('.assistant-new'), panel.locator('[data-assistant-context-link]'),
            initialComposer.locator('textarea'), initialComposer.locator('[data-assistant-settings] > summary'),
            initialComposer.locator('.assistant-composer-context label'),
            initialComposer.getByRole('button', {name: 'Send message', exact: true})]) {
            await expectMinimumTarget(control);
        }
        await expectCompactChat(panel);
        await page.screenshot({path: info.outputPath(`chat-empty-${theme}-${viewport.width}.png`)});
        const pageY = await page.evaluate(() => window.scrollY);
        await send(page, panel, 'Hello from the synthetic browser fixture.');
        await expectCompactChat(panel);
        await expect(panel.locator('.assistant-message--assistant .assistant-message-text')).toHaveCSS('font-size', '13px');
        await page.screenshot({path: info.outputPath(`chat-compact-populated-${theme}-${viewport.width}.png`)});
        await send(page, panel, '[long] A synthetic message with no financial information.');
        const transcript = panel.locator('[data-assistant-transcript]');
        await expect(transcript).toBeVisible();
        expect(await transcript.evaluate(node => node.scrollHeight)).toBeGreaterThan(await transcript.evaluate(node => node.clientHeight));
        await expect.poll(() => tailDistance(transcript)).toBeLessThanOrEqual(3);
        const composer = panel.locator('[data-assistant-send]');
        const sendButton = composer.getByRole('button', {name: 'Send message', exact: true});
        await expectInsideViewport(composer.locator('textarea'), viewport);
        await expectInsideViewport(sendButton, viewport);
        const before = await sendButton.boundingBox();
        await transcript.focus();
        await transcript.press('Control+Home');
        await expect.poll(() => transcript.evaluate(node => node.scrollTop)).toBeLessThanOrEqual(3);
        expect(await sendButton.boundingBox()).toEqual(before);
        expect(await page.evaluate(() => window.scrollY)).toBe(pageY);
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
        expect(await panel.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
        expect(await transcript.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
        // The main financial view keeps its own scroll position and dimensions;
        // only the transcript owns the chat's long response.
        await panel.getByRole('button', {name: 'Close assistant', exact: true}).focus();
        await expect(panel.getByRole('button', {name: 'Close assistant', exact: true})).toBeInViewport();
        await page.screenshot({path: info.outputPath(`chat-transcript-${theme}-${viewport.width}.png`)});
        expect(errors).toEqual([]); expect(external).toEqual([]);
    });
}

test('Chat sends on Enter, preserves Shift+Enter and ignores composition confirmation', async ({page}, info) => {
    const panel = await openChat(page, info, {width: 390, height: 844});
    const requests = [];
    page.on('request', request => {
        if (request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/messages/')) requests.push(request);
    });
    let input = panel.locator('[data-assistant-send] textarea');
    await input.fill('First line');
    await input.press('End');
    await input.press('Shift+Enter');
    await input.pressSequentially('Second line');
    await expect(input).toHaveValue('First line\nSecond line');
    expect(requests).toHaveLength(0);
    // Browser automation cannot start an operating-system IME. Its explicit
    // composition flag supplements the real Enter/Shift+Enter events above.
    const consumed = await input.evaluate(node => !node.dispatchEvent(new KeyboardEvent('keydown', {
        key: 'Enter', code: 'Enter', isComposing: true, bubbles: true, cancelable: true,
    })));
    expect(consumed).toBe(false);
    expect(requests).toHaveLength(0);
    await input.press('Enter');
    await expect(panel.locator('.assistant-message--assistant')).toHaveCount(1);
    await expect(panel.locator('[data-assistant-send]')).not.toHaveAttribute('aria-busy');
    expect(requests).toHaveLength(1);
    expect(requests[0].postData()).toMatch(/name="content"\r\n\r\nFirst line\r\nSecond line/);
    input = panel.locator('[data-assistant-send] textarea');
    await expect(input).toHaveValue('');
    await expect(input).toBeFocused();
    await input.press('Enter');
    await page.waitForTimeout(150);
    expect(requests).toHaveLength(1);
    for (const selector of ['.assistant-history', '.assistant-delete']) {
        const menu = panel.locator(selector);
        await menu.locator(':scope > summary').press('Enter');
        await expect(menu).toHaveAttribute('open');
        await menu.locator(':scope > summary').press('Escape');
        await expect(menu).not.toHaveAttribute('open');
        await expect(menu.locator(':scope > summary')).toBeFocused();
        await expect(panel).toBeVisible();
    }
    await panel.locator('.assistant-history > summary').press('Enter');
    await input.click();
    await expect(panel.locator('.assistant-history')).not.toHaveAttribute('open');
    await expect(input).toBeFocused();
});

for (const theme of ['light', 'dark']) {
    test(`Streaming follows its tail until the reader scrolls up (${theme})`, async ({page}, info) => {
        const panel = await openChat(page, info, {theme, width: 390, height: 844});
        await send(page, panel, '[long] Initial synthetic response.');
        let transcript = panel.locator('[data-assistant-transcript]');
        await panel.locator('[data-assistant-send] textarea').fill('[tail] A paced synthetic response.');
        await panel.locator('[data-assistant-send] textarea').press('Enter');
        await expect(panel.locator('.assistant-message--assistant')).toHaveCount(2);
        await expect(panel.locator('.assistant-message--assistant').last()).toContainText('paragraph 4');
        await expect.poll(() => tailDistance(transcript)).toBeLessThanOrEqual(3);
        await transcript.focus();
        await transcript.press('Control+Home');
        await expect.poll(() => transcript.evaluate(node => node.scrollTop)).toBeLessThanOrEqual(3);
        const position = await transcript.evaluate(node => node.scrollTop);
        await expect(panel.locator('.assistant-message--assistant').last()).toContainText('paragraph 12');
        expect(await transcript.evaluate(node => node.scrollTop)).toBe(position);
        await expect(panel.locator('[data-assistant-send]')).not.toHaveAttribute('aria-busy');
        transcript = panel.locator('[data-assistant-transcript]');
        expect(await transcript.evaluate(node => node.scrollTop)).toBe(position);
        await expect(panel.locator('[data-assistant-send] textarea')).toBeInViewport();
    });
}

for (const viewport of [{width: 320, height: 480}, {width: 390, height: 320}, {width: 320, height: 320}]) {
test(`Phone focus and composer stay bounded (${viewport.width}x${viewport.height})`, async ({page}, info) => {
    const panel = await openChat(page, info, viewport);
    const minimize = panel.getByRole('button', {name: 'Minimize assistant', exact: true});
    const form = panel.locator('[data-assistant-send]');
    await selectModel(panel, 'mock-mini');
    expect(await panel.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
    await expectSeparateControls(form.locator('[data-assistant-settings] > summary'), form.locator('.assistant-composer-context label'),
        form.getByRole('button', {name: 'Send message', exact: true}));
    const input = form.locator('textarea');
    const oneLine = await input.boundingBox();
    await input.fill(Array.from({length: 30}, (_, i) => `Synthetic draft line ${i}`).join('\n'));
    if (viewport.height >= 480) await expect.poll(async () => (await input.boundingBox()).height).toBeGreaterThan(oneLine.height);
    expect((await input.boundingBox()).height).toBeLessThanOrEqual(128);
    await expectMinimumTarget(input);
    await expectInsideViewport(input, viewport);
    await expectInsideViewport(form.getByRole('button', {name: 'Send message', exact: true}), viewport);
    await page.screenshot({path: info.outputPath(`chat-compose-${viewport.width}x${viewport.height}.png`)});
    await minimize.focus(); await minimize.press('Shift+Tab');
    await expect(form.getByRole('button', {name: 'Send message', exact: true})).toBeFocused();
    await form.getByRole('button', {name: 'Send message', exact: true}).press('Tab');
    await expect(minimize).toBeFocused();
    for (const control of [form.locator('[data-assistant-settings] > summary'), form.locator('input[name="include_context"]'), input]) {
        await control.focus(); await expect(control).toBeFocused(); await expect(control).toBeInViewport();
        await control.press('Tab');
        expect(await panel.evaluate(node => node.contains(document.activeElement))).toBe(true);
    }
    if (viewport.height <= 320) {
        await input.fill('[tail]\n' + await input.inputValue());
        await input.press('Enter');
        const stop = form.getByRole('button', {name: 'Stop response', exact: true});
        await expectInsideViewport(stop, viewport);
        await stop.press('Enter');
        await expect(form).not.toHaveAttribute('aria-busy');
        await expectInsideViewport(form.getByRole('button', {name: 'Send message', exact: true}), viewport);
        await page.screenshot({path: info.outputPath(`chat-stopped-${viewport.width}x${viewport.height}.png`)});
    }
    await input.press('Escape');
    await expect(panel).toBeHidden();
    await expect(page.locator('[data-assistant-minimized]').getByRole('button', {name: 'Restore assistant', exact: true})).toBeFocused();
});
}

test('A delayed completion refresh cannot discard a newly started follow-up', async ({page}, info) => {
    const panel = await openChat(page, info, {width: 390, height: 844});
    let release, requested;
    const gate = new Promise(resolve => { release = resolve; });
    const pending = new Promise(resolve => { requested = resolve; });
    await page.route(/\/assistant\/[a-f0-9-]{36}\/(?:\?.*)?$/, async route => {
        if (route.request().method() !== 'GET') return route.continue();
        requested(); await gate; await route.continue().catch(() => {});
    }, {times: 1});
    const input = panel.locator('[data-assistant-send] textarea');
    await input.fill('Synthetic response with a delayed owned refresh');
    await input.press('Enter');
    await pending;
    try {
        await expect(panel.locator('.assistant-message--assistant')).toContainText('Synthetic');
        await expect(input).toBeDisabled();
        await expect(panel.locator('[data-assistant-send] button[type="submit"]')).toBeDisabled();
    } finally { release(); }
    const next = panel.locator('[data-assistant-send] textarea');
    await expect(next).toBeEnabled();
    await expect(next).toHaveValue('');
    await expect(next).toBeFocused();
    await next.pressSequentially('A new follow-up stays here');
    await expect(next).toHaveValue('A new follow-up stays here');
});


for (const theme of ['light', 'dark']) for (const viewport of [
    {width: 1440, height: 900}, {width: 390, height: 844}, {width: 320, height: 320},
]) {
    test(`Chat settings keep supported effort, keyboard and completion state (${theme}, ${viewport.width}x${viewport.height})`, async ({page}, info) => {
        const errors = [], external = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('request', request => {
            if (!['localhost', '127.0.0.1'].includes(new URL(request.url()).hostname)) external.push(request.url());
        });
        const language = viewport.width === 390 ? 'pt-br' : 'en';
        const settingsName = language === 'pt-br' ? 'Configurações do chat' : 'Chat settings';
        const sendName = language === 'pt-br' ? 'Enviar mensagem' : 'Send message';
        const panel = await openChat(page, info, {...viewport, theme, language});
        const form = panel.locator('[data-assistant-send]');
        const settings = form.locator('[data-assistant-settings]');
        const summary = settings.locator(':scope > summary');
        const model = settings.locator('select[name="model"]');
        const effort = settings.locator('select[name="reasoning_effort"]');
        await expect(summary).toHaveAccessibleName(settingsName);
        await expect(model).toBeHidden();
        await expectSettingsGear(summary);
        const compactHeight = (await form.boundingBox()).height;
        await summary.press('Enter');
        await expect(settings).toHaveAttribute('open');
        if (viewport.width >= 1280) {
            await page.locator('main h1').first().click();
            await expect(settings).not.toHaveAttribute('open');
            await expect(panel).toBeVisible();
            await summary.press('Enter');
        }
        await expect(model).toHaveValue('mock-standard');
        await expect(effort).toHaveValue('');
        await expect(effort).toHaveAccessibleName(language === 'pt-br' ? 'Esforço de raciocínio' : 'Reasoning effort');
        await expect.poll(() => effort.locator('option:not([hidden])').evaluateAll(nodes => nodes.map(node => node.value))).toEqual(['', 'low', 'medium', 'high']);
        // Native keyboard selection remains available inside a deliberate
        // settings disclosure; Escape belongs to this menu before the sheet.
        await effort.focus(); await effort.press('End'); await effort.press('Tab');
        await expect(effort).toHaveValue('high');
        await expect(settings).not.toHaveAttribute('open');
        await expect(form.locator('input[name="include_context"]')).toBeFocused();
        await summary.press('Enter');
        await model.selectOption('mock-mini');
        await expect(effort).toHaveValue('high');
        await expect.poll(() => effort.locator('option:not([hidden])').evaluateAll(nodes => nodes.map(node => node.value))).toEqual(['', 'low', 'high']);
        await model.selectOption('mock-standard');
        await effort.selectOption('medium');
        await model.selectOption('mock-mini');
        await expect(effort).toHaveValue('');
        await expect(settings.locator('[data-assistant-settings-notice]')).toContainText(language === 'pt-br' ? 'Esforço redefinido' : 'Effort reset');
        await effort.selectOption('high');
        await expect(settings.locator('[data-assistant-settings-notice]')).toBeEmpty();
        for (const control of [model, effort]) {
            await control.focus();
            await expectMinimumTarget(control);
            await expectInsideViewport(control, viewport);
        }
        await expectSavedSettings(page, 'mock-mini', 'high');
        const savedStatus = settings.locator('[data-assistant-preferences-status]');
        await expect(savedStatus).toHaveText(await form.getAttribute('data-preferences-saved'));
        if (viewport.height >= 600) {
            // Normal windows have room for the save acknowledgement. It must
            // not be clipped by the settings popup's short-screen scroll cap.
            const popup = await settings.locator('.assistant-settings-body').boundingBox();
            const saved = await savedStatus.boundingBox();
            expect(saved.y).toBeGreaterThanOrEqual(popup.y + 1);
            expect(saved.y + saved.height).toBeLessThanOrEqual(popup.y + popup.height - 1);
        }
        await page.screenshot({path: info.outputPath(`chat-settings-${theme}-${viewport.width}x${viewport.height}.png`)});
        await effort.press('Escape');
        await expect(settings).not.toHaveAttribute('open');
        await expect(summary).toBeFocused();
        await expect(panel).toBeVisible();
        expect((await form.boundingBox()).height).toBe(compactHeight);
        await expectSeparateControls(summary, form.locator('.assistant-composer-context label'),
            form.getByRole('button', {name: sendName, exact: true}));
        await form.locator('textarea').fill('[settings] Synthetic configuration only.');
        const posted = page.waitForRequest(request => request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/messages/'));
        await form.locator('textarea').press('Enter');
        const data = (await posted).postData();
        expect(data).toMatch(/name="model"\r\n\r\nmock-mini/);
        expect(data).toMatch(/name="reasoning_effort"\r\n\r\nhigh/);
        await expect(panel.locator('.assistant-message--assistant').last()).toContainText('mock-mini; effort: high');
        await expect(panel.locator('[data-assistant-send]')).not.toHaveAttribute('aria-busy');
        const next = panel.locator('[data-assistant-settings]');
        await expect(next).not.toHaveAttribute('open');
        await expect(next.locator('select[name="model"]')).toHaveValue('mock-mini');
        await expect(next.locator('select[name="reasoning_effort"]')).toHaveValue('high');
        await expect(panel.locator('[data-assistant-send] textarea')).toBeFocused();
        await expectSavedSettings(page, 'mock-mini', 'high');
        // A new conversation reuses account settings, while Close still
        // discards private unsent text and per-message context permission.
        const previousConversation = await panel.locator('[data-conversation-id]').getAttribute('data-conversation-id');
        await panel.locator('.assistant-new').press('Enter');
        await expect(panel.locator('[data-conversation-id]')).not.toHaveAttribute('data-conversation-id', previousConversation);
        await expect(panel.locator('select[name="model"]')).toHaveValue('mock-mini');
        await expect(panel.locator('select[name="reasoning_effort"]')).toHaveValue('high');
        await panel.locator('[data-assistant-send] textarea').fill('This unsent text must not be saved with preferences');
        await panel.locator('input[name="include_context"]').focus();
        await panel.locator('input[name="include_context"]').press('Space');
        const closeName = language === 'pt-br' ? 'Fechar assistente' : 'Close assistant';
        const openName = language === 'pt-br' ? 'Abrir assistente Tuxedo' : 'Open Tuxedo assistant';
        await panel.getByRole('button', {name: closeName, exact: true}).press('Enter');
        await page.getByRole('button', {name: openName, exact: true}).press('Enter');
        await expect(panel.locator('[data-assistant-send] textarea')).toHaveValue('');
        await expect(panel.locator('input[name="include_context"]')).not.toBeChecked();
        await expect(panel.locator('select[name="model"]')).toHaveValue('mock-mini');
        await expect(panel.locator('select[name="reasoning_effort"]')).toHaveValue('high');
        await page.reload();
        await page.getByRole('button', {name: openName, exact: true}).press('Enter');
        await expect(panel.locator('select[name="model"]')).toHaveValue('mock-mini');
        await expect(panel.locator('select[name="reasoning_effort"]')).toHaveValue('high');
        await expectSettingsGear(panel.locator('[data-assistant-settings] > summary'));
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
        expect(errors).toEqual([]); expect(external).toEqual([]);
    });
}

test('The latest keyboard settings survive a delayed save and HTMX workspace navigation', async ({page}, info) => {
    const panel = await openChat(page, info);
    await expectSavedSettings(page, 'mock-standard', '');
    let release, captured;
    const gate = new Promise(resolve => { release = resolve; });
    const pending = new Promise(resolve => { captured = resolve; });
    const saves = [];
    page.on('request', request => {
        if (request.method() === 'POST' && new URL(request.url()).pathname === '/assistant/preferences/') saves.push(request);
    });
    await page.route('**/assistant/preferences/', async route => {
        // Delay delivery of an already completed local save, never a database
        // transaction, while the user makes several newer keyboard choices.
        const response = await route.fetch();
        captured();
        await gate;
        await route.fulfill({response});
    }, {times: 1});
    const settings = panel.locator('[data-assistant-settings]');
    await settings.locator(':scope > summary').press('Enter');
    const model = settings.locator('select[name="model"]');
    const effort = settings.locator('select[name="reasoning_effort"]');
    await model.focus(); await model.press('End'); await model.press('Tab');
    await pending;
    try {
        await expect(model).toHaveValue('mock-mini');
        await effort.focus(); await effort.press('End'); await effort.press('Tab');
        await settings.locator(':scope > summary').press('Enter');
        await model.focus(); await model.press('Home'); await model.press('ArrowDown'); await model.press('Tab');
        await expect(model).toHaveValue('mock-standard');
        await effort.focus(); await effort.press('Home'); await effort.press('ArrowDown'); await effort.press('ArrowDown');
        await effort.press('Tab');
        await expect(effort).toHaveValue('medium');
    } finally { release(); }
    await expectSavedSettings(page, 'mock-standard', 'medium');
    expect(saves.length).toBeGreaterThanOrEqual(2);
    await panel.getByRole('button', {name: 'Close assistant', exact: true}).press('Enter');
    // The shared shell deliberately disables HTMX's extra request headers;
    // its real XMLHttpRequest still distinguishes a boosted navigation.
    const navigated = page.waitForResponse(response => response.request().resourceType() === 'xhr'
        && new URL(response.url()).pathname === '/transactions/');
    await page.locator('[data-app-navigation="desktop"] a[href="/transactions/"]').press('Enter');
    expect((await navigated).ok()).toBe(true);
    await expect(page).toHaveURL(/\/transactions\/$/);
    await page.getByRole('button', {name: 'Open Tuxedo assistant', exact: true}).press('Enter');
    await expect(panel.locator('select[name="model"]')).toHaveValue('mock-standard');
    await expect(panel.locator('select[name="reasoning_effort"]')).toHaveValue('medium');
    await expect(panel.locator('[data-assistant-send] textarea')).toHaveValue('');
    await expect(panel.locator('input[name="include_context"]')).not.toBeChecked();
});

test('Native message submission remembers settings for a fresh conversation without JavaScript', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, baseURL: info.project.use.baseURL,
        viewport: {width: 390, height: 844}, locale: 'en'});
    try {
        const page = await context.newPage();
        await signup(page, info);
        await page.goto('/assistant/');
        const form = page.locator('[data-assistant-send]');
        await form.locator('[data-assistant-settings] > summary').press('Enter');
        const model = form.locator('select[name="model"]');
        const effort = form.locator('select[name="reasoning_effort"]');
        await model.focus(); await model.press('End'); await model.press('Tab');
        await effort.focus(); await effort.press('End'); await effort.press('Tab');
        await expect(model).toHaveValue('mock-mini');
        await expect(effort).toHaveValue('high');
        await form.locator('textarea').fill('[settings] A native synthetic preference check.');
        await form.getByRole('button', {name: 'Send message', exact: true}).click();
        await expect(page.locator('.assistant-message--assistant')).toContainText('mock-mini; effort: high');
        await page.goto('/assistant/');
        await expect(page.locator('[data-assistant-send] select[name="model"]')).toHaveValue('mock-mini');
        await expect(page.locator('[data-assistant-send] select[name="reasoning_effort"]')).toHaveValue('high');
        await expect(page.locator('[data-assistant-send] textarea')).toHaveValue('');
        // A fresh unscoped native page offers no page-data consent at all.
        await expect(page.locator('input[name="include_context"]')).toHaveCount(0);
        await page.locator('.assistant-new').press('Enter');
        await expect(page.locator('[data-assistant-send] select[name="model"]')).toHaveValue('mock-mini');
        await expect(page.locator('[data-assistant-send] select[name="reasoning_effort"]')).toHaveValue('high');
    } finally { await context.close(); }
});

test('A failed settings save can be retried without sending or discarding a chat draft', async ({page}, info) => {
    const panel = await openChat(page, info);
    await expectSavedSettings(page, 'mock-standard', '');
    const sends = [];
    page.on('request', request => {
        if (request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/messages/')) sends.push(request);
    });
    await panel.locator('[data-assistant-send] textarea').fill('A private unsent draft stays in this document');
    await page.route('**/assistant/preferences/', route => route.fulfill({status: 503,
        contentType: 'application/json', body: JSON.stringify({error: 'unavailable'})}), {times: 1});
    const settings = panel.locator('[data-assistant-settings]');
    await settings.locator(':scope > summary').press('Enter');
    const effort = settings.locator('select[name="reasoning_effort"]');
    await effort.focus(); await effort.press('End'); await effort.press('Tab');
    await effort.press('Escape');
    await expect(settings).not.toHaveAttribute('open');
    await settings.locator(':scope > summary').press('Enter');
    await expect(settings.locator('[data-assistant-preferences-status]')).toContainText('Could not save chat settings.');
    await settings.locator('[data-assistant-preferences-retry]').press('Enter');
    await expectSavedSettings(page, 'mock-standard', 'high');
    await expect(settings.locator('[data-assistant-preferences-status]')).toHaveText('Chat settings saved.');
    await expect(settings.locator('[data-assistant-preferences-retry]')).toBeHidden();
    await expect(panel.locator('[data-assistant-send] textarea')).toHaveValue('A private unsent draft stays in this document');
    await expect(panel.locator('input[name="include_context"]')).not.toBeChecked();
    expect(sends).toEqual([]);
});
