// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

test.skip(process.env.E2E_ASSISTANT_FIXTURES !== '1', 'Use the guarded --assistant-fixtures disposable runner.');

async function signup(page, info) {
    const response = await page.request.get('/accounts/signup/');
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const username = `stream-${info.workerIndex}-${Date.now()}`;
    const created = await page.request.post('/accounts/signup/', {form: {
        csrfmiddlewaretoken: token, username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!',
    }, headers: {Referer: response.url()}, maxRedirects: 0});
    expect(created.status(), await created.text()).toBe(302);
}

const strings = {
    en: {open: 'Open Tuxedo assistant', close: 'Close assistant', model: 'Model', settings: 'Chat settings',
        message: 'Message', send: 'Send message', stop: 'Stop response'},
    pt: {open: 'Abrir assistente Tuxedo', close: 'Fechar assistente', model: 'Modelo', settings: 'Configurações do chat',
        message: 'Mensagem', send: 'Enviar mensagem', stop: 'Interromper resposta'},
};

for (const theme of ['light', 'dark']) for (const width of [1440, 390]) {
    const language = width === 390 ? 'pt' : 'en';
    test(`Streaming preserves financial drafts, keyboard and account actions (${theme}, ${width}, ${language})`, async ({page}, info) => {
        const errors = [], external = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('request', request => { if (!['127.0.0.1', 'localhost'].includes(new URL(request.url()).hostname)) external.push(request.url()); });
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({width, height: 844});
        await signup(page, info);
        await page.context().addCookies([{name: 'django_language', value: language === 'pt' ? 'pt-br' : 'en', url: info.project.use.baseURL}]);
        await page.goto('/transactions/create/');
        const draft = page.locator('#id_title');
        await draft.fill('Synthetic financial draft stays untouched');
        const geometry = await page.locator('main').boundingBox();
        const c = strings[language];
        await page.getByRole('button', {name: c.open, exact: true}).press('Enter');
        const panel = page.locator('#assistant-panel');
        const form = panel.locator('[data-assistant-send]');
        await expect(form).toBeVisible();
        const model = form.getByLabel(`${c.model} *`, {exact: true});
        await expect(model).toHaveValue('');
        const include = form.locator('input[name="include_context"]');
        await include.focus(); await include.press('Space');
        await expect(include).toBeChecked();
        await form.getByLabel(`${c.message} *`, {exact: true}).fill('Synthetic invalid response keeps consent and draft');
        await form.getByRole('button', {name: c.send, exact: true}).press('Enter');
        await expect(model).toHaveAttribute('aria-invalid', 'true');
        await expect(model).toBeFocused();
        await expect(model).toBeInViewport();
        await expect(include).toBeChecked();
        await expect(form.getByLabel(`${c.message} *`, {exact: true})).toHaveValue('Synthetic invalid response keeps consent and draft');
        await page.screenshot({path: info.outputPath(`stream-invalid-${theme}-${width}.png`)});
        await include.focus(); await include.press('Space');
        await expect(include).not.toBeChecked();
        await form.locator('[data-assistant-settings] > summary').press('Enter');
        await model.focus(); await model.press('ArrowDown'); await model.press('Enter');
        await expect(model).toHaveValue('mock-standard');
        await expect(include).not.toBeChecked();
        await form.getByLabel(`${c.message} *`, {exact: true}).fill('Synthetic test only');
        const posted = page.waitForRequest(request => request.method() === 'POST' && request.url().endsWith('/messages/'));
        await form.getByRole('button', {name: c.send, exact: true}).press('Enter');
        expect((await posted).postData()).not.toContain('name="include_context"');
        await expect(panel.locator('.assistant-message--assistant .assistant-message-text')).toContainText('Synthetic');
        await expect(panel.locator('[data-assistant-send]')).not.toHaveAttribute('aria-busy');
        await expect(panel.getByLabel(`${c.model} *`, {exact: true})).toHaveValue('mock-standard');
        const scopedForm = panel.locator('[data-assistant-send]');
        await scopedForm.locator('input[name="include_context"]').focus();
        await scopedForm.locator('input[name="include_context"]').press('Space');
        await expect(scopedForm.locator('input[name="include_context"]')).toBeChecked();
        await scopedForm.locator('textarea').fill('Synthetic scoped follow-up');
        const optedIn = page.waitForRequest(request => request.method() === 'POST' && request.url().endsWith('/messages/'));
        await scopedForm.getByRole('button', {name: c.send, exact: true}).press('Enter');
        expect((await optedIn).postData()).toContain('name="include_context"');
        await expect(panel.locator('.assistant-message--assistant')).toHaveCount(2);
        await expect(panel.locator('[data-assistant-send]')).not.toHaveAttribute('aria-busy');
        await expect(panel.locator('input[name="include_context"]')).not.toBeChecked();
        await expect(page.locator('#departure-confirm')).toBeHidden();
        if (width >= 1280) expect(await page.locator('main').boundingBox()).toEqual(geometry);
        await page.screenshot({path: info.outputPath(`stream-${theme}-${width}.png`)});
        await panel.getByRole('button', {name: c.close, exact: true}).press('Escape');
        await expect(draft).toHaveValue('Synthetic financial draft stays untouched');
        const nav = page.locator(`[data-app-navigation="${width >= 1024 ? 'desktop' : 'mobile'}"] a[href="/banking/"]`);
        await nav.press('Enter');
        await expect(page.locator('#departure-confirm')).toBeVisible();
        await page.locator('[data-departure-leave]').press('Enter');
        await expect(page).toHaveURL(/\/banking\/$/);
        await page.goto('/assistant/connections/');
        const account = page.locator('article.surface-panel');
        await expect(account.locator('.assistant-account-actions .action-link')).toHaveCount(2);
        await account.locator('.assistant-disconnect > summary').press('Enter');
        const confirm = account.locator('.assistant-disconnect button');
        await confirm.focus(); await expect(confirm).toBeInViewport();
        const bounds = await confirm.boundingBox();
        expect(bounds.x).toBeGreaterThanOrEqual(0); expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
        await page.screenshot({path: info.outputPath(`stream-settings-${theme}-${width}.png`)});
        expect(errors).toEqual([]); expect(external).toEqual([]);
    });
}

