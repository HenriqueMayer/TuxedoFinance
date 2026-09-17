// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { selectChoice } = require('./helpers/forms');

async function post(page, path, fields) {
    const response = await page.request.get(path);
    const html = await response.text();
    const csrf = html.match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {
        form: { csrfmiddlewaretoken: csrf, ...fields }, headers: { Referer: response.url() }, maxRedirects: 0,
    });
    expect(saved.status(), await saved.text()).toBe(302);
}
async function fixture(page, testInfo) {
    const username = `forms-${testInfo.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', { username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' });
    await post(page, '/banking/create/', { name: 'Keyboard bank' });
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', { bank, name: 'Keyboard account', currency: 'BRL', opening_balance: '1000', pix_enabled: 'on' });
    await page.goto('/banking/credit-cards/create/');
    const account = await page.locator('#id_account option').last().getAttribute('value');
    for (const name of ['Keyboard card A', 'Keyboard card B']) {
        await post(page, '/banking/credit-cards/create/', { account, name, card_type: 'PHYSICAL', closing_day: '20', due_day: '28' });
    }
    for (const name of ['Aplicativo Comida', 'Aplicativo Transporte']) {
        await post(page, '/categories/create/', { name, transaction_type: 'EXPENSE' });
    }
    await post(page, '/categories/create/', { name: 'Pagamento', transaction_type: 'INCOME' });
    await page.goto('/transactions/create/');
    return { bank, account };
}
async function tabTo(page, locator) {
    for (let i = 0; i < 80; i++) {
        if (await locator.evaluate(element => element === document.activeElement)) return;
        await page.keyboard.press('Tab');
    }
    throw new Error('Control not reachable using Tab');
}

test('category keyboard choice has visible active state, cancellation and no implicit submit', async ({ page }, testInfo) => {
    await fixture(page, testInfo);
    await expect(page.locator('#category-fields')).toBeHidden();
    await page.getByLabel('Transaction type').selectOption('EXPENSE');
    const search = page.locator('#category-search');
    const options = search.locator('..').getByRole('option');
    await search.fill('aplicati');
    await expect(options).toHaveCount(2);
    await search.press('ArrowDown');
    await expect(options.nth(0)).toHaveAttribute('aria-selected', 'true');
    const inactiveColor = await options.nth(1).evaluate(el => getComputedStyle(el).backgroundColor);
    expect(await options.nth(0).evaluate(el => getComputedStyle(el).backgroundColor)).not.toBe(inactiveColor);
    await search.press('ArrowDown');
    await expect(options.nth(1)).toHaveAttribute('aria-selected', 'true');
    await expect(search).toBeFocused();
    await page.screenshot({ path: testInfo.outputPath('category-keyboard-light.png'), fullPage: true });
    await page.evaluate(() => document.documentElement.classList.add('dark'));
    await expect(options.nth(1)).toHaveCSS('background-color', 'rgb(250, 248, 243)');
    await page.screenshot({ path: testInfo.outputPath('category-keyboard-dark.png'), fullPage: true });
    await search.press('Enter');
    await expect(search).toHaveValue('Aplicativo Transporte');
    const selected = await page.locator('#id_category').inputValue();
    await search.fill('Comida');
    await expect(options).toHaveCount(1);
    await search.press('Enter');
    await expect(page.locator('#id_category')).toHaveValue(selected);
    await expect(page).toHaveURL(/transactions\/create/);
    await search.press('Tab');
    await expect(search).toHaveValue('Aplicativo Transporte');
    await search.focus();
    await search.fill('missing-category');
    await expect(page.getByText('No matching options', { exact: true })).toBeVisible();
    await search.press('Enter');
    await search.press('Escape');
    await expect(search).toHaveValue('Aplicativo Transporte');
    await search.press('ArrowUp');
    await expect(search).toHaveAttribute('aria-expanded', 'true');
    await search.press('Escape');
    await search.locator('..').getByRole('button').click();
    await expect(page.locator('#id_category')).toHaveValue('');
    await selectChoice(search, { label: 'Aplicativo Comida' });
    await page.getByLabel('Transaction type').selectOption('INCOME');
    await expect(search).toHaveValue('');
    await search.fill('aplicati');
    await expect(options).toHaveCount(0);
});

for (const viewport of [
    { name: 'desktop light', width: 1280, height: 720, dark: false },
    { name: 'desktop dark', width: 1280, height: 720, dark: true },
    { name: 'mobile short viewport', width: 390, height: 500, dark: false },
]) {
    test(`credit choices scroll into view without moving focus: ${viewport.name}`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        await page.emulateMedia({ reducedMotion: 'reduce' });
        const { account } = await fixture(page, testInfo);
        for (const suffix of ['C', 'D', 'E', 'F', 'G', 'H']) {
            await post(page, '/banking/credit-cards/create/', { account, name: `Keyboard card ${suffix}`,
                card_type: 'PHYSICAL', closing_day: '20', due_day: '28' });
        }
        await page.reload();
        await page.evaluate(dark => document.documentElement.classList.toggle('dark', dark), viewport.dark);
        await page.getByLabel('Transaction type').selectOption('EXPENSE');
        await selectChoice(page.locator('#category-search'), { label: 'Aplicativo Comida' });
        const channel = page.getByLabel('Payment channel');
        await channel.focus();
        // Begin with the controlling field at the bottom, as in a long form.
        await channel.evaluate(element => window.scrollBy(0,
            element.getBoundingClientRect().bottom - window.innerHeight + 24));
        await page.keyboard.press('c');
        await page.keyboard.press('Tab');
        const search = page.locator('#id_credit_card-search');
        const list = page.locator('#id_credit_card-search-results');
        await expect(search).toBeFocused();
        await expect(list.getByRole('option')).toHaveCount(8);
        const fullyVisible = async () => search.evaluate(input => {
            const results = document.getElementById(input.getAttribute('aria-controls'));
            return input.getBoundingClientRect().top >= document.querySelector('header').getBoundingClientRect().bottom
                && results.getBoundingClientRect().bottom <= window.innerHeight;
        });
        await expect.poll(fullyVisible).toBe(true);
        await page.keyboard.press('Escape');
        await search.evaluate(element => window.scrollBy(0,
            element.getBoundingClientRect().bottom - window.innerHeight + 24));
        await page.keyboard.press('ArrowDown');
        await expect.poll(fullyVisible).toBe(true);
        const scrollY = await page.evaluate(() => window.scrollY);
        for (let i = 1; i < 8; i++) await page.keyboard.press('ArrowDown');
        const last = list.getByRole('option').last();
        await expect(last).toHaveAttribute('aria-selected', 'true');
        await expect(last).toBeInViewport({ ratio: 1 });
        expect(await list.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
        expect(await page.evaluate(() => window.scrollY)).toBeCloseTo(scrollY, 0);
        await expect(search).toBeFocused();
        await page.screenshot({ path: testInfo.outputPath('credit-choices-viewport.png') });
        if (viewport.width < 500) {
            await page.setViewportSize({ width: viewport.width, height: 360 });
            await expect.poll(fullyVisible).toBe(true);
            await expect(last).toBeInViewport({ ratio: 1 });
            await expect(search).toBeFocused();
        }
        await page.keyboard.press('Escape');
        await page.keyboard.press('ArrowDown');
        await expect.poll(fullyVisible).toBe(true);
        await page.keyboard.press('Enter');
        await expect(search).toHaveValue(/Keyboard card A/);
        await expect(page.getByLabel('Installments')).toBeVisible();
        await expect(search).toBeFocused();

        await page.keyboard.type('no-matching-card');
        await expect(list.getByRole('status')).toHaveText('No matching options');
        await expect.poll(fullyVisible).toBe(true);
        await page.keyboard.press('Tab');
        await expect(search).toHaveValue(/Keyboard card A/);
        await expect(list).toBeHidden();
    });
}

test('a recurring credit transaction can be completed with keyboard only', async ({ page }, testInfo) => {
    await fixture(page, testInfo);
    await tabTo(page, page.locator('#id_title'));
    await page.keyboard.type('Keyboard recurring');
    await page.keyboard.press('Tab');
    await page.keyboard.type('25');
    await page.keyboard.press('Tab');
    await page.keyboard.press('e');
    await page.keyboard.press('Tab');
    await expect(page.locator('#category-search')).toBeFocused();
    await page.keyboard.type('aplicati');
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter');
    await tabTo(page, page.getByLabel('Payment channel'));
    await page.keyboard.press('c');
    await page.keyboard.press('Tab');
    await expect(page.locator('#id_credit_card-search')).toBeFocused();
    await expect(page.getByLabel('Installments')).toBeHidden();
    await page.keyboard.type('Keyboard card A');
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter');
    await expect(page.getByLabel('Installments')).toBeVisible();
    await tabTo(page, page.getByLabel('Transaction date'));
    await page.keyboard.type('07/09/2026');
    const advanced = page.locator('summary').filter({ hasText: 'Advanced options' });
    await tabTo(page, advanced);
    await page.keyboard.press('Enter');
    await page.keyboard.press('Tab');
    await expect(page.getByLabel('Fixed / recurring transaction')).toBeFocused();
    await expect(page.getByLabel('Repeat until')).toBeHidden();
    await page.keyboard.press('Space');
    await page.keyboard.press('Tab');
    await expect(page.getByLabel('Repeat until')).toBeFocused();
    await page.keyboard.type('07/12/2026');
    await tabTo(page, page.getByLabel('Notes'));
    await page.keyboard.type('Entirely by keyboard');
    await tabTo(page, page.getByRole('button', { name: 'Save', exact: true }));
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/transactions\/$/);
    await expect(page.getByText('Keyboard recurring', { exact: true })).toBeVisible();
    await page.getByRole('link', { name: /Edit/ }).first().click();
    await expect(page.getByLabel('Installments')).toBeVisible();
    await expect(page.getByLabel('Repeat until')).toHaveValue('07/12/2026');
});

test('multi-select search keeps checked values and keyboard focus while filtering', async ({ page }, testInfo) => {
    await fixture(page, testInfo);
    await page.goto('/banking/loyalty/create/');
    const search = page.locator('#id_cards-search');
    await search.fill('card A');
    await search.press('Tab');
    const first = page.getByRole('checkbox', { name: 'Keyboard card A' });
    await expect(first).toBeFocused();
    await page.keyboard.press('Space');
    await expect(first).toBeChecked();
    await expect(first).toBeFocused();
    await search.fill('card B');
    await search.press('Tab');
    await page.keyboard.press('Space');
    await search.fill('');
    await expect(page.getByRole('checkbox', { name: 'Keyboard card A' })).toBeChecked();
    await expect(page.getByRole('checkbox', { name: 'Keyboard card B' })).toBeChecked();
    await page.locator('#id_name').fill('Keyboard points');
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page).not.toHaveURL(/loyalty\/create/);
});

test('conditional branches preserve server errors, clear inactive values and skip hidden controls', async ({ page }, testInfo) => {
    await fixture(page, testInfo);
    await page.locator('#id_title').fill('Invalid payment');
    await page.locator('#id_amount').fill('50');
    await page.getByLabel('Transaction type').selectOption('EXPENSE');
    await selectChoice(page.locator('#category-search'), { label: 'Aplicativo Comida' });
    await page.getByLabel('Payment channel').selectOption('CREDIT_CARD');
    await selectChoice(page.locator('#id_credit_card-search'), { label: 'Keyboard card A - Keyboard bank > Keyboard account (BRL)' });
    await page.getByLabel('Installments').fill('0');
    await page.getByLabel('Transaction date').fill('07/09/2026');
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.locator('#id_installments-error-1')).toBeVisible();
    await page.getByLabel('Payment channel').selectOption('PIX');
    await expect(page.locator('#credit-card-fields')).toBeHidden();
    await expect(page.locator('#id_installments')).toHaveValue('1');
    await expect(page.locator('#id_installments-error-1')).toHaveCount(0);
    await page.getByLabel('Payment channel').focus();
    await page.keyboard.press('Tab');
    await expect(page.locator('#id_bank_account-search')).toBeFocused();
    await expect(page.locator('#id_credit_card')).toHaveValue('');
});

test('IOF, loyalty purchases and transport voucher wait for their controlling choices', async ({ page }, testInfo) => {
    const { account } = await fixture(page, testInfo);
    await page.goto('/banking/loyalty-entries/create/');
    await page.getByLabel('Kind').selectOption('PURCHASE');
    await expect(page.getByLabel('Amount paid')).toBeHidden();
    await selectChoice(page.locator('#id_funding_account-search'), account);
    await expect(page.getByLabel('Amount paid')).toBeVisible();
    await page.getByLabel('Amount paid').fill('25');
    await page.getByLabel('Kind').selectOption('ADJUSTMENT');
    await expect(page.getByLabel('Amount paid')).toBeHidden();
    await expect(page.locator('#id_cash_amount')).toHaveValue('');
    await page.goto('/banking/rewards/redeem/');
    await expect(page.locator('#id_iof_account-search')).toBeHidden();
    await page.getByLabel('Iof amount').fill('1');
    await selectChoice(page.locator('#id_iof_account-search'), account);
    await page.getByLabel('Iof amount').fill('0');
    await expect(page.locator('#id_iof_account-search')).toBeHidden();
    await expect(page.locator('#id_iof_account')).toHaveValue('');
    await page.goto('/sandbox/');
    await expect(page.getByLabel('Calculate CLT deductions automatically', { exact: true })).not.toBeChecked();
    await page.getByLabel('Calculate CLT deductions automatically', { exact: true }).check();
    await page.getByText('Optional CLT details', { exact: true }).press('Space');
    await expect(page.getByLabel('Actual monthly transport cost', { exact: true })).toBeHidden();
    await page.getByLabel('Receive transport voucher', { exact: true }).check();
    await page.getByLabel('Actual monthly transport cost', { exact: true }).fill('200');
    await page.getByLabel('Receive transport voucher', { exact: true }).uncheck();
    await expect(page.locator('#id_vt_cost')).toHaveValue('');
    await expect(page.getByLabel('Actual monthly transport cost', { exact: true })).toBeHidden();
});

test('pickers initialize once after HTMX navigation and keep native options scoped', async ({ page }, testInfo) => {
    await fixture(page, testInfo);
    await page.goto('/categories/');
    await page.getByRole('link', { name: 'New Category', exact: true }).click();
    await expect(page.locator('#parent-category-search')).toHaveCount(1);
    await page.evaluate(() => {
        document.body.dispatchEvent(new Event('htmx:load', { bubbles: true }));
        document.body.dispatchEvent(new Event('htmx:load', { bubbles: true }));
        window.selectionChanges = 0;
        document.querySelector('#id_parent_category').addEventListener('change', () => window.selectionChanges++);
    });
    await selectChoice(page.locator('#parent-category-search'), { label: 'Aplicativo Comida' });
    expect(await page.evaluate(() => window.selectionChanges)).toBe(1);
    await expect(page.locator('#parent-category-search')).toHaveCount(1);
    await page.getByRole('link', { name: 'Cancel', exact: true }).click();
    await page.goBack();
    await expect(page.locator('#parent-category-search')).toHaveCount(1);
    await selectChoice(page.locator('#parent-category-search'), { label: 'Aplicativo Transporte' });
    await expect(page.getByRole('combobox', { name: 'Parent category', exact: true })).toHaveValue('Aplicativo Transporte');
});

test('native forms and conditional fields remain usable without JavaScript', async ({ browser }, testInfo) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    try {
        const { account } = await fixture(page, testInfo);
        await expect(page.locator('#id_category')).toBeVisible();
        await expect(page.getByLabel('Installments')).toBeVisible();
        await page.locator('#id_title').fill('Native transaction');
        await page.locator('#id_amount').fill('10');
        await page.getByLabel('Transaction type').selectOption('EXPENSE');
        await page.getByLabel('Category', { exact: false }).selectOption({ label: 'Aplicativo Comida' });
        await page.getByLabel('Payment channel').selectOption('ACCOUNT');
        await page.locator('#id_bank_account').selectOption(account);
        await page.getByLabel('Transaction date').fill('07/09/2026');
        await page.getByRole('button', { name: 'Save', exact: true }).click();
        await expect(page).toHaveURL(/transactions\/$/);
        await page.goto('/sandbox/');
        await expect(page.locator('[data-manual-options]')).toBeVisible();
        await expect(page.locator('[data-clt-options]')).toBeVisible();
        await page.getByText('Optional CLT details', { exact: true }).press('Enter');
        await expect(page.getByLabel('Actual monthly transport cost', { exact: true })).toBeVisible();
    } finally { await context.close(); }
});

test('investment choices wait for asset, operation and source and clear abandoned branches', async ({ page }, testInfo) => {
    const { bank, account } = await fixture(page, testInfo);
    await post(page, '/investments/products/create/', { bank, name: 'Portfolio' });
    await page.goto('/investments/assets/create/');
    await expect(page.getByLabel('How this asset is valued')).toHaveValue('');
    await expect(page.locator('#monetary-opening-fields')).toBeHidden();
    await expect(page.locator('#unit-opening-fields')).toBeHidden();
    await page.getByLabel('How this asset is valued').selectOption('MONETARY');
    await expect(page.locator('#monetary-opening-fields')).toBeVisible();
    await page.locator('#id_opening_balance').fill('20');
    await expect(page.locator('#opening-product-fields')).toBeVisible();
    await selectChoice(page.locator('#id_opening_product-search'), { label: 'Keyboard bank - Portfolio' });
    await page.getByLabel('How this asset is valued').selectOption('UNITS');
    await expect(page.locator('#id_opening_balance')).toHaveValue('0');
    await expect(page.locator('#id_opening_product')).toHaveValue('');
    await expect(page.locator('#opening-product-fields')).toBeHidden();
    for (const [name, code, valuation_mode] of [['Cash pot', 'POT', 'MONETARY'], ['Shares', 'STK', 'UNITS']]) {
        await post(page, '/investments/assets/create/', { name, code, valuation_mode, asset_class: 'LIQUIDITY', currency: 'BRL',
            opening_balance: '0', opening_quantity: '0', opening_unit_price: '0' });
    }
    await page.goto('/investments/create/');
    await selectChoice(page.locator('#id_asset-search'), { label: 'Cash pot (POT)' });
    await expect(page.locator('#money-fields')).toBeHidden();
    await expect(page.locator('#funding-section')).toBeHidden();
    await page.getByLabel('Type').selectOption('YIELD');
    await expect(page.locator('#monetary-yield-fields')).toBeVisible();
    await expect(page.locator('#regular-amount-field')).toBeHidden();
    await expect(page.locator('#ending-balance-field')).toBeHidden();
    await page.getByRole('radio', { name: 'Enter the yield amount' }).check();
    await page.locator('#id_amount').fill('10');
    await selectChoice(page.locator('#id_asset-search'), { label: 'Shares (STK)' });
    await expect(page.locator('#id_amount')).toHaveValue('');
    await page.getByLabel('Type').selectOption('DEPOSIT');
    await expect(page.locator('#unit-fields')).toBeVisible();
    await expect(page.locator('#cash-fields')).toBeHidden();
    await selectChoice(page.locator('#id_source_account-search'), account);
    await page.locator('#id_cash_amount').fill('20');
    await selectChoice(page.locator('#id_source_account-search'), '');
    await expect(page.locator('#cash-fields')).toBeHidden();
    await expect(page.locator('#id_cash_amount')).toHaveValue('');
    await page.getByLabel('Type').selectOption('WITHDRAWAL');
    await expect(page.locator('#cash-fields')).toBeHidden();
    await selectChoice(page.locator('#id_destination_account-search'), account);
    await expect(page.locator('#cash-fields')).toBeVisible();
    await selectChoice(page.locator('#id_asset-search'), '');
    await expect(page.locator('#unit-fields')).toBeHidden();
    await expect(page.locator('#funding-section')).toBeHidden();
    await expect(page.locator('#id_destination_account')).toHaveValue('');
});

test('Portuguese mobile form keeps translated keyboard help and visible focus', async ({ page }, testInfo) => {
    await fixture(page, testInfo);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.request.post('/i18n/setlang/', {
        form: { csrfmiddlewaretoken: await page.locator('[name="csrfmiddlewaretoken"]').first().inputValue(), language: 'pt-br', next: '/transactions/create/' },
        headers: { Referer: page.url() },
    });
    await page.reload();
    await page.locator('#id_transaction_type').selectOption('EXPENSE');
    await page.locator('#category-search').fill('aplicati');
    await page.locator('#category-search').press('ArrowDown');
    await expect(page.locator('#category-search-help')).toHaveText('Digite para pesquisar. Use ↑/↓ para navegar, Enter para selecionar, Escape para fechar e Tab para continuar.');
    await expect(page.locator('#category-search-help')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('category-keyboard-pt-br-mobile.png'), fullPage: true });
});
