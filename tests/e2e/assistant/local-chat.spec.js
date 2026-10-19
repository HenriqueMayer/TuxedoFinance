// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function post(page, path, fields = {}) {
    const csrfPage = path === '/accounts/logout/' || path.startsWith('/assistant/') || path.startsWith('/i18n/') ? '/assistant/' : path;
    const response = await page.request.get(csrfPage);
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    return page.request.post(path, {form: {csrfmiddlewaretoken: token, ...fields},
        headers: {Referer: response.url()}, maxRedirects: 0});
}
async function signup(page, info, suffix = '') {
    const username = `assistant-${info.workerIndex}-${Date.now()}${suffix}`;
    const response = await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    expect(response.status(), await response.text()).toBe(302);
}
const copy = {
    en: {open: 'Open Tuxedo assistant', close: 'Close assistant', new: 'New conversation',
        unavailable: 'Provider not connected', history: 'History', remove: 'Delete conversation', confirm: 'Confirm deletion'},
    pt: {open: 'Abrir assistente Tuxedo', close: 'Fechar assistente', new: 'Nova conversa',
        unavailable: 'Provedor não conectado', history: 'Histórico', remove: 'Excluir conversa', confirm: 'Confirmar exclusão'},
};
for (const theme of ['light', 'dark']) for (const width of [1440, 390]) for (const language of ['en', 'pt']) {
    test(`Local assistant preserves financial drafts (${theme}, ${width}, ${language})`, async ({page}, info) => {
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({width, height: 844});
        await signup(page, info);
        await post(page, '/i18n/setlang/', {language: language === 'pt' ? 'pt-br' : 'en', next: '/transactions/create/'});
        await page.goto('/transactions/create/');
        const title = page.locator('#id_title');
        await title.fill('Private draft that must survive chat');
        const c = copy[language];
        const launcher = page.getByRole('button', {name: c.open, exact: true});
        await launcher.focus();
        await launcher.press('Space');
        const panel = page.locator('#assistant-panel');
        await expect(panel).toBeVisible();
        await expect(panel.getByText(c.unavailable, {exact: true})).toBeVisible();
        await expect(panel.locator('textarea')).toBeDisabled();
        await expect(page.locator('#departure-confirm')).toBeHidden();
        await expect(panel).toHaveAttribute('aria-modal', width >= 1280 ? 'false' : 'true');
        if (width >= 1280) {
            await expect(page.locator('main')).not.toHaveAttribute('inert');
            const boxes = await page.evaluate(() => ({main: document.querySelector('main').getBoundingClientRect().right,
                panel: document.querySelector('#assistant-panel').getBoundingClientRect().left}));
            expect(boxes.main).toBeLessThanOrEqual(boxes.panel);
        } else {
            await expect(page.locator('main')).toHaveAttribute('inert');
            const close = panel.getByRole('button', {name: c.close, exact: true});
            await close.focus();
            await close.press('Shift+Tab');
            await expect(panel.locator('.assistant-transcript')).toBeFocused();
            const box = await panel.boundingBox();
            expect(box.x).toBeGreaterThanOrEqual(0);
            expect(box.width).toBeLessThanOrEqual(width);
        }
        await panel.getByRole('button', {name: c.new, exact: true}).press('Enter');
        await expect(panel.locator('[data-conversation-id]')).toHaveAttribute('data-conversation-id', /[a-f0-9-]{36}/);
        await expect(panel.getByRole('heading', {name: c.new, exact: true})).toBeVisible();
        const conversation = await panel.locator('[data-conversation-id]').getAttribute('data-conversation-id');
        if (width < 1280) {
            const close = panel.getByRole('button', {name: c.close, exact: true});
            await close.focus();
            await close.press('Shift+Tab');
            await expect(panel.locator('.assistant-delete > summary')).toBeFocused();
            await panel.locator('.assistant-delete > summary').press('Tab');
            await expect(close).toBeFocused();
        }
        await panel.getByRole('button', {name: c.close, exact: true}).press('Escape');
        await expect(panel).toBeHidden();
        await expect(launcher).toBeFocused();
        await expect(title).toHaveValue('Private draft that must survive chat');
        await launcher.press('Enter');
        await expect(panel.locator('[data-conversation-id]')).toHaveAttribute('data-conversation-id', conversation);
        const history = panel.locator('.assistant-history');
        if (!await history.getAttribute('open')) await history.locator('summary').press('Enter');
        await history.getByRole('link', {name: new RegExp(c.new)}).press('Enter');
        await expect(panel.locator('[data-conversation-id]')).toHaveAttribute('data-conversation-id', conversation);
        await expect(page.locator('#departure-confirm')).toBeHidden();
        await panel.locator('.assistant-delete > summary').press('Enter');
        await panel.getByRole('button', {name: c.confirm, exact: true}).press('Enter');
        await expect(panel.locator('[data-conversation-id]')).toHaveAttribute('data-conversation-id', '');
        await panel.getByRole('button', {name: c.close, exact: true}).press('Enter');
        await expect(title).toHaveValue('Private draft that must survive chat');
        // Opening/deleting chat must not rebase the edited financial form.
        const navigation = page.locator(`[data-app-navigation="${width >= 1024 ? 'desktop' : 'mobile'}"]`);
        await navigation.locator('a[href="/banking/"]').press('Enter');
        await expect(page.locator('#departure-confirm')).toBeVisible();
        await page.locator('[data-departure-stay]').press('Enter');
        await expect(title).toHaveValue('Private draft that must survive chat');
        await launcher.press('Enter');
        await expect(panel.getByText(c.unavailable, {exact: true})).toBeVisible();
        await page.screenshot({path: info.outputPath(`assistant-${theme}-${width}-${language}.png`)});
        expect(errors).toEqual([]);
    });
}

