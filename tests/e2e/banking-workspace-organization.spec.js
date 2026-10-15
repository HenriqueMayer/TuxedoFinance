// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { selectChoice } = require('./helpers/forms');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const result = await page.request.post(path, { form: { csrfmiddlewaretoken: token, ...values },
        headers: { Referer: response.url() }, maxRedirects: 0 });
    expect(result.status(), (await result.text()).match(/role="alert"[^>]*>[^<]+/g)?.join(' ')).toBe(302);
    return result.headers().location;
}

async function seed(page, info) {
    const username = `banking-organized-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', { username, email: `${username}@example.test`, password1: 'Bank-E2E-2026!', password2: 'Bank-E2E-2026!' });
    await post(page, '/banking/create/', { name: 'Organization bank', color: '#24594A' });
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', { bank, name: 'Daily account', currency: 'BRL', opening_balance: '1000', opening_date: '2020-01-01', planning_enabled: 'on', reserved_amount: '0' });
    await post(page, '/investments/products/create/', { bank, name: 'Daily pot', purpose: 'MONTHLY_CASH' });
    await page.goto('/investments/assets/create/');
    const product = await page.locator('#id_opening_product option').filter({ hasText: 'Daily pot' }).getAttribute('value');
    await post(page, '/investments/assets/create/', { name: 'Emergency cash', code: 'EMERGENCY', asset_class: 'LIQUIDITY', currency: 'BRL', valuation_mode: 'MONETARY', opening_balance: '300', opening_quantity: '0', opening_unit_price: '0', opening_product: product, opening_date: '2020-01-01' });
    await page.goto('/investments/create/');
    const asset = await page.locator('#id_asset option').filter({ hasText: 'Emergency cash' }).getAttribute('value');
    await page.goto('/banking/credit-cards/create/');
    const account = await page.locator('#id_account option').last().getAttribute('value');
    const today = new Date().toISOString().slice(0, 10);
    await post(page, '/banking/credit-cards/create/', { account, name: 'Daily card', card_type: 'PHYSICAL', closing_day: '31', due_day: '30', manual_settlement_from: today });
    await post(page, '/categories/create/', { name: 'Card food', transaction_type: 'EXPENSE' });
    await page.goto('/transactions/create/');
    const card = await page.locator('#id_credit_card option').last().getAttribute('value');
    const category = await page.locator('#id_category option').filter({ hasText: /^Card food$/ }).getAttribute('value');
    await post(page, '/transactions/create/', { title: 'Card expense', amount: '100', transaction_type: 'EXPENSE', category,
        payment_channel: 'CREDIT_CARD', credit_card: card, date: today, installments: '1' });
    await post(page, '/banking/exchange-rates/create/', { from_currency: 'USD', to_currency: 'BRL', rate: '5.12', effective_date: '2026-10-02', notes: 'Local evidence' });
    await post(page, '/banking/exchange-rates/create/', { from_currency: 'EUR', to_currency: 'BRL', rate: '6.12', effective_date: '2026-10-02', notes: 'Other source' });
    return { bank, account, product, asset, card };
}

for (const theme of ['light', 'dark']) {
    for (const width of [390, 1440]) {
        test(`bank reserves and invoice/FX live filters preserve keyboard context (${width}, ${theme})`, async ({ page }, info) => {
            await page.setViewportSize({ width, height: 800 });
            await page.addInitScript(value => localStorage.setItem('theme', value), theme);
            const { bank, account, product, asset, card } = await seed(page, info);
            await page.goto('/banking/');
            const bankGroup = page.locator(`#bank-${bank}`);
            await expect(bankGroup).not.toHaveAttribute('open', '');
            await expect(bankGroup.locator(':scope > summary')).toHaveCSS('min-height', '56px');
            await expect(bankGroup.getByRole('link', { name: 'Add account', exact: true })).toBeHidden();
            await bankGroup.locator(':scope > summary').focus();
            await page.keyboard.press('Enter');
            await expect(bankGroup.getByRole('link', { name: 'Add account', exact: true })).toBeVisible();
            await expect(page.locator(`#bank-accounts-${bank}`)).toBeVisible();
            await expect(page.locator(`#bank-cards-${bank}`)).toBeVisible();
            const accountRow = page.locator(`#account-row-${account}`);
            await expect(accountRow.locator('td:nth-child(4) form')).toHaveCount(0);
            const accountActions = accountRow.locator('td:last-child');
            await expect(accountActions.locator(`#planning-toggle-${account}`)).toBeVisible();
            await expect(accountActions.locator('summary')).toHaveCSS('font-size', '14px');
            const rowActionSize = await accountActions.locator('summary').boundingBox();
            expect(rowActionSize.height).toBeGreaterThanOrEqual(width < 768 ? 44 : 36);
            expect(rowActionSize.width).toBeGreaterThanOrEqual(width < 768 ? 44 : 36);
            const bankOptions = page.locator(`#bank-options-${bank}`);
            await expect(bankOptions.getByRole('link', { name: 'Edit bank', exact: true })).toBeHidden();
            await bankOptions.locator(':scope > summary').press('Enter');
            await expect(bankOptions.getByRole('link', { name: 'Change marker color', exact: true })).toBeVisible();
            await bankOptions.locator(':scope > summary').press('Escape');
            await expect(bankOptions).not.toHaveAttribute('open', '');
            await page.locator(`#position-planning-${product}-${asset}`).press('Enter');
            const reserves = page.locator(`#bank-reserves-${bank}`);
            await expect(reserves).toHaveAttribute('open', '');
            await expect(reserves.locator(`#cash-position-${product}-${asset}`)).toBeVisible();
            await expect(page.locator('#planning-availability')).toContainText(/1[.,\s]000[,.]00/);
            await page.locator(`#planning-toggle-${account}`).press('Enter');
            await expect(reserves.locator(`#account-row-${account}`)).toBeVisible();
            await expect(reserves.locator(`#account-row-${account}`)).toContainText(/1[.,\s]000[,.]00/);
            await page.locator(`#planning-toggle-${account}`).press('Enter');
            await expect(page.locator(`#bank-positions-${bank} > section[aria-labelledby="bank-accounts-${bank}"] #account-row-${account}`)).toBeVisible();
            if (width < 768) {
                const labelColor = await page.locator(`#account-row-${account} td[data-label]`).first()
                    .evaluate(cell => getComputedStyle(cell, '::before').color);
                if (theme === 'dark') expect(labelColor).toBe('rgb(184, 184, 184)');
                else expect(labelColor).not.toBe('rgb(184, 184, 184)');
            }
            await reserves.locator(':scope > summary').press('Space');
            await expect(reserves.locator(`#cash-position-${product}-${asset}`)).toBeHidden();
            await page.screenshot({ path: info.outputPath(`bank-reserves-${width}-${theme}.png`), fullPage: true });
            const search = page.locator('#bank-filter-q');
            await search.fill('No matching bank');
            await expect(page.locator('#bank-results')).toContainText('No matching banks');
            await expect(search).toBeFocused();
            await expect(page).toHaveURL(/q=No\+matching\+bank/);
            await page.locator('[data-live-link="bank-filter-form"]').press('Enter');
            await expect(search).toHaveValue('');
            await expect(bankGroup).not.toHaveAttribute('open', '');

            await bankGroup.locator(':scope > summary').press('Enter');
            await bankGroup.getByRole('link', { name: 'Bank details', exact: true }).press('Enter');
            const cardRow = page.locator(`#credit-card-${card}`);
            const detailOptions = page.locator(`#bank-detail-options-${bank}`);
            await detailOptions.locator(':scope > summary').press('Enter');
            const detailPanel = detailOptions.locator('.secondary-actions-panel');
            const detailBounds = await detailPanel.boundingBox();
            expect(detailBounds.x).toBeGreaterThanOrEqual(0);
            expect(detailBounds.x + detailBounds.width).toBeLessThanOrEqual(width);
            for (const name of ['Edit bank', 'Change marker color', 'Add loyalty program', 'Delete']) {
                await expect(detailPanel.getByRole('link', { name, exact: true })).toBeVisible();
            }
            await detailOptions.locator(':scope > summary').press('Escape');
            await expect(detailOptions).not.toHaveAttribute('open', '');
            await expect(cardRow).toHaveCount(1);
            await expect(cardRow).toContainText('closes 31, due 30');
            await expect(cardRow.getByRole('link', { name: 'Invoices for Daily card', exact: true })).toBeVisible();
            const cardOptions = cardRow.locator('details.compact-menu');
            await expect(cardOptions.getByRole('link', { name: 'Edit', exact: true })).toBeHidden();
            await cardOptions.locator('summary').press('Enter');
            await expect(cardOptions.getByRole('link', { name: 'Edit', exact: true })).toBeVisible();
            await expect(cardOptions.getByRole('link', { name: 'Delete', exact: true })).toBeVisible();
            await cardOptions.locator('summary').press('Escape');
            await expect(cardOptions).not.toHaveAttribute('open', '');
            await page.screenshot({ path: info.outputPath(`bank-detail-${width}-${theme}.png`), fullPage: true });

            await page.goto('/banking/invoices/');
            const invoiceCriteria = page.locator('#invoice-extra-filters');
            await expect(invoiceCriteria).not.toHaveAttribute('open', '');
            await invoiceCriteria.locator(':scope > summary').press('Enter');
            await selectChoice(page.locator('#invoice-filter-card'), card);
            await expect(page).toHaveURL(new RegExp(`card=${card}`));
            await expect(page.locator('#invoice-results')).toContainText('Daily card');
            await page.locator('#invoice-filter-month-trigger').press('Space');
            const invoiceMonth = new Date().toISOString().slice(0, 7);
            await page.locator('#invoice-filter-month-year').fill(invoiceMonth.slice(0, 4));
            await page.locator('#invoice-filter-month-year').press('Enter');
            await selectChoice(page.locator('#invoice-filter-month-choice'), invoiceMonth.slice(5));
            await expect(page).toHaveURL(new RegExp(`month=${invoiceMonth}`));
            await expect(page.locator('#invoice-filter-month')).toHaveValue(invoiceMonth);
            await expect(page.locator('#invoice-active-filter-count')).toHaveText('2 active');
            await page.locator('#invoice-filter-status').selectOption('PAID');
            await expect(page.locator('#invoice-results')).toContainText('No matching invoices.');
            await page.locator('#invoice-filter-status').selectOption('');
            await expect(page.locator('#invoice-results')).toContainText('Daily card');
            await page.locator('#invoice-filter-q').fill('missing card');
            await expect(page.locator('#invoice-results')).toContainText('No matching invoices.');
            await expect(page.locator('#invoice-filter-q')).toBeFocused();
            await page.locator('[data-live-link="invoice-filter-form"]').press('Enter');
            await expect(page.locator('#invoice-filter-card')).toHaveValue('');
            await expect(page.locator('#invoice-filter-month')).toHaveValue('');
            await expect(page.locator('#invoice-active-filter-count')).toBeEmpty();
            await expect(invoiceCriteria).toHaveAttribute('open', '');
            await expect(page.locator('#invoice-results')).toContainText('Daily card');
            await page.screenshot({ path: info.outputPath(`invoice-filters-${width}-${theme}.png`), fullPage: true });

            await page.goto('/banking/exchange-rates/');
            const rateCriteria = page.locator('#rate-extra-filters');
            await expect(rateCriteria).not.toHaveAttribute('open', '');
            await rateCriteria.locator(':scope > summary').press('Enter');
            await page.locator('#rate-filter-from_currency').selectOption('USD');
            await page.locator('#rate-filter-to_currency').selectOption('BRL');
            await expect(page.locator('#rate-results')).toContainText('USD');
            await expect(page.locator('#rate-results')).not.toContainText('EUR');
            await expect(page.locator('#rate-active-filter-count')).toHaveText('2 active');
            await page.locator('#rate-filter-date_from').fill('2026-10-03');
            await page.locator('#rate-filter-date_from').press('Tab');
            await expect(page.locator('#rate-results')).toContainText('No matching exchange rates.');
            await page.locator('#rate-filter-date_to').fill('2026-10-01');
            await page.locator('#rate-filter-date_to').press('Tab');
            await expect(page.locator('#rate-filter-date_to-error-1')).toBeVisible();
            await page.locator('#rate-filter-date_to').fill('2026-10-30');
            await page.locator('#rate-filter-date_to').press('Tab');
            await expect(page.locator('#rate-filter-date_to-error-1')).toHaveCount(0);
            await page.locator('[data-live-link="rate-filter-form"]').press('Enter');
            // Wait for this explicit reset to finish before starting a new
            // search; otherwise typing deliberately supersedes the GET.
            await expect(page.locator('#rate-filter-date_from')).toHaveValue('');
            await expect(page.locator('#rate-filter-from_currency')).toHaveValue('');
            await page.locator('#rate-filter-q').fill('Local evidence');
            await expect(page.locator('#rate-results li')).toHaveCount(1);
            await expect(page.locator('#rate-filter-q')).toBeFocused();
            const origin = new URL(page.url()).pathname + new URL(page.url()).search;
            await page.locator('#rate-results').getByRole('link', { name: 'Edit', exact: true }).press('Enter');
            await page.locator('#id_rate').fill('0');
            await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
            await expect(page.locator('#id_rate')).toHaveValue('0');
            await expect(page.getByRole('link', { name: 'Cancel', exact: true })).toHaveAttribute('href', origin);
            await page.getByRole('link', { name: 'Cancel', exact: true }).press('Enter');
            await expect(page.locator('#rate-results')).toContainText(/5[,.]12/);
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            await page.screenshot({ path: info.outputPath(`fx-filters-${width}-${theme}.png`), fullPage: true });
        });
    }
}

