// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

test.skip(process.env.E2E_ASSISTANT_FIXTURES !== '1', 'Use the guarded --assistant-fixtures disposable runner.');

async function post(page, path, values, source = path) {
    const response = await page.request.get(source);
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {form: {csrfmiddlewaretoken: token, ...values},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(saved.status(), await saved.text()).toBe(302);
    return saved.headers().location;
}

async function document(page, path) {
    const response = await page.request.get(path);
    expect(response.status()).toBe(200);
    return response.text();
}

async function transactionValues(page, id) {
    const html = await document(page, `/transactions/${id}/edit/`);
    return page.evaluate(source => {
        const doc = new DOMParser().parseFromString(source, 'text/html');
        return Object.fromEntries(['title', 'amount', 'date', 'notes'].map(name => {
            const field = doc.querySelector(`#id_${name}`);
            return [name, field.tagName === 'TEXTAREA' ? field.textContent : field.getAttribute('value')];
        }));
    }, html);
}

async function seed(page, info) {
    const username = `chat-consult-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    await post(page, '/banking/create/', {name: 'Synthetic consultation bank', color: '#527891'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: 'Synthetic consultation account', currency: 'BRL',
        opening_balance: '5000', opening_date: '2020-01-01', planning_enabled: 'on'});
    await post(page, '/categories/create/', {name: 'Synthetic consultation category', transaction_type: 'EXPENSE'});
    await page.goto('/transactions/create/');
    const account = await page.locator('#id_bank_account option').filter({hasText: 'Synthetic consultation account'}).getAttribute('value');
    const category = await page.locator('#id_category option').filter({hasText: 'Synthetic consultation category'}).getAttribute('value');
    await post(page, '/transactions/create/', {title: 'Synthetic consultation purchase', amount: '25.00', category,
        transaction_type: 'EXPENSE', payment_channel: 'ACCOUNT', bank_account: account, date: '2026-10-10',
        notes: 'Private seeded note must remain untouched during aggregate consultation.'});
    await post(page, '/planning/budgets/create/', {month: '2026-10', category, currency: 'BRL', amount: '200.00'});
    const html = await document(page, '/transactions/');
    const id = html.match(/href="\/transactions\/(\d+)\/edit\//)[1];
    return {id, category: Number(category)};
}

async function sendTool(page, content, marker, name, arguments_) {
    const before = await content.locator('.assistant-message--assistant').count();
    const form = content.locator('[data-assistant-send]');
    await form.locator('textarea').fill(marker + JSON.stringify({name, arguments: arguments_}));
    const submitted = page.waitForRequest(request => request.method() === 'POST' && request.url().endsWith('/messages/'));
    await form.locator('textarea').press('Enter');
    await submitted;
    await expect(content.locator('[data-assistant-send]')).not.toHaveAttribute('aria-busy');
    await expect(content.locator('.assistant-message--assistant')).toHaveCount(before + 1);
    return content.locator('.assistant-message--assistant').last();
}

async function confirm(page, content, c) {
    const card = content.locator('[data-assistant-proposal]').last();
    const id = await card.getAttribute('data-assistant-proposal');
    const button = card.getByRole('button', {name: c.confirm, exact: true});
    await button.scrollIntoViewIfNeeded();
    await button.focus();
    const bounds = await button.boundingBox();
    expect(bounds.width).toBeGreaterThanOrEqual(44);
    expect(bounds.height).toBeGreaterThanOrEqual(44);
    await button.press('Enter');
    const updated = content.locator(`[data-assistant-proposal="${id}"]`);
    await expect(updated).toContainText(c.completed);
    await expect(updated.getByRole('button')).toHaveCount(0);
    return updated;
}

for (const [width, theme, language] of [[1440, 'light', 'en'], [390, 'dark', 'pt-br']]) {
    const c = language === 'en'
        ? {open: 'Open Tuxedo assistant', account: 'Accounts', confirm: 'Confirm action', completed: 'Completed'}
        : {open: 'Abrir assistente Tuxedo', account: 'Contas', confirm: 'Confirmar ação', completed: 'Concluída'};
    test(`Cross-workspace consultation and monthly simulation keep writes reviewed (${width}, ${theme}, ${language})`, async ({page}, info) => {
        test.setTimeout(120000);
        const errors = [], external = [], nativeDialogs = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('request', request => {if (!['127.0.0.1', 'localhost'].includes(new URL(request.url()).hostname)) external.push(request.url());});
        page.on('dialog', dialog => {nativeDialogs.push(dialog.message()); return dialog.dismiss();});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({width, height: 900});
        const data = await seed(page, info);
        const original = await transactionValues(page, data.id);
        await page.context().addCookies([{name: 'django_language', value: language, url: info.project.use.baseURL}]);
        await page.goto('/banking/');
        const geometry = await page.locator('main').boundingBox();
        await page.getByRole('button', {name: c.open, exact: true}).press('Enter');
        const panel = page.locator('#assistant-panel');
        await expect(panel).toBeVisible();
        await expect(panel).toHaveAttribute('aria-modal', String(width < 1280));
        await expect(panel.locator('[data-assistant-context-link]')).toContainText(c.account);
        const settings = panel.locator('[data-assistant-settings]');
        await settings.locator(':scope > summary').press('Enter');
        const model = settings.locator('select[name="model"]');
        await model.focus(); await model.press('ArrowDown'); await model.press('Enter');
        await expect(model).toHaveValue('mock-standard');
        await settings.locator(':scope > summary').press('Escape');

        const planning = await sendTool(page, panel, '[consult]', 'read_financial_data', {
            area: 'planning', month: '2026-10', query: '', record_id: null, page: 0});
        const planResult = JSON.parse(await planning.locator('pre code').innerText());
        expect(planResult.area).toBe('planning');
        expect(planResult.items).toHaveLength(1);
        expect(planResult.items[0]).toMatchObject({limit: '200.00', actual: '25.00', forecast: '25.00', remaining: '175.00'});
        expect(planResult.saved).toBe(false);
        await expect(page).toHaveURL(/\/banking\/$/);
        await expect(panel.locator('[data-assistant-context-link]')).toContainText(c.account);
        await expect(panel.locator('[data-assistant-proposal]')).toHaveCount(0);

        const simulated = await sendTool(page, panel, '[consult]', 'simulate_month', {
            planning_month: '2026-10', gross_salary: '6000.00', clt_dependents: 0,
            clt_pension: '0.00', clt_transport: '0.00', clt_food: '0.00', clt_health: '0.00',
            clt_other: '600.00', extra_expenses: [], category_reductions: []});
        const simulation = JSON.parse(await simulated.locator('pre code').innerText());
        expect(simulation).toMatchObject({kind: 'monthly_simulation', complete: true, saved: false,
            payroll: {net: '4373.39', inss: '641.51', irrf: '385.10', deductions: '600.00'},
            forecast: {total: '25.00'}, budget: {remaining: '4348.39'}});
        expect(simulation.tax_rules.year).toBe(2026);
        await expect(panel.locator('[data-assistant-proposal]')).toHaveCount(0);
        expect(await transactionValues(page, data.id)).toEqual(original);
        await expect(page.locator('#departure-confirm')).toBeHidden();
        const cut = await sendTool(page, panel, '[consult]', 'simulate_month', {
            planning_month: '2026-10', gross_salary: '6000.00', clt_dependents: 0,
            clt_pension: '0.00', clt_transport: '0.00', clt_food: '0.00', clt_health: '0.00',
            clt_other: '600.00', extra_expenses: [],
            category_reductions: [{category_id: data.category, amount: '5.00'}]});
        const reduced = JSON.parse(await cut.locator('pre code').innerText());
        expect(reduced).toMatchObject({complete: true, saved: false,
            forecast: {total: '25.00', adjusted_total: '20.00', reduction_total: '5.00'},
            payroll: {net: '4373.39'}, budget: {remaining: '4353.39', remaining_before_reductions: '4348.39'}});
        await expect(panel.locator('[data-assistant-proposal]')).toHaveCount(0);
        expect(await transactionValues(page, data.id)).toEqual(original);
        if (width >= 1280) expect(await page.locator('main').boundingBox()).toEqual(geometry);
        expect(await panel.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
        await page.screenshot({path: info.outputPath(`consultation-simulation-${theme}-${width}.png`)});

        const conversation = await panel.locator('[data-conversation-id]').getAttribute('data-conversation-id');
        const source = simulated.locator('.assistant-references a[href="/planning/?month=2026-10"]');
        await expect(source).toBeVisible();
        await source.press('Enter');
        await expect(page).toHaveURL(/\/planning\/\?month=2026-10$/);
        await expect(page.locator('#departure-confirm')).toBeHidden();
        await page.goto(`/assistant/${conversation}/`);
        await page.reload();
        const chat = page.locator('main [data-assistant-content]');
        await expect(chat.locator('.assistant-message--assistant')).toHaveCount(3);
        await expect(chat.locator('.assistant-references a[href="/planning/?month=2026-10"]')).toHaveCount(3);
        expect(JSON.parse(await chat.locator('.assistant-message--assistant').last().locator('pre code').innerText()).budget.remaining).toBe('4353.39');

        // Queries and simulations need no confirmation. Edits and deletion keep
        // the separate, keyboard-operable human review boundary.
        await sendTool(page, chat, '[action]', 'prepare_transaction_update', {
            transaction_id: Number(data.id), changes: [{field: 'amount', value: '30.00'}]});
        await expect(chat.locator('[data-assistant-proposal]').last()).toContainText('30.00');
        expect(await transactionValues(page, data.id)).toEqual(original);
        await confirm(page, chat, c);
        const edited = await transactionValues(page, data.id);
        expect(edited).toEqual({...original, amount: '30.00'});
        await sendTool(page, chat, '[action]', 'prepare_transaction_delete', {transaction_id: Number(data.id)});
        expect(await transactionValues(page, data.id)).toEqual(edited);
        const deleted = await confirm(page, chat, c);
        await expect(deleted.locator('a')).toHaveAttribute('href', '/transactions/');
        expect((await page.request.get(`/transactions/${data.id}/edit/`)).status()).toBe(404);
        await expect(page.locator('#departure-confirm')).toBeHidden();
        await page.screenshot({path: info.outputPath(`consultation-reviewed-writes-${theme}-${width}.png`), fullPage: true});
        expect(errors).toEqual([]); expect(external).toEqual([]); expect(nativeDialogs).toEqual([]);
    });
}