test('Assistant cancels reads, recovers failures and follows authorized HTMX navigation', async ({page}, info) => {
    await signup(page, info);
    await page.setViewportSize({width: 1440, height: 900});
    await page.goto('/dashboard/');
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    await page.route('**/assistant/**', async route => { await gate; await route.continue().catch(() => {}); }, {times: 1});
    await page.getByRole('button', {name: copy.en.open, exact: true}).click();
    const panel = page.locator('#assistant-panel');
    await expect(panel.getByRole('button', {name: 'Cancel loading', exact: true})).toBeVisible();
    await panel.getByRole('button', {name: 'Cancel loading', exact: true}).click();
    await expect(panel.getByText('Loading cancelled.', {exact: true})).toBeVisible();
    release();
    await page.route('**/assistant/**', route => route.abort(), {times: 1});
    await panel.getByRole('button', {name: copy.en.close, exact: true}).click();
    await page.getByRole('button', {name: copy.en.open, exact: true}).click();
    await expect(panel.getByRole('button', {name: 'Try again', exact: true})).toBeVisible();
    await panel.getByRole('button', {name: 'Try again', exact: true}).click();
    await expect(panel.getByText(copy.en.unavailable, {exact: true})).toBeVisible();
    await panel.getByRole('button', {name: copy.en.new, exact: true}).click();
    await expect(panel.locator('[data-conversation-id]')).toHaveAttribute('data-conversation-id', /[a-f0-9-]{36}/);
    const id = await panel.locator('[data-conversation-id]').getAttribute('data-conversation-id');
    await page.locator('[data-app-navigation="desktop"] a[href="/banking/"]').click();
    await expect(page).toHaveURL(/\/banking\/$/);
    await expect(panel.locator('[data-conversation-id]')).toHaveAttribute('data-conversation-id', id);
    await expect(panel.getByText(copy.en.unavailable, {exact: true})).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(/\/dashboard\/$/);
    await expect(panel.locator('[data-conversation-id]')).toHaveAttribute('data-conversation-id', id);
    const headers = (await page.request.get(`/assistant/${id}/`, {headers: {'X-Tuxedo-Assistant': 'panel'}})).headers();
    expect(headers['cache-control']).toContain('no-store');
});

