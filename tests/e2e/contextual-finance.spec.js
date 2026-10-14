// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { selectChoice } = require('./helpers/forms');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, { form: { csrfmiddlewaretoken: csrf, ...values },
        headers: { Referer: response.url() }, maxRedirects: 0 });
    expect(saved.status(), (await saved.text()).match(/role="alert"[^>]*>[^<]+/g)?.join(' ')).toBe(302);
}

async function seed(page, info) {
    const username = `contextual-finance-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', { username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' });
    await post(page, '/banking/create/', { name: 'Routine bank' });
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', { bank, name: 'Routine account', currency: 'BRL',
        opening_balance: '1000', opening_date: '2025-01-01', pix_enabled: 'on' });
    await post(page, '/categories/create/', { name: 'Food', transaction_type: 'EXPENSE' });
    await post(page, '/categories/create/', { name: 'Books', transaction_type: 'EXPENSE' });
    await post(page, '/categories/create/', { name: 'Salary', transaction_type: 'INCOME' });
    await page.goto('/transactions/create/');
    const account = await page.locator('#id_bank_account option').last().getAttribute('value');
    const food = await page.locator('#id_category option').filter({ hasText: /^Food$/ }).getAttribute('value');
    const books = await page.locator('#id_category option').filter({ hasText: /^Books$/ }).getAttribute('value');
    await post(page, '/banking/credit-cards/create/', { account, name: 'Confirmed card', card_type: 'PHYSICAL',
        closing_day: '20', due_day: '25', manual_settlement_from: new Date().toISOString().slice(0, 10) });
    await post(page, '/banking/credit-cards/create/', { account, name: 'Automatic card', card_type: 'PHYSICAL', closing_day: '20', due_day: '25' });
    await page.goto('/transactions/create/');
    const confirmedCard = await page.locator('#id_credit_card option').filter({ hasText: /^Confirmed card/ }).getAttribute('value');
    const automaticCard = await page.locator('#id_credit_card option').filter({ hasText: /^Automatic card/ }).getAttribute('value');
    await post(page, '/investments/products/create/', { bank, name: 'Routine portfolio', purpose: 'INVESTMENT' });
    await page.goto('/investments/assets/create/');
    const product = await page.locator('#id_opening_product option').last().getAttribute('value');
    await post(page, '/investments/assets/create/', { name: 'Routine fund', code: 'FUND', asset_class: 'LIQUIDITY',
        valuation_mode: 'MONETARY', currency: 'BRL', opening_balance: '100', opening_quantity: '0',
        opening_unit_price: '0', opening_product: product, opening_date: '2026-01-01' });
    await post(page, '/investments/assets/create/', { name: 'Routine share', code: 'SHARE', asset_class: 'EQUITY',
        valuation_mode: 'UNITS', currency: 'BRL', opening_balance: '0', opening_quantity: '2',
        opening_unit_price: '100', opening_product: product, opening_date: '2026-01-01' });
    await page.goto('/investments/create/');
    const fund = await page.locator('#id_asset option').filter({ hasText: /^Routine fund/ }).getAttribute('value');
    const share = await page.locator('#id_asset option').filter({ hasText: /^Routine share/ }).getAttribute('value');
    return { account, food, books, product, fund, share, confirmedCard, automaticCard };
}

async function fillSplit(page, data) {
    await page.locator('#id_title').fill('Routine purchase');
    await page.locator('#id_amount').fill('45.10');
    await page.locator('#id_transaction_type').focus();
    await page.keyboard.press('End');
    await page.keyboard.press('Tab');
    for (let step = 0; step < 8 && !(await page.locator('#id_split_categories').evaluate(element => element === document.activeElement)); step++) {
        await page.keyboard.press('Tab');
    }
    await expect(page.locator('#id_split_categories')).toBeFocused();
    const help = page.locator('[data-help-trigger][aria-controls="id_split_categories-help"]');
    if (await help.isVisible()) {
        const content = page.locator('#id_split_categories-help');
        await help.hover();
        await expect(content).toBeVisible();
        const bounds = await content.boundingBox();
        expect(bounds.x).toBeGreaterThanOrEqual(0);
        expect(bounds.x + bounds.width).toBeLessThanOrEqual(page.viewportSize().width);
        await page.mouse.move(1, 1);
        await expect(content).toBeHidden();
        await help.focus();
        await expect(content).toBeVisible();
        await help.press('Escape');
        await expect(content).toBeHidden();
        await help.press('Tab');
        await expect(page.locator('#id_split_categories')).toBeFocused();
    }
    await page.keyboard.press('Space');
    await selectChoice(page.locator('#id_splits-0-category'), data.food);
    await page.locator('#id_splits-0-amount').fill('15');
    await selectChoice(page.locator('#id_splits-1-category'), data.books);
    await page.locator('#id_splits-1-amount').fill('29.10');
    await page.locator('#id_payment_channel').selectOption('ACCOUNT');
    await selectChoice(page.locator('#id_bank_account'), data.account);
    await page.locator('#id_date').fill('10/01/2026');
}

for (const theme of ['light', 'dark']) {
for (const width of [390, 1440]) {
test(`contextual finance returns and split keyboard recovery (${width}, ${theme})`, async ({ page }, info) => {
    page.on('dialog', dialog => dialog.accept());
    await page.setViewportSize({ width, height: 780 });
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    const data = await seed(page, info);
    const origin = '/transactions/?q=Routine&month=2026-01';
    await page.goto(origin);
    await page.locator('main').getByRole('link', { name: 'New Transaction', exact: true }).first().press('Enter');
    await expect(page.locator('#category-split-choice')).toBeHidden();
    await expect(page.locator('#category-split-fields')).toBeHidden();
    await expect(page.getByRole('button', { name: 'Add category', exact: true })).toBeHidden();
    await fillSplit(page, data);
    await expect(page.locator('#category-fields')).toBeHidden();
    await page.getByRole('button', { name: 'Add category', exact: true }).press('Enter');
    await expect(page.locator('#id_splits-2-category')).toBeHidden();
    await expect(page.locator('#id_splits-2-category-search')).toBeVisible();
    await expect(page.locator('#id_title')).toHaveValue('Routine purchase');
    await expect(page.getByText('Transaction "Routine purchase" created.', { exact: true })).toHaveCount(0);
    await page.locator('#id_title').press('Enter');
    await expect(page.getByText('Category amounts must add up to the transaction total.', { exact: true })).toBeVisible();
    await expect(page.getByText('Transaction "Routine purchase" created.', { exact: true })).toHaveCount(0);
    await expect(page.locator('#id_splits-1-amount')).toHaveValue('29.10');
    await expect(page.locator('main input[name="next"]')).toHaveValue(origin);
    await page.locator('#id_splits-1-amount').focus();
    await page.screenshot({ path: info.outputPath(`contextual-split-error-${width}-${theme}.png`), fullPage: true });
    await page.locator('#id_splits-1-amount').fill('30.10');
    await page.locator('#id_title').press('Enter');
    expect(new URL(page.url()).pathname + new URL(page.url()).search).toBe(origin);
    await page.locator('main').getByRole('link', { name: 'Edit', exact: true }).press('Enter');
    await expect(page.locator('#id_split_categories')).toBeChecked();
    await expect(page.locator('#category-split-fields')).toBeVisible();
    await page.locator('#id_split_categories').press('Space');
    await expect(page.locator('#category-split-fields')).toBeHidden();
    await expect(page.getByRole('button', { name: 'Add category', exact: true })).toBeHidden();
    await expect(page.locator('#id_splits-0-amount')).toHaveValue('');
    await selectChoice(page.locator('#id_category'), data.food);
    await page.getByRole('link', { name: 'Cancel', exact: true }).press('Enter');
    expect(new URL(page.url()).pathname + new URL(page.url()).search).toBe(origin);

    await page.locator('main').getByRole('link', { name: 'New Transaction', exact: true }).first().press('Enter');
    await page.locator('#id_title').fill('Routine single purchase');
    await page.locator('#id_amount').fill('5');
    await page.locator('#id_transaction_type').selectOption('EXPENSE');
    await selectChoice(page.locator('#id_category'), data.food);
    await page.locator('#id_payment_channel').selectOption('ACCOUNT');
    await selectChoice(page.locator('#id_bank_account'), data.account);
    await page.locator('#id_date').fill('11/01/2026');
    await expect(page.locator('#id_split_categories')).not.toBeChecked();
    await expect(page.getByRole('button', { name: 'Add category', exact: true })).toBeHidden();
    await page.locator('#id_title').press('Enter');
    expect(new URL(page.url()).pathname + new URL(page.url()).search).toBe(origin);
    await expect(page.getByText('Routine single purchase', { exact: true })).toBeVisible();

    const portfolioOrigin = '/investments/?section=portfolio';
    await page.goto(portfolioOrigin);
    const suffix = width < 640 ? '-mobile' : '';
    const fundRow = page.locator(`#position-${data.product}-${data.fund}${suffix}`);
    await fundRow.getByRole('link', { name: 'Update', exact: true }).press('Enter');
    await page.getByRole('link', { name: 'Record yield', exact: true }).press('Enter');
    await expect(page.locator('#id_product')).toHaveValue(data.product);
    await expect(page.locator('#id_asset')).toHaveValue(data.fund);
    await expect(page.locator('#id_kind')).toHaveValue('YIELD');
    await expect(page.locator('input[name="yield_input_mode"]:checked')).toHaveCount(0);
    await page.getByRole('radio', { name: 'Enter the yield amount', exact: true }).press('Space');
    await page.locator('#id_amount').fill('5');
    await page.locator('#id_date').fill('10/01/2026');
    await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
    await expect(page).toHaveURL(new RegExp(`#position-${data.product}-${data.fund}${suffix}$`));
    await expect(fundRow).toContainText(/105[,.]00/);
    const shareRow = page.locator(`#position-${data.product}-${data.share}${suffix}`);
    await shareRow.getByRole('link', { name: 'Update', exact: true }).press('Enter');
    for (const label of ['Contribute', 'Redeem', 'Record yield', 'Update price']) {
        await expect(page.getByRole('link', { name: label, exact: true })).toBeVisible();
    }
    await page.getByRole('link', { name: 'Update price', exact: true }).press('Enter');
    await expect(page.locator('#id_asset')).toHaveValue(data.share);
    await page.locator('#id_date').fill('10/01/2026');
    await page.locator('#id_unit_price').fill('125');
    await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
    await expect(page.locator('#id_source')).toHaveAttribute('aria-invalid', 'true');
    await expect(page.locator('main input[name="next"]')).toHaveValue(`${portfolioOrigin}#position-${data.product}-${data.share}${suffix}`);
    await page.locator('#id_source').fill('Price consulted locally');
    await page.locator('#id_source').press('Tab');
    await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(new RegExp(`#position-${data.product}-${data.share}${suffix}$`));
    await expect(shareRow).toContainText('2 units');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await shareRow.getByRole('link', { name: 'Update', exact: true }).focus();
    await page.screenshot({ path: info.outputPath(`contextual-position-${width}-${theme}.png`), fullPage: true });

    await page.goto(`/transactions/create/?credit_card=${data.confirmedCard}&next=%2Fbanking%2F`);
    await expect(page.locator('#payment-channel-status')).toContainText('require confirmed payments');
    await expect(page.locator('#payment-channel-status')).toContainText('The app does not pay the bank.');
    await selectChoice(page.locator('#id_credit_card'), data.automaticCard);
    await expect(page.locator('#payment-channel-status')).toContainText('automatic accounting on the due date');
});
}
}