test('Streaming validates fields, stops partial output and renders provider text safely', async ({page}, info) => {
    await signup(page, info);
    await page.goto('/assistant/');
    let form = page.locator('[data-assistant-send]');
    await form.locator('textarea').fill('Missing model');
    await form.getByRole('button', {name: 'Send message', exact: true}).press('Enter');
    await expect(page.locator('[data-assistant-send] select[name="model"]')).toHaveAttribute('aria-invalid', 'true');
    await expect(page.locator('[data-assistant-send] select[name="model"]')).toBeFocused();
    form = page.locator('[data-assistant-send]');
    await form.locator('select[name="model"]').selectOption('mock-mini');
    await form.locator('textarea').fill('[cancel]');
    await form.getByRole('button', {name: 'Send message', exact: true}).press('Enter');
    await expect(form.getByRole('button', {name: 'Stop response', exact: true})).toBeVisible();
    await expect(page.locator('.assistant-message--assistant .assistant-message-text')).not.toBeEmpty();
    await form.getByRole('button', {name: 'Stop response', exact: true}).press('Enter');
    await expect(form.locator('[data-assistant-send-status]')).toContainText('Response stopped.');
    await expect(form).not.toHaveAttribute('aria-busy');
    const conversation = await page.locator('[data-conversation-id]').getAttribute('data-conversation-id');
    await page.goto(`/assistant/${conversation}/?model=mock-mini`);
    await expect(page.locator('.assistant-message--assistant .assistant-partial')).toContainText('Partial response · Stopped');
    form = page.locator('[data-assistant-send]');
    await form.locator('textarea').fill('[html]');
    await form.getByRole('button', {name: 'Send message', exact: true}).press('Enter');
    await expect(page.locator('.assistant-message--assistant').last()).toContainText('<img');
    await expect(page.locator('.assistant-message img')).toHaveCount(0);
    await expect(page.locator('[data-assistant-send]')).not.toHaveAttribute('aria-busy');
    await expect(page).toHaveURL(new RegExp(`/assistant/${conversation}/$`));
    await expect(page.locator('[data-assistant-send] select[name="model"]')).toHaveValue('mock-mini');
    form = page.locator('[data-assistant-send]');
    await form.locator('textarea').fill('[error]');
    await form.getByRole('button', {name: 'Send message', exact: true}).press('Enter');
    await expect(form.locator('[data-assistant-send-status]')).toContainText('could not be completed');
    await expect(form.locator('textarea')).toHaveValue('[error]');
});