test('Native assistant supports local history and deletion without JavaScript', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, baseURL: info.project.use.baseURL});
    const page = await context.newPage();
    await signup(page, info, '-native');
    await page.goto('/banking/');
    await page.getByRole('link', {name: copy.en.open, exact: true}).click();
    await expect(page).toHaveURL(/\/assistant\//);
    await expect(page.getByText(copy.en.unavailable, {exact: true})).toBeVisible();
    await page.getByRole('button', {name: copy.en.new, exact: true}).click();
    await expect(page).toHaveURL(/\/assistant\/[a-f0-9-]{36}\//);
    await page.locator('.assistant-delete > summary').click();
    await page.getByRole('button', {name: copy.en.confirm, exact: true}).click();
    await expect(page).toHaveURL(/\/assistant\/\?/);
    await expect(page.locator('[data-conversation-id]')).toHaveAttribute('data-conversation-id', '');
    await context.close();
});

test('Private assistant history reauthorizes after logout and account change', async ({page}, info) => {
    await signup(page, info, '-alice');
    await page.goto('/assistant/');
    const created = await post(page, '/assistant/conversations/new/', {title: 'Alice private conversation'});
    expect(created.status()).toBe(302);
    const oldURL = created.headers().location;
    await page.goto(oldURL);
    await expect(page.locator('main')).toContainText('Alice private conversation');
    const token = (await page.locator('[data-assistant-content]').getAttribute('data-assistant-scope')) || '';
    expect((await post(page, '/accounts/logout/')).status()).toBe(302);
    await signup(page, info, '-bob');
    await page.goto('/banking/');
    await page.goBack();
    await expect(page.locator('body')).not.toContainText('Alice private conversation');
    const response = await page.request.get(oldURL);
    expect(response.status()).toBe(404);
    const denied = await page.request.get(`/assistant/context/?scope=${encodeURIComponent(token)}`);
    expect(denied.status()).toBeGreaterThanOrEqual(400);
    expect(await denied.text()).not.toContain('Alice private conversation');
});

test('A stale assistant asset response does not discard an edited transaction', async ({page}, info) => {
    await signup(page, info, '-assets');
    await page.goto('/transactions/create/');
    await page.locator('#id_title').fill('Draft before asset refresh');
    await page.evaluate(() => { window.TuxedoRuntimeAssets.revision = 'old-assistant-revision'; });
    await page.getByRole('button', {name: copy.en.open, exact: true}).click();
    const panel = page.locator('#assistant-panel');
    await expect(panel.getByRole('link', {name: 'Open full page', exact: false})).toBeVisible();
    await expect(panel.locator('[data-assistant-content]')).toHaveCount(0);
    await expect(page.locator('#id_title')).toHaveValue('Draft before asset refresh');
    await panel.getByRole('link', {name: 'Open full page', exact: false}).click();
    await expect(page.locator('#departure-confirm')).toBeVisible();
    await page.locator('[data-departure-stay]').click();
    await expect(page.locator('#id_title')).toHaveValue('Draft before asset refresh');
});

test('Reopening a panel never flashes its former owner while reauthorization is pending', async ({page}, info) => {
    await signup(page, info, '-old-panel');
    const created = await post(page, '/assistant/conversations/new/', {title: 'Former owner private history'});
    expect(created.status()).toBe(302);
    await page.goto('/banking/');
    await page.getByRole('button', {name: copy.en.open, exact: true}).click();
    const panel = page.locator('#assistant-panel');
    await expect(panel.getByText('Former owner private history', {exact: true})).toBeVisible();
    await panel.getByRole('button', {name: copy.en.close, exact: true}).click();
    expect((await post(page, '/accounts/logout/')).status()).toBe(302);
    await signup(page, info, '-new-panel');
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    await page.route('**/assistant/**', async route => { await gate; await route.continue().catch(() => {}); }, {times: 1});
    await page.getByRole('button', {name: copy.en.open, exact: true}).click();
    await expect(panel.getByText('Loading conversation…', {exact: true})).toBeVisible();
    await expect(panel).not.toContainText('Former owner private history');
    release();
    await expect(panel.getByText('Your session changed. Open the assistant page to continue.', {exact: true})).toBeVisible();
    await expect(panel).not.toContainText('Former owner private history');
});