test('bank reserves and financial filters keep a complete mobile native path', async ({ browser }, info) => {
    const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 800 } });
    const page = await context.newPage();
    try {
        const { bank, product, asset, card } = await seed(page, info);
        await page.goto('/banking/');
        await page.locator(`#bank-${bank} > summary`).press('Enter');
        await page.locator(`#position-planning-${product}-${asset}`).press('Enter');
        await expect(page.locator(`#bank-${bank}`)).toHaveAttribute('open', '');
        await expect(page.locator(`#bank-reserves-${bank}`)).toHaveAttribute('open', '');
        await expect(page.locator(`#cash-position-${product}-${asset}`)).toContainText(/300[,.]00/);
        await page.goto('/banking/invoices/');
        await page.locator('#invoice-extra-filters > summary').press('Enter');
        await page.locator('#invoice-filter-month').fill(new Date().toISOString().slice(0, 7));
        await page.locator('#invoice-filter-card').selectOption(card);
        await page.locator('#invoice-filter-form').getByRole('button', { name: 'Filter', exact: true }).press('Enter');
        await expect(page.locator('#invoice-results')).toContainText('Daily card');
        await page.goto('/banking/exchange-rates/');
        await page.locator('#rate-extra-filters > summary').press('Enter');
        await page.locator('#rate-filter-from_currency').selectOption('USD');
        await page.locator('#rate-filter-form').getByRole('button', { name: 'Filter', exact: true }).press('Enter');
        await expect(page.locator('#rate-results')).not.toContainText('EUR');
        await expect(page.locator('#rate-results')).toContainText('USD');
        await context.addCookies([{ name: 'django_language', value: 'pt-br', url: info.project.use.baseURL }]);
        await page.goto('/banking/?q=Organization');
        await expect(page.locator('html')).toHaveAttribute('lang', 'pt-br');
        const menu = page.locator('details[name="account-updates"]').first();
        await menu.locator('summary').press('Enter');
        await expect(menu.getByRole('link', { name: 'Nova transação', exact: true })).toBeVisible();
        await expect(menu.locator('summary')).toHaveCSS('font-size', '14px');
        await menu.getByRole('link', { name: 'Nova transação', exact: true }).press('Enter');
        await expect(page.getByRole('link', { name: 'Cancelar', exact: true })).toHaveAttribute('href', '/banking/?q=Organization');
    } finally { await context.close(); }
});

