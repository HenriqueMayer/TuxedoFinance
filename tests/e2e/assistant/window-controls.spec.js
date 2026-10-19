// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

test.skip(process.env.E2E_ASSISTANT_FIXTURES !== '1', 'Use the guarded --assistant-fixtures disposable runner.');

async function post(page, path, fields = {}) {
    const source = path === '/accounts/signup/' ? path : '/assistant/';
    const response = await page.request.get(source);
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    return page.request.post(path, {form: {csrfmiddlewaretoken: token, ...fields},
        headers: {Referer: response.url()}, maxRedirects: 0});
}

async function signup(page, info, suffix = '') {
    const username = `chat-window-${info.workerIndex}-${Date.now()}${suffix}`;
    expect((await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'})).status()).toBe(302);
    return username;
}

async function configure(panel) {
    const settings = panel.locator('[data-assistant-settings]');
    await settings.locator(':scope > summary').press('Enter');
    await settings.locator('select[name="model"]').selectOption('mock-mini');
    await settings.locator('select[name="reasoning_effort"]').selectOption('high');
    await settings.locator('select[name="reasoning_effort"]').press('Escape');
    await expect(settings).not.toHaveAttribute('open');
}

async function expectTargetInViewport(control, width, height) {
    await expect(control).toBeInViewport();
    const box = await control.boundingBox();
    expect(box.width).toBeGreaterThanOrEqual(43.99);
    expect(box.height).toBeGreaterThanOrEqual(43.99);
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
    expect(box.y + box.height).toBeLessThanOrEqual(height + 1);
}

for (const theme of ['light', 'dark']) for (const width of [1440, 390]) {
    test(`Assistant tab minimizes and restores the same draft and settings (${theme}, ${width})`, async ({page}, info) => {
        const errors = [], external = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('request', request => {
            if (!['localhost', '127.0.0.1'].includes(new URL(request.url()).hostname)) external.push(request.url());
        });
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({width, height: 844});
        await signup(page, info);
        await page.goto('/transactions/create/');
        const financial = page.locator('#id_title');
        await financial.fill('Unsubmitted financial form remains intact');
        const geometry = await page.locator('main').boundingBox();
        const launcher = page.getByRole('button', {name: 'Open Tuxedo assistant', exact: true});
        await launcher.press('Enter');
        const panel = page.locator('#assistant-panel');
        const minimize = panel.getByRole('button', {name: 'Minimize assistant', exact: true});
        const close = panel.getByRole('button', {name: 'Close assistant', exact: true});
        await expect(minimize).toBeFocused();
        await expectTargetInViewport(minimize, width, 844);
        await expectTargetInViewport(close, width, 844);
        await configure(panel);
        const input = panel.locator('[data-assistant-send] textarea');
        const consent = panel.locator('input[name="include_context"]');
        await input.fill('A private unsent chat draft');
        await consent.focus(); await consent.press('Space');
        await minimize.press('Enter');
        await expect(panel).toBeHidden();
        const dock = page.locator('[data-assistant-minimized]');
        const restore = dock.getByRole('button', {name: 'Restore assistant', exact: true});
        await expect(dock).toBeVisible();
        await expect(restore).toBeFocused();
        await expectTargetInViewport(restore, width, 844);
        await expectTargetInViewport(dock.getByRole('button', {name: 'Close assistant', exact: true}), width, 844);
        if (width === 390) {
            const navigation = page.locator('[data-app-navigation="mobile"]');
            await expect(navigation).not.toHaveAttribute('inert');
            const dockBox = await dock.boundingBox(), navBox = await navigation.boundingBox();
            expect(dockBox.y + dockBox.height).toBeLessThanOrEqual(navBox.y);
        }
        expect(await page.locator('main').boundingBox()).toEqual(geometry);
        await expect(financial).toHaveValue('Unsubmitted financial form remains intact');
        await expect(page.locator('#departure-confirm')).toBeHidden();
        await page.screenshot({path: info.outputPath(`assistant-tab-minimized-${theme}-${width}.png`)});
        // Same-document minimization retains the draft in memory, but its
        // authorization proof is checked before any private content returns.
        let release, requested;
        const gate = new Promise(resolve => { release = resolve; });
        const pending = new Promise(resolve => { requested = resolve; });
        await page.route(/\/assistant\/(?:\?.*)?$/, async route => {
            if (route.request().method() !== 'GET') return route.continue();
            requested(); await gate; await route.continue().catch(() => {});
        }, {times: 1});
        await restore.press('Enter');
        await pending;
        try { await expect(input).toBeHidden(); }
        finally { release(); }
        await expect(input).toBeVisible();
        await expect(input).toHaveValue('A private unsent chat draft');
        await expect(panel.locator('select[name="model"]')).toHaveValue('mock-mini');
        await expect(panel.locator('select[name="reasoning_effort"]')).toHaveValue('high');
        await expect(panel.locator('input[name="include_context"]')).toBeChecked();
        await expect(minimize).toBeFocused();
        await page.screenshot({path: info.outputPath(`assistant-tab-restored-${theme}-${width}.png`)});
        await input.press('Escape');
        await expect(panel).toBeHidden();
        await expect(restore).toBeFocused();
        await restore.press('Enter');
        await expect(input).toHaveValue('A private unsent chat draft');
        await close.press('Enter');
        await expect(panel).toBeHidden();
        await expect(dock).toBeHidden();
        await expect(launcher).toBeFocused();
        await launcher.press('Enter');
        await expect(panel.locator('[data-assistant-send] textarea')).toHaveValue('');
        await expect(panel.locator('input[name="include_context"]')).not.toBeChecked();
        await expect(panel.locator('select[name="model"]')).toHaveValue('mock-mini');
        await expect(panel.locator('select[name="reasoning_effort"]')).toHaveValue('high');
        await close.press('Enter');
        await expect(financial).toHaveValue('Unsubmitted financial form remains intact');
        expect(errors).toEqual([]); expect(external).toEqual([]);
    });
}

test('Minimizing keeps a response running and closing cancels without deleting stored history', async ({page}, info) => {
    await page.setViewportSize({width: 390, height: 844});
    await signup(page, info);
    await page.goto('/banking/');
    const launcher = page.getByRole('button', {name: 'Open Tuxedo assistant', exact: true});
    await launcher.press('Enter');
    const panel = page.locator('#assistant-panel');
    await configure(panel);
    let cancellations = 0;
    page.on('request', request => {
        if (request.method() === 'POST' && /\/cancel\/$/.test(new URL(request.url()).pathname)) cancellations += 1;
    });
    await panel.locator('[data-assistant-send] textarea').fill('[tail] Synthetic minimized response');
    await panel.locator('[data-assistant-send] textarea').press('Enter');
    await expect(panel.locator('.assistant-message--assistant')).toContainText('paragraph 2');
    await panel.getByRole('button', {name: 'Minimize assistant', exact: true}).press('Enter');
    await expect(panel).toBeHidden();
    await expect(panel.locator('.assistant-message--assistant')).toContainText('paragraph 12');
    expect(cancellations).toBe(0);
    await page.locator('[data-assistant-minimized]').getByRole('button', {name: 'Restore assistant', exact: true}).press('Enter');
    await expect(panel).toBeVisible();
    await expect(panel.locator('.assistant-message--assistant')).toContainText('paragraph 30');
    await expect(panel.locator('[data-assistant-send]')).not.toHaveAttribute('aria-busy');
    expect(cancellations).toBe(0);
    const conversation = await panel.locator('[data-conversation-id]').getAttribute('data-conversation-id');
    await panel.locator('[data-assistant-send] textarea').fill('[tail] Synthetic response closed mid-stream');
    await panel.locator('[data-assistant-send] textarea').press('Enter');
    await expect(panel.locator('.assistant-message--assistant')).toHaveCount(2);
    await expect(panel.locator('.assistant-message--assistant').last()).toContainText('paragraph 2');
    await panel.getByRole('button', {name: 'Close assistant', exact: true}).press('Enter');
    await expect.poll(() => cancellations).toBe(1);
    await launcher.press('Enter');
    await expect(panel.locator('[data-conversation-id]')).toHaveAttribute('data-conversation-id', conversation);
    await expect(panel.locator('.assistant-message--assistant')).toHaveCount(2);
    await expect(panel.locator('.assistant-message--assistant').last()).toContainText('Partial response · Stopped');
    await expect(panel.locator('[data-assistant-send] textarea')).toHaveValue('');
});

for (const sessionChange of ['logout', 'another user', 'the same user signs in again']) {
    test(`Minimized private drafts cannot return after ${sessionChange}`, async ({page}, info) => {
        const username = await signup(page, info, '-first');
        await page.goto('/banking/');
        await page.getByRole('button', {name: 'Open Tuxedo assistant', exact: true}).press('Enter');
        const panel = page.locator('#assistant-panel');
        await expect(panel.locator('[data-assistant-send]')).toBeVisible();
        await panel.locator('[data-assistant-send] textarea').fill('Private unsent text for the former session');
        await panel.getByRole('button', {name: 'Minimize assistant', exact: true}).press('Enter');
        expect((await post(page, '/accounts/logout/')).status()).toBe(302);
        if (sessionChange === 'another user') await signup(page, info, '-second');
        if (sessionChange === 'the same user signs in again') expect((await post(page, '/accounts/login/', {
            username, password: 'Tuxedo-E2E-2026!'})).status()).toBe(302);
        let release;
        const gate = new Promise(resolve => { release = resolve; });
        await page.route(/\/assistant\/(?:\?.*)?$/, async route => {
            if (route.request().method() !== 'GET') return route.continue();
            await gate; await route.continue().catch(() => {});
        }, {times: 1});
        await page.locator('[data-assistant-minimized]').getByRole('button', {name: 'Restore assistant', exact: true}).press('Enter');
        try { await expect(panel.locator('textarea')).toBeHidden(); }
        finally { release(); }
        await expect(panel).toContainText('Your session changed. Open the assistant page to continue.');
        await expect(panel).not.toContainText('Private unsent text for the former session');
        await expect(panel.locator('[data-assistant-send]')).toHaveCount(0);
        await expect(page.locator('[data-assistant-minimized]')).toBeHidden();
    });
}

test('Touch can minimize, restore and close the labelled assistant tab above mobile navigation', async ({browser}, info) => {
    const context = await browser.newContext({baseURL: info.project.use.baseURL,
        viewport: {width: 320, height: 480}, hasTouch: true, isMobile: true, reducedMotion: 'reduce'});
    try {
        const page = await context.newPage();
        await page.addInitScript(() => localStorage.setItem('theme', 'dark'));
        await signup(page, info);
        await page.goto('/banking/');
        const launcher = page.getByRole('button', {name: 'Open Tuxedo assistant', exact: true});
        await launcher.tap();
        const panel = page.locator('#assistant-panel');
        const input = panel.locator('[data-assistant-send] textarea');
        await expect(input).toBeVisible();
        await input.fill('Touch draft stays with the minimized tab');
        await panel.getByRole('button', {name: 'Minimize assistant', exact: true}).tap();
        const dock = page.locator('[data-assistant-minimized]');
        const restore = dock.getByRole('button', {name: 'Restore assistant', exact: true});
        await expectTargetInViewport(restore, 320, 480);
        const bounds = await dock.boundingBox(), navigation = await page.locator('[data-app-navigation="mobile"]').boundingBox();
        expect(bounds.y + bounds.height).toBeLessThanOrEqual(navigation.y);
        await page.screenshot({path: info.outputPath('assistant-tab-touch-320.png')});
        await restore.tap();
        await expect(input).toHaveValue('Touch draft stays with the minimized tab');
        await panel.getByRole('button', {name: 'Minimize assistant', exact: true}).tap();
        await dock.getByRole('button', {name: 'Close assistant', exact: true}).tap();
        await expect(dock).toBeHidden();
        await launcher.tap();
        await expect(panel.locator('[data-assistant-send] textarea')).toHaveValue('');
        await page.screenshot({path: info.outputPath('assistant-window-touch-320.png')});
    } finally { await context.close(); }
});

test('A delayed restore authorization cannot replace a newer completed response', async ({page}, info) => {
    await signup(page, info);
    await page.goto('/banking/');
    await page.getByRole('button', {name: 'Open Tuxedo assistant', exact: true}).press('Enter');
    const panel = page.locator('#assistant-panel');
    await configure(panel);
    await panel.locator('[data-assistant-send] textarea').fill('[tail] Synthetic restore and completion race');
    await panel.locator('[data-assistant-send] textarea').press('Enter');
    await expect(panel.locator('.assistant-message--assistant')).toContainText('paragraph 2');
    await panel.getByRole('button', {name: 'Minimize assistant', exact: true}).press('Enter');
    let release, captured;
    const gate = new Promise(resolve => { release = resolve; });
    const capturedResponse = new Promise(resolve => { captured = resolve; });
    await page.route(/\/assistant\/[a-f0-9-]{36}\/(?:\?.*)?$/, async route => {
        if (route.request().method() !== 'GET') return route.continue();
        // Capture an authorized, incomplete server document now. Delay its
        // delivery, not the GET itself, while the actual stream finishes and
        // the normal completion GET refreshes the hidden transcript.
        const response = await route.fetch();
        const body = await response.text();
        captured(body);
        await gate;
        await route.fulfill({response, body}).catch(() => {});
    }, {times: 1});
    await page.locator('[data-assistant-minimized]').getByRole('button', {name: 'Restore assistant', exact: true}).press('Enter');
    const staleBody = await capturedResponse;
    try {
        expect(staleBody).not.toContain('paragraph 30');
        await expect(panel).toBeHidden();
        await expect(panel.locator('.assistant-message--assistant')).toContainText('paragraph 30');
        await expect(panel.locator('[data-assistant-send]')).not.toHaveAttribute('aria-busy');
        await expect(panel.locator('[data-assistant-send] textarea')).toBeEnabled();
    } finally { release(); }
    await expect(panel).toBeVisible();
    await expect(panel.locator('.assistant-message--assistant')).toContainText('paragraph 30');
    await expect(panel.locator('.assistant-partial')).toHaveCount(0);
    const form = panel.locator('[data-assistant-send]');
    await expect(form.locator('textarea')).toHaveValue('');
    await expect(form.locator('textarea')).toBeEnabled();
    await expect(form.locator('select[name="model"]')).toHaveValue('mock-mini');
    await expect(form.locator('select[name="reasoning_effort"]')).toHaveValue('high');
    await form.locator('textarea').fill('A synthetic follow-up after restoring the completed response');
    await form.locator('textarea').press('Enter');
    await expect(panel.locator('.assistant-message--assistant')).toHaveCount(2);
    await expect(panel.locator('[data-assistant-send]')).not.toHaveAttribute('aria-busy');
    await page.screenshot({path: info.outputPath('assistant-restored-completed-stream.png')});
});


test('Restoring a minimized transcript preserves an earlier reading position', async ({page}, info) => {
    await page.setViewportSize({width: 390, height: 844});
    await signup(page, info);
    await page.goto('/banking/');
    await page.getByRole('button', {name: 'Open Tuxedo assistant', exact: true}).press('Enter');
    const panel = page.locator('#assistant-panel');
    await configure(panel);
    await panel.locator('[data-assistant-send] textarea').fill('[long] Synthetic transcript position');
    await panel.locator('[data-assistant-send] textarea').press('Enter');
    await expect(panel.locator('.assistant-message--assistant')).toContainText('Paragraph 52.');
    await expect(panel.locator('[data-assistant-send]')).not.toHaveAttribute('aria-busy');
    const transcript = panel.locator('[data-assistant-transcript]');
    await transcript.focus();
    await transcript.press('Control+Home');
    await expect.poll(() => transcript.evaluate(node => node.scrollTop)).toBeLessThanOrEqual(3);
    // This regression owns restoration, not native keyboard-scroll timing.
    // Set a precise non-tail position after the real keyboard/focus check so a
    // browser's unfinished PageDown animation cannot change the captured value.
    await transcript.evaluate(node => node.scrollTo({top: 200, behavior: 'instant'}));
    await expect.poll(() => transcript.evaluate(node => node.scrollTop)).toBe(200);
    const position = await transcript.evaluate(node => node.scrollTop);
    await panel.getByRole('button', {name: 'Minimize assistant', exact: true}).press('Enter');
    await expect(panel).toBeHidden();
    await page.locator('[data-assistant-minimized]').getByRole('button', {name: 'Restore assistant', exact: true}).press('Enter');
    await expect(panel).toBeVisible();
    await expect.poll(() => transcript.evaluate(node => node.scrollTop)).toBeCloseTo(position, 0);
    expect(await transcript.evaluate(node => node.scrollHeight - node.clientHeight - node.scrollTop)).toBeGreaterThan(100);
    await page.screenshot({path: info.outputPath('assistant-restored-transcript-position.png')});
});

test('Restoring after a selected ChatGPT account change keeps fresh settings and requires context consent again', async ({page}, info) => {
    await signup(page, info);
    await page.goto('/banking/');
    await page.getByRole('button', {name: 'Open Tuxedo assistant', exact: true}).press('Enter');
    const panel = page.locator('#assistant-panel');
    await configure(panel);
    const form = panel.locator('[data-assistant-send]');
    const previousConnection = await form.locator('input[name="connection_id"]').inputValue();
    const nextConnection = 'd6626ba1-31b4-4a38-9de9-2d99014781af';
    expect(previousConnection).not.toBe(nextConnection);
    await form.locator('textarea').fill('An unsent text draft may stay with the same local user');
    await form.locator('input[name="include_context"]').focus();
    await form.locator('input[name="include_context"]').press('Space');
    await panel.getByRole('button', {name: 'Minimize assistant', exact: true}).press('Enter');
    await page.route(/\/assistant\/(?:\?.*)?$/, async route => {
        if (route.request().method() !== 'GET') return route.continue();
        const response = await route.fetch();
        // Ownership and connection isolation have real database coverage. This
        // browser boundary supplies the same authorized owner/session with a
        // different selected account and that account's fresh server defaults.
        const body = await page.evaluate(({html, connection}) => {
            const document = new DOMParser().parseFromString(html, 'text/html');
            const form = document.querySelector('[data-assistant-send]');
            form.elements.connection_id.setAttribute('value', connection);
            for (const [name, value] of [['model', 'mock-standard'], ['reasoning_effort', 'low']]) {
                for (const option of form.elements[name].options) option.toggleAttribute('selected', option.value === value);
            }
            form.elements.include_context.removeAttribute('checked');
            return document.documentElement.outerHTML;
        }, {html: await response.text(), connection: nextConnection});
        await route.fulfill({response, body});
    }, {times: 1});
    await page.locator('[data-assistant-minimized]').getByRole('button', {name: 'Restore assistant', exact: true}).press('Enter');
    await expect(panel).toBeVisible();
    await expect(panel.locator('[data-assistant-send] input[name="connection_id"]')).toHaveValue(nextConnection);
    await expect(panel.locator('[data-assistant-send] textarea')).toHaveValue('An unsent text draft may stay with the same local user');
    await expect(panel.locator('select[name="model"]')).toHaveValue('mock-standard');
    await expect(panel.locator('select[name="reasoning_effort"]')).toHaveValue('low');
    await expect(panel.locator('input[name="include_context"]')).not.toBeChecked();
});