for (const theme of ['light', 'dark']) {
    test(`Assistant short phone keeps long history and expanded context inside its surface (${theme})`, async ({page}, info) => {
        await page.setViewportSize({width: 320, height: 480});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await signup(page, info, '-small');
        const longTitle = 'W'.repeat(120);
        for (const title of [longTitle, '<img src=x onerror=alert(1)>']) {
            expect((await post(page, '/assistant/conversations/new/', {title})).status()).toBe(302);
        }
        await page.goto('/banking/');
        await page.getByRole('button', {name: copy.en.open, exact: true}).click();
        const panel = page.locator('#assistant-panel');
        await expect(panel.getByText(longTitle, {exact: true})).toBeVisible();
        await expect(panel.locator('.assistant-history-list img')).toHaveCount(0);
        await panel.locator('.assistant-context-details > summary').press('Enter');
        const source = panel.locator('.assistant-sources a').first();
        await source.focus();
        await expect(source).toBeInViewport();
        await expect(panel.getByRole('button', {name: copy.en.close, exact: true})).toBeInViewport();
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
        expect(await panel.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
        await page.screenshot({path: info.outputPath(`assistant-small-${theme}.png`)});
        await source.press('Escape');
        await expect(panel).toBeHidden();
        await expect(page.getByRole('button', {name: copy.en.open, exact: true})).toBeFocused();
    });
}

test('Mobile browser Back keeps the native departure dialog usable above the assistant', async ({page}, info) => {
    await page.setViewportSize({width: 390, height: 844});
    await signup(page, info, '-back-dialog');
    // Use an ordinary workspace link: same-document HTMX traversal owns the
    // styled dialog; a full-document Back instead belongs to beforeunload.
    await page.goto('/transactions/');
    await page.getByRole('link', {name: 'New transaction', exact: true}).first().press('Enter');
    await expect(page).toHaveURL(url => url.pathname === '/transactions/create/');
    const formURL = page.url();
    await page.locator('#id_title').fill('Draft behind mobile assistant');
    await page.getByRole('button', {name: copy.en.open, exact: true}).click();
    const panel = page.locator('#assistant-panel');
    await expect(panel.getByText(copy.en.unavailable, {exact: true})).toBeVisible();
    await page.evaluate(() => history.back());
    const departure = page.locator('#departure-confirm');
    await expect(departure).toBeVisible();
    await expect(departure).not.toHaveAttribute('inert');
    await expect(page.locator('[data-departure-stay]')).toBeFocused();
    await page.locator('[data-departure-stay]').press('Enter');
    await expect(departure).toBeHidden();
    await expect(page).toHaveURL(formURL);
    await expect(panel).toBeVisible();
    await panel.getByRole('button', {name: copy.en.close, exact: true}).press('Enter');
    await expect(page.locator('#id_title')).toHaveValue('Draft behind mobile assistant');
});

test('Touch assistant preserves its conversation and clears the bottom navigation', async ({browser}, info) => {
    const context = await browser.newContext({baseURL: info.project.use.baseURL,
        viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true});
    try {
        const page = await context.newPage();
        await signup(page, info, '-touch');
        await page.goto('/banking/');
        const launcher = page.getByRole('button', {name: copy.en.open, exact: true});
        const navigation = page.locator('[data-app-navigation="mobile"]');
        const launchBox = await launcher.boundingBox(), navBox = await navigation.boundingBox();
        expect(launchBox.y + launchBox.height).toBeLessThanOrEqual(navBox.y);
        await launcher.tap();
        const panel = page.locator('#assistant-panel');
        await expect(panel.getByText(copy.en.unavailable, {exact: true})).toBeVisible();
        await panel.getByRole('button', {name: copy.en.new, exact: true}).tap();
        await expect(panel.locator('[data-conversation-id]')).toHaveAttribute('data-conversation-id', /[a-f0-9-]{36}/);
        const id = await panel.locator('[data-conversation-id]').getAttribute('data-conversation-id');
        await panel.getByRole('button', {name: copy.en.close, exact: true}).tap();
        await expect(panel).toBeHidden();
        await launcher.tap();
        await expect(panel.locator('[data-conversation-id]')).toHaveAttribute('data-conversation-id', id);
        await page.screenshot({path: info.outputPath('assistant-touch.png')});
        await panel.getByRole('button', {name: copy.en.close, exact: true}).tap();
        await expect(navigation).not.toHaveAttribute('inert');
    } finally {
        await context.close();
    }
});
