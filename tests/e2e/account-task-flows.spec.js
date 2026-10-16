// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { selectChoice } = require('./helpers/forms');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, { form: { csrfmiddlewaretoken: csrf, ...values }, headers: { Referer: response.url() }, maxRedirects: 0 });
    expect(saved.status(), (await saved.text()).match(/role="alert"[^>]*>[^<]+/g)?.join(' ')).toBe(302);
    return saved.headers().location;
}
async function seed(page, testInfo) {
    const username = `account-tasks-${testInfo.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', { username, email: `${username}@example.test`, password1: 'Task-E2E-2026!', password2: 'Task-E2E-2026!' });
    await post(page, '/banking/create/', { name: 'Task bank' });
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', { bank, name: 'Daily account', currency: 'BRL', opening_balance: '1000', opening_date: '2025-01-01', pix_enabled: 'on', planning_enabled: 'on' });
    await page.goto('/banking/credit-cards/create/');
    const account = await page.locator('#id_account option').last().getAttribute('value');
    const today = new Date().toISOString().slice(0, 10);
    await post(page, '/banking/credit-cards/create/', { account, name: 'Daily card', card_type: 'PHYSICAL', closing_day: '31', due_day: '30', manual_settlement_from: today });
    await post(page, '/categories/create/', { name: 'Meals', transaction_type: 'EXPENSE' });
    await page.goto('/transactions/create/');
    const card = await page.locator('#id_credit_card option').last().getAttribute('value');
    const category = await page.locator('#id_category option').filter({ hasText: /^Meals$/ }).getAttribute('value');
    await post(page, '/transactions/create/', { title: 'Card meal', amount: '100', category, transaction_type: 'EXPENSE', payment_channel: 'CREDIT_CARD', credit_card: card, date: today, installments: '1' });
    return { bank, account, today };
}

for (const theme of ['light', 'dark']) {
for (const width of [390, 1440]) {
test(`account tasks keep context and invoice recovery (${width}, ${theme})`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 780 });
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    const { bank, account, today } = await seed(page, testInfo);
    const origin = `/banking/${bank}/`;
    await page.goto(origin);
    const menu = page.locator('details[name="account-updates"]').first();
    const summary = menu.locator('summary');
    await summary.focus();
    await expect(menu).not.toHaveAttribute('open', '');
    await summary.press('Enter');
    await page.locator(`#account-row-${account}`).getByRole('link', { name: 'New transaction', exact: true }).focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('#id_bank_account')).toHaveValue(account);
    await page.getByRole('link', { name: 'Cancel', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/banking/${bank}/$`));
    await summary.press('Enter');
    await expect(menu.getByRole('link', { name: 'Import statement', exact: true })).toHaveCount(0);
    await expect(menu.locator('a[href*="roadmap"], a[href*="imports"]')).toHaveCount(0);
    await summary.press('Escape');
    await page.getByRole('link', { name: 'Invoices for Daily card', exact: true }).click();
    await page.getByRole('link', { name: 'View invoice', exact: true }).click();
    await expect(page.locator('#invoice-summary')).toContainText('Remaining');
    await expect(page.getByText('Record a payment already made at your bank. This application does not send a payment.', { exact: true })).toBeVisible();
    await selectChoice(page.locator('#id_account'), account);
    await page.locator('#id_amount').fill('101');
    await page.locator('#id_date').fill(today);
    await page.getByRole('button', { name: 'Confirm payment', exact: true }).focus();
    await page.keyboard.press('Enter');
    await expect(page.getByText('Payments cannot exceed the current invoice amount.', { exact: true })).toBeVisible();
    await expect(page.locator('#id_account-search')).toHaveValue(/Daily account/);
    await page.locator('#id_amount').fill('25');
    await page.getByRole('button', { name: 'Confirm payment', exact: true }).click();
    await expect(page).toHaveURL(/#invoice-summary$/);
    await expect(page.locator('#invoice-summary')).toContainText(/75[,.]00/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`invoice-task-${width}-${theme}.png`), fullPage: true });
    await page.goto('/categories/?q=Meals&type=EXPENSE');
    await page.locator('main').getByRole('link', { name: 'Edit', exact: true }).focus();
    await page.keyboard.press('Enter');
    await page.locator('#id_name').fill('');
    await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
    await expect(page.locator('#id_name')).toHaveValue('');
    await expect(page.getByRole('link', { name: 'Cancel', exact: true })).toHaveAttribute('href', '/categories/?q=Meals&type=EXPENSE');
    await page.locator('#id_name').fill('Meals');
    await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
    await expect(page).toHaveURL(/categories\/\?q=Meals&type=EXPENSE$/);
});
}
}

test('account update choices work natively on mobile without JavaScript', async ({ browser }, testInfo) => {
    const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 780 } });
    const page = await context.newPage();
    try {
        const { bank, account } = await seed(page, testInfo);
        await page.goto(`/banking/${bank}/`);
        const menu = page.locator('details[name="account-updates"]').first();
        await menu.locator('summary').press('Enter');
        await expect(menu.getByRole('link', { name: 'Import statement', exact: true })).toHaveCount(0);
        await expect(menu.locator('a[href*="roadmap"]')).toHaveCount(0);
        await page.locator(`#account-row-${account}`).getByRole('link', { name: 'New transaction', exact: true }).click();
        await expect(page.locator('#id_bank_account')).toHaveValue(account);
        await page.getByRole('link', { name: 'Cancel', exact: true }).click();
        await expect(page).toHaveURL(new RegExp(`/banking/${bank}/$`));
    } finally { await context.close(); }
});