for (const [theme, language] of [['light', 'en'], ['dark', 'pt-br']]) {
    test(`compact account actions preserve touch, errors and origin (${theme}, ${language})`, async ({ browser }, info) => {
        const context = await browser.newContext({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 800 } });
        const page = await context.newPage();
        try {
            await page.addInitScript(value => localStorage.setItem('theme', value), theme);
            const username = `banking-touch-${info.workerIndex}-${Date.now()}`;
            await post(page, '/accounts/signup/', { username, email: `${username}@example.test`, password1: 'Bank-E2E-2026!', password2: 'Bank-E2E-2026!' });
            await post(page, '/banking/create/', { name: 'Touch bank', color: '#24594A' });
            await page.goto('/banking/accounts/create/');
            const bank = await page.locator('#id_bank option').last().getAttribute('value');
            await post(page, '/banking/accounts/create/', { bank, name: 'Touch account', currency: 'BRL', opening_balance: '1000', opening_date: '2020-01-01', planning_enabled: 'on', reserved_amount: '0' });
            await context.addCookies([{ name: 'django_language', value: language, url: info.project.use.baseURL }]);
            const origin = '/banking/?q=Touch';
            await page.goto(origin);
            const row = page.locator('tr[id^="account-row-"]').first();
            const account = (await row.getAttribute('id')).replace('account-row-', '');
            const menu = row.locator('details[name="account-updates"]');
            const summary = menu.locator('summary');
            await expect(menu).not.toHaveAttribute('open', '');
            await summary.tap();
            await expect(menu).toHaveAttribute('open', '');
            await expect(summary).toHaveCSS('font-size', '14px');
            const purchase = menu.getByRole('link', { name: language === 'en' ? 'New transaction' : 'Nova transação', exact: true });
            for (const control of [summary, purchase, row.locator(`#planning-toggle-${account}`)]) {
                const bounds = await control.boundingBox();
                expect(bounds.height).toBeGreaterThanOrEqual(44);
                expect(bounds.width).toBeGreaterThanOrEqual(44);
            }
            await purchase.tap();
            await expect(page.locator('#id_bank_account')).toHaveValue(account);
            await page.locator('#id_amount').fill('0');
            await page.getByRole('button', { name: language === 'en' ? 'Save' : 'Salvar', exact: true }).tap();
            await expect(page.locator('#id_amount')).toHaveValue('0');
            await expect(page.locator('#id_bank_account')).toHaveValue(account);
            const cancel = page.getByRole('link', { name: language === 'en' ? 'Cancel' : 'Cancelar', exact: true });
            await expect(cancel).toHaveAttribute('href', origin);
            await cancel.tap();
            await expect(page).toHaveURL(/\/banking\/\?q=Touch$/);
            await expect(page.locator(`#account-row-${account}`)).toContainText(/1[.,\s]000[,.]00/);
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            await page.locator(`#bank-${bank}`).getByRole('link', { name: language === 'en' ? 'Bank details' : 'Detalhes do banco', exact: true }).tap();
            const detailOptions = page.locator(`#bank-detail-options-${bank}`);
            await detailOptions.locator(':scope > summary').tap();
            const panel = detailOptions.locator('.secondary-actions-panel');
            const bounds = await panel.boundingBox();
            expect(bounds.x).toBeGreaterThanOrEqual(0);
            expect(bounds.x + bounds.width).toBeLessThanOrEqual(390);
            const names = language === 'en'
                ? ['Edit bank', 'Change marker color', 'Add loyalty program', 'Delete']
                : ['Editar banco', 'Alterar cor do marcador', 'Adicionar programa de fidelidade', 'Excluir'];
            for (const name of names) await expect(panel.getByRole('link', { name, exact: true })).toBeVisible();
            await page.getByRole('heading', { name: 'Touch bank', exact: true }).tap();
            await expect(detailOptions).not.toHaveAttribute('open', '');
            await page.screenshot({ path: info.outputPath(`compact-bank-touch-${theme}-${language}.png`), fullPage: true });
        } finally { await context.close(); }
    });
}
