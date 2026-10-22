// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

test.skip(process.env.E2E_ASSISTANT_FIXTURES !== '1', 'Use the guarded --assistant-fixtures disposable runner.');

async function post(page, path, values, source = path) {
    const response = await page.request.get(source);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...values},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(saved.status(), await saved.text()).toBe(302);
    return saved.headers().location;
}

async function documentValues(page, path, selector, attribute) {
    const response = await page.request.get(path);
    expect(response.status()).toBe(200);
    const html = await response.text();
    return page.evaluate(({html, selector, attribute}) => [...new DOMParser().parseFromString(html, 'text/html').querySelectorAll(selector)]
        .map(node => attribute ? node.getAttribute(attribute) : node.textContent.trim()), {html, selector, attribute});
}

async function seed(page, info) {
    const username = `chat-action-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    await post(page, '/banking/create/', {name: 'Synthetic review bank', color: '#527891'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: 'Synthetic review account', currency: 'BRL',
        opening_balance: '5000', opening_date: '2020-01-01', planning_enabled: 'on'});
    for (const name of ['Synthetic original category', 'Synthetic replacement category']) {
        await post(page, '/categories/create/', {name, transaction_type: 'EXPENSE'});
    }
    await page.goto('/transactions/create/');
    const account = await page.locator('#id_bank_account option').filter({hasText: 'Synthetic review account'}).getAttribute('value');
    const category = await page.locator('#id_category option').filter({hasText: 'Synthetic original category'}).getAttribute('value');
    const replacement = await page.locator('#id_category option').filter({hasText: 'Synthetic replacement category'}).getAttribute('value');
    const today = new Date().toISOString().slice(0, 10), month = today.slice(0, 7);
    await post(page, '/transactions/create/', {title: 'Synthetic existing purchase', amount: '25', category,
        transaction_type: 'EXPENSE', payment_channel: 'ACCOUNT', bank_account: account, date: today});
    const links = await documentValues(page, '/transactions/', '#transaction-results a[href*="/edit/"]', 'href');
    const transaction = Number(links[0].match(/\/transactions\/(\d+)\/edit\//)[1]);
    return {account: Number(account), category: Number(category), replacement: Number(replacement), transaction, today, month};
}

const copy = {
    en: {open: 'Open Tuxedo assistant', confirm: 'Confirm action', discard: 'Discard', completed: 'Completed', discarded: 'Discarded',
        view: 'View saved record', minimize: 'Minimize assistant', waiting: 'Thinking…'},
    'pt-br': {open: 'Abrir assistente Tuxedo', confirm: 'Confirmar ação', discard: 'Descartar', completed: 'Concluída', discarded: 'Descartada',
        view: 'Ver registro salvo', minimize: 'Minimizar assistente', waiting: 'Pensando…'},
};

async function prepare(page, panel, name, arguments_, {failed = false} = {}) {
    const before = await panel.locator('.assistant-message--assistant').count();
    const form = panel.locator('[data-assistant-send]');
    await form.locator('textarea').fill((failed ? '[failed_action]' : '[action]') + JSON.stringify({name, arguments: arguments_}));
    await form.locator('textarea').press('Enter');
    await expect(panel.locator('[data-assistant-progress]')).toBeVisible();
    await expect(panel.locator('[data-assistant-send]')).not.toHaveAttribute('aria-busy');
    await expect(panel.locator('.assistant-message--assistant')).toHaveCount(before + 1);
    if (failed) return;
    const card = panel.locator('[data-assistant-proposal]').last();
    await expect(card).toBeVisible();
    return card;
}

async function target(locator) {
    await locator.scrollIntoViewIfNeeded();
    await expect(locator).toBeInViewport();
    const bounds = await locator.boundingBox();
    expect(bounds.width).toBeGreaterThanOrEqual(43.99);
    expect(bounds.height).toBeGreaterThanOrEqual(43.99);
}

async function confirm(page, panel, card, c) {
    const id = await card.getAttribute('data-assistant-proposal');
    const button = card.getByRole('button', {name: c.confirm, exact: true});
    await target(button); await button.focus(); await button.press('Enter');
    const updated = panel.locator(`[data-assistant-proposal="${id}"]`);
    await expect(updated).toContainText(c.completed);
    await expect(updated.getByRole('button')).toHaveCount(0);
    await expect(updated).toBeFocused();
    return updated;
}

for (const theme of ['light', 'dark']) for (const width of [1440, 390]) {
    const language = width < 768 ? 'pt-br' : 'en', c = copy[language];
    test(`Reviewed financial actions preserve drafts (${theme}, ${width}, ${language})`, async ({page}, info) => {
        test.setTimeout(120000);
        const errors = [], external = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('request', request => { if (!['127.0.0.1', 'localhost'].includes(new URL(request.url()).hostname)) external.push(request.url()); });
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({width, height: 900});
        const data = await seed(page, info);
        await page.context().addCookies([{name: 'django_language', value: language, url: info.project.use.baseURL}]);
        await page.goto('/transactions/create/');
        const financialDraft = page.locator('#id_title');
        await financialDraft.fill('Financial draft must stay untouched');
        const pageGeometry = await page.locator('main').boundingBox();
        await page.getByRole('button', {name: c.open, exact: true}).press('Enter');
        const panel = page.locator('#assistant-panel');
        await expect(panel.locator('[data-assistant-send]')).toBeVisible();
        const settings = panel.locator('[data-assistant-settings]');
        await settings.locator(':scope > summary').press('Enter');
        await settings.locator('select[name="model"]').selectOption('mock-standard');
        await settings.locator('select[name="reasoning_effort"]').selectOption('low');
        await settings.locator(':scope > summary').press('Escape');

        const transactionArgs = {title: 'Synthetic chat purchase', amount: '15.00', currency: 'BRL', date: data.today,
            transaction_type: 'EXPENSE', category_id: data.category, payment_channel: 'ACCOUNT', account_id: data.account,
            debit_card_id: null, credit_card_id: null, installments: 1, is_fixed: false, fixed_until: null, billing_override: null, notes: ''};
        const sending = panel.locator('[data-assistant-send] textarea');
        await sending.fill('[action]' + JSON.stringify({name: 'prepare_transaction', arguments: transactionArgs}));
        await sending.press('Enter');
        await expect(panel.locator('[data-assistant-progress]')).toHaveText(c.waiting);
        await page.screenshot({path: info.outputPath(`action-thinking-${theme}-${width}.png`)});
        await expect(panel.locator('[data-assistant-send]')).not.toHaveAttribute('aria-busy');
        const transactionCard = panel.locator('[data-assistant-proposal]').last();
        await expect(transactionCard).toContainText('Synthetic chat purchase');
        expect(await documentValues(page, '/transactions/', '#transaction-results li')).toHaveLength(1);
        await page.screenshot({path: info.outputPath(`action-review-${theme}-${width}.png`)});
        const replayURL = await transactionCard.locator('form').first().getAttribute('action');
        const draft = panel.locator('[data-assistant-send] textarea');
        await draft.fill('Chat draft must stay untouched');
        const completedTransaction = await confirm(page, panel, transactionCard, c);
        await expect(panel.locator('[data-assistant-send] textarea')).toHaveValue('Chat draft must stay untouched');
        await expect(panel.locator('select[name="model"]')).toHaveValue('mock-standard');
        await expect(panel.locator('select[name="reasoning_effort"]')).toHaveValue('low');
        await expect(panel.locator('input[name="include_context"]')).toHaveCount(0);
        await expect(financialDraft).toHaveValue('Financial draft must stay untouched');
        await expect(page.locator('#departure-confirm')).toBeHidden();
        expect(await documentValues(page, '/transactions/', '#transaction-results li')).toHaveLength(2);
        await post(page, replayURL, {}, await completedTransaction.locator('a').getAttribute('href'));
        expect(await documentValues(page, '/transactions/', '#transaction-results li')).toHaveLength(2);
        await target(completedTransaction.getByRole('link', {name: c.view}));
        await page.screenshot({path: info.outputPath(`action-completed-${theme}-${width}.png`)});

        const categoryCard = await prepare(page, panel, 'prepare_categorization', {transaction_id: data.transaction, category_id: data.replacement});
        expect(await documentValues(page, `/transactions/${data.transaction}/edit/`, '#id_category option[selected]', 'value')).toEqual([String(data.category)]);
        await confirm(page, panel, categoryCard, c);
        expect(await documentValues(page, `/transactions/${data.transaction}/edit/`, '#id_category option[selected]', 'value')).toEqual([String(data.replacement)]);

        const goalCard = await prepare(page, panel, 'prepare_goal', {name: 'Synthetic confirmed chat goal', target_amount: '150.00', currency: 'BRL', target_date: null});
        expect(await documentValues(page, '/planning/goals/', '#goal-results article')).toHaveLength(0);
        await page.screenshot({path: info.outputPath(`goal-review-${theme}-${width}.png`)});
        await confirm(page, panel, goalCard, c);
        expect(await documentValues(page, '/planning/goals/', '#goal-results article')).toHaveLength(1);

        const budgetCard = await prepare(page, panel, 'prepare_budget', {category_id: data.replacement, month: data.month, currency: 'BRL', amount: '120.00'});
        expect(await documentValues(page, `/planning/?month=${data.month}`, '.budget-row')).toHaveLength(0);
        await confirm(page, panel, budgetCard, c);
        expect(await documentValues(page, `/planning/?month=${data.month}`, '.budget-row')).toHaveLength(1);

        const discarded = await prepare(page, panel, 'prepare_goal', {name: 'Synthetic discarded chat goal', target_amount: '200.00', currency: 'BRL', target_date: null});
        const discardID = await discarded.getAttribute('data-assistant-proposal');
        const discard = discarded.getByRole('button', {name: c.discard, exact: true});
        await target(discard); await discard.focus(); await discard.press('Enter');
        await expect(panel.locator(`[data-assistant-proposal="${discardID}"]`)).toContainText(c.discarded);
        expect(await documentValues(page, '/planning/goals/', '#goal-results article')).toHaveLength(1);

        const beforeFailed = await panel.locator('[data-assistant-proposal]').count();
        await prepare(page, panel, 'prepare_goal', {name: 'Synthetic failed chat goal', target_amount: '200.00', currency: 'BRL', target_date: null}, {failed: true});
        await expect(panel.locator('[data-assistant-proposal]')).toHaveCount(beforeFailed);
        expect(await documentValues(page, '/planning/goals/', '#goal-results article')).toHaveLength(1);
        const conversation = await panel.locator('[data-conversation-id]').getAttribute('data-conversation-id');
        expect(await documentValues(page, `/assistant/${conversation}/`, '[data-assistant-proposal]')).toHaveLength(beforeFailed);
        expect(await panel.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
        if (width >= 1280) expect(await page.locator('main').boundingBox()).toEqual(pageGeometry);
        await panel.getByRole('button', {name: c.minimize, exact: true}).press('Enter');
        await expect(financialDraft).toHaveValue('Financial draft must stay untouched');
        const nav = page.locator(`[data-app-navigation="${width >= 1024 ? 'desktop' : 'mobile'}"] a[href="/planning/"]`);
        await nav.press('Enter'); await expect(page.locator('#departure-confirm')).toBeVisible();
        await page.locator('[data-departure-leave]').press('Enter');
        await expect(page).toHaveURL(/\/planning\/$/);
        await expect(page.locator('main > .section-nav')).toHaveCSS('margin-bottom', '24px');
        await page.screenshot({path: info.outputPath(`actions-planning-${theme}-${width}.png`), fullPage: true});
        expect(errors).toEqual([]); expect(external).toEqual([]);
    });
}

test('Native assistant confirms a reviewed proposal without JavaScript', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, baseURL: info.project.use.baseURL,
        viewport: {width: 390, height: 844}, locale: 'en'});
    try {
        const page = await context.newPage();
        const username = `native-action-${info.workerIndex}-${Date.now()}`;
        await post(page, '/accounts/signup/', {username, email: `${username}@example.test`, password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
        await page.goto('/assistant/');
        const form = page.locator('[data-assistant-send]');
        await form.locator('[data-assistant-settings] > summary').press('Enter');
        await form.locator('select[name="model"]').selectOption('mock-standard');
        await form.locator('textarea').fill('[action]' + JSON.stringify({name: 'prepare_goal', arguments: {
            name: 'Native synthetic target', target_amount: '100.00', currency: 'BRL', target_date: null}}));
        await form.getByRole('button', {name: 'Send message', exact: true}).click();
        const review = page.locator('[data-assistant-proposal]');
        await expect(review).toContainText('Native synthetic target');
        const confirm = review.getByRole('button', {name: 'Confirm action', exact: true});
        await target(confirm); await confirm.press('Enter');
        await expect(page.locator('[data-assistant-proposal]')).toContainText('Completed');
        await expect(page.locator('[data-assistant-proposal] a')).toHaveAttribute('href', /\/planning\/goals\/\d+\//);
        await page.screenshot({path: info.outputPath('native-action-completed-phone.png')});
    } finally { await context.close(); }
});