test('Native chat sends and preserves the explicitly selected model without JavaScript', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, baseURL: info.project.use.baseURL,
        viewport: {width: 390, height: 844}, locale: 'en'});
    const page = await context.newPage();
    await signup(page, info); await page.goto('/banking/');
    await page.getByRole('link', {name: 'Open Tuxedo assistant', exact: true}).click();
    const form = page.locator('[data-assistant-send]');
    await form.locator('[data-assistant-settings] > summary').press('Enter');
    await form.locator('select[name="model"]').selectOption('mock-mini');
    await form.locator('textarea').fill('Native synthetic question');
    const nativeSend = form.getByRole('button', {name: 'Send message', exact: true});
    await nativeSend.scrollIntoViewIfNeeded();
    const beforeSend = await nativeSend.boundingBox();
    const beforeDock = await page.locator('.app-bottom-navigation').boundingBox();
    expect(beforeSend.y + beforeSend.height).toBeLessThanOrEqual(beforeDock.y);
    await page.screenshot({path: info.outputPath('stream-native-composer-phone.png')});
    await form.getByRole('button', {name: 'Send message', exact: true}).click();
    await expect(page).toHaveURL(/\/assistant\/[a-f0-9-]{36}\/\?scope=.+/);
    expect(new URL(page.url()).searchParams.has('model')).toBe(false);
    expect(new URL(page.url()).searchParams.has('reasoning_effort')).toBe(false);
    await expect(page.locator('.assistant-message--assistant')).toContainText('Synthetic');
    await expect(page.locator('[data-assistant-send] select[name="model"]')).toHaveValue('mock-mini');
    const sendAgain = page.locator('[data-assistant-send]').getByRole('button', {name: 'Send message', exact: true});
    await sendAgain.scrollIntoViewIfNeeded();
    const afterSend = await sendAgain.boundingBox();
    const afterDock = await page.locator('.app-bottom-navigation').boundingBox();
    expect(afterSend.y + afterSend.height).toBeLessThanOrEqual(afterDock.y);
    await page.screenshot({path: info.outputPath('stream-native-phone.png')});
    await context.close();
});


test('Native settings reject an incompatible effort and recover without JavaScript', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, baseURL: info.project.use.baseURL,
        viewport: {width: 390, height: 844}, locale: 'en'});
    try {
        const page = await context.newPage();
        await signup(page, info);
        await page.goto('/assistant/');
        let form = page.locator('[data-assistant-send]');
        let settings = form.locator('[data-assistant-settings]');
        await settings.locator(':scope > summary').press('Enter');
        await settings.locator('select[name="model"]').selectOption('mock-mini');
        await settings.locator('select[name="reasoning_effort"]').selectOption('medium');
        await form.locator('textarea').fill('[settings] Native synthetic question');
        await form.getByRole('button', {name: 'Send message', exact: true}).click();
        form = page.locator('[data-assistant-send]');
        settings = form.locator('[data-assistant-settings]');
        await expect(settings).toHaveAttribute('open');
        await expect(settings.locator('select[name="reasoning_effort"]')).toHaveAttribute('aria-invalid', 'true');
        await expect(settings).toContainText('This effort is not available for the selected model.');
        await expect(form.locator('textarea')).toHaveValue('[settings] Native synthetic question');
        await expect(page.locator('.assistant-message--assistant')).toHaveCount(0);
        await settings.locator('select[name="reasoning_effort"]').selectOption('high');
        await page.screenshot({path: info.outputPath('chat-settings-native-recovery.png')});
        await form.getByRole('button', {name: 'Send message', exact: true}).click();
        await expect(page.locator('.assistant-message--assistant')).toContainText('mock-mini; effort: high');
        await expect(page.locator('[data-assistant-settings] select[name="reasoning_effort"]')).toHaveValue('high');
        await expect(page).toHaveURL(/\/assistant\/[a-f0-9-]{36}\/$/);
    } finally { await context.close(); }
});