test('category splits and contextual price links work without JavaScript', async ({ browser }, info) => {
    const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 780 } });
    const page = await context.newPage();
    try {
        const data = await seed(page, info);
        const origin = '/transactions/?q=Routine&month=2026-01';
        await page.goto(origin);
        await page.locator('main').getByRole('link', { name: 'New Transaction', exact: true }).first().click();
        await fillSplit(page, data);
        await page.getByRole('button', { name: 'Add category', exact: true }).click();
        await expect(page.locator('#id_splits-2-category')).toBeVisible();
        await expect(page.locator('#id_title')).toHaveValue('Routine purchase');
        await expect(page.locator('main input[name="next"]')).toHaveValue(origin);
        await page.locator('#id_title').press('Enter');
        await expect(page.getByText('Category amounts must add up to the transaction total.', { exact: true })).toBeVisible();
        await expect(page.getByText('Transaction "Routine purchase" created.', { exact: true })).toHaveCount(0);
        await expect(page.locator('#id_splits-1-amount')).toHaveValue('29.10');
        await expect(page.locator('main input[name="next"]')).toHaveValue(origin);
        await page.locator('#id_splits-1-amount').fill('30.10');
        await page.locator('#id_splits-1-amount').press('Enter');
        expect(new URL(page.url()).pathname + new URL(page.url()).search).toBe(origin);
        await page.goto('/investments/?section=portfolio');
        const row = page.locator(`#position-${data.product}-${data.share}-mobile`);
        await row.getByRole('link', { name: 'Update', exact: true }).press('Enter');
        await page.getByRole('link', { name: 'Update price', exact: true }).press('Enter');
        await expect(page.locator('#id_asset')).toHaveValue(data.share);
        await page.getByRole('link', { name: 'Cancel', exact: true }).press('Enter');
        await expect(page).toHaveURL(new RegExp(`#position-${data.product}-${data.share}-mobile$`));
    } finally {
        await context.close();
    }
});
