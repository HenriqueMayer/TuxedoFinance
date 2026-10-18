// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function post(page, path, fields = {}) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...fields},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(saved.status(), await saved.text()).toBe(302);
}

async function seed(page, info) {
    // Match the application's configured UTC calendar, including the hours
    // when São Paulo is still on the previous day. Settlement starts today.
    const today = new Date().toISOString().slice(0, 10);
    const username = `home-shortcuts-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    await post(page, '/accounts/settings/', {base_currency: 'BRL', date_format: 'DMY'});
    await post(page, '/banking/create/', {name: 'Shortcut bank', color: '#315D50'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').filter({hasText: /^Shortcut bank$/}).getAttribute('value');
    // More accounts below the shortcut prevent end-of-document clamping from
    // accidentally hiding a regression beneath the fixed workspace title bar.
    for (const name of ['A Daily', 'B Savings', 'C Reserve', 'D Additional', 'E Additional', 'F Additional']) {
        await post(page, '/banking/accounts/create/', {bank, name, currency: 'BRL',
            opening_date: '2020-01-01', opening_balance: '500',
            ...(name === 'C Reserve' ? {} : {planning_enabled: 'on'})});
    }
    await post(page, '/categories/create/', {name: 'Shortcut cost', transaction_type: 'EXPENSE'});
    await page.goto('/banking/credit-cards/create/');
    const account = await page.locator('#id_account option').filter({hasText: 'A Daily'}).getAttribute('value');
    await post(page, '/banking/credit-cards/create/', {account, name: 'Shortcut card',
        card_type: 'PHYSICAL', closing_day: '31', due_day: '28', manual_settlement_from: today});
    await page.goto('/transactions/create/');
    const category = await page.locator('#id_category option').filter({hasText: /^Shortcut cost$/}).getAttribute('value');
    const credit_card = await page.locator('#id_credit_card option').filter({hasText: /^Shortcut card/}).getAttribute('value');
    await post(page, '/transactions/create/', {title: 'Shortcut invoice source', amount: '25.00',
        transaction_type: 'EXPENSE', category, payment_channel: 'CREDIT_CARD', credit_card, date: today});
    return {bank};
}

async function accountShortcut(page, name) {
    const shortcut = page.locator('main a[href*="#account-row-"]').filter({hasText: name});
    const target = (await shortcut.getAttribute('href')).split('#')[1];
    await shortcut.press('Enter');
    await expect(page).toHaveURL(url => url.hash === `#${target}`);
    const heading = page.locator(`#${target} h3`);
    await expect(heading).toHaveText(name);
    // A shortcut must reveal its destination rather than merely change the URL.
    await expect(heading).toBeInViewport();
    await expect.poll(() => heading.evaluate(element => {
        const box = element.getBoundingClientRect();
        const visible = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
        return element === visible || element.contains(visible);
    })).toBe(true);
    return target;
}

for (const theme of ['light', 'dark']) for (const width of [1280, 390]) {
    test(`Home shortcuts preserve account, invoice and month context (${theme}, ${width})`, async ({page}, info) => {
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({width, height: 844});
        const {bank} = await seed(page, info);
        const origin = '/dashboard/?month=2026-09';
        await page.goto(origin);
        const main = page.locator('main');
        await expect(main.locator('a[href*="/ingestion/"], a[href*="/dashboard/wealth/"]')).toHaveCount(0);
        await main.getByRole('link', {name: 'New transaction', exact: true}).press('Enter');
        await expect(page.locator('main input[name="next"]')).toHaveValue(origin);
        await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);
        await expect(page.locator('#departure-confirm')).toBeHidden();

        const navigation = page.locator('[data-period-navigation]').first();
        await navigation.getByRole('link', {name: 'Previous month', exact: true}).press('Enter');
        await expect(page).toHaveURL(/month=2026-08$/);
        await navigation.getByRole('link', {name: 'Next month', exact: true}).press('Enter');
        await expect(page).toHaveURL(/month=2026-09$/);
        await expect(page.locator('#departure-confirm')).toBeHidden();

        await main.getByRole('link', {name: 'View Banking', exact: true}).press('Enter');
        await expect(page).toHaveURL(/\/banking\/$/);
        await expect(page.locator(`#bank-${bank}`)).toBeVisible();
        await page.goBack();
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);
        await accountShortcut(page, 'B Savings');
        await page.screenshot({path: info.outputPath(`home-included-account-${theme}-${width}.png`)});
        await page.goBack();
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);
        const reserve = await accountShortcut(page, 'C Reserve');
        await expect(page.locator(`#${reserve}`).locator('xpath=ancestor::details').first()).toHaveAttribute('open', '');
        await page.goBack();
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);

        await main.getByRole('link', {name: 'All invoices', exact: true}).press('Enter');
        await expect(page).toHaveURL(/\/banking\/invoices\/$/);
        await expect(page.getByRole('heading', {name: 'Shortcut card', exact: true})).toBeVisible();
        await page.goBack();
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);
        const invoice = main.locator('a[href*="/banking/invoices/"]').filter({hasText: 'Shortcut card'});
        await invoice.press('Enter');
        await expect(page.locator('main input[name="next"]')).toHaveValue(origin);
        await expect(page.locator('h1')).toContainText('Shortcut card');
        const invoiceUrl = page.url();
        await page.getByRole('link', {name: 'Card settings', exact: true}).press('Enter');
        await expect(page.locator('main input[name="next"]')).toHaveValue(new URL(invoiceUrl).pathname + new URL(invoiceUrl).search);
        await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
        await expect(page).toHaveURL(invoiceUrl);
        await page.getByRole('link', {name: 'Record payment', exact: true}).press('Enter');
        await expect(page.locator('#invoice-payment')).toBeInViewport();
        await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);
        await navigation.getByRole('link', {name: 'Back to this month', exact: true}).press('Enter');
        await expect(page).toHaveURL(/\/dashboard\/$/);
        expect(errors).toEqual([]);
    });
}

test('Home account and invoice shortcuts keep native mobile navigation', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 390, height: 844}});
    try {
        const page = await context.newPage();
        await seed(page, info);
        const origin = '/dashboard/?month=2026-09';
        await page.goto(origin);
        await accountShortcut(page, 'B Savings');
        await page.goBack();
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);
        await accountShortcut(page, 'C Reserve');
        await page.goBack();
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);
        await page.locator('main a[href*="/banking/invoices/"]').filter({hasText: 'Shortcut card'}).press('Enter');
        await expect(page.locator('main input[name="next"]')).toHaveValue(origin);
        await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);
    } finally {
        await context.close();
    }
});
