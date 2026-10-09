// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { selectChoice } = require('./helpers/forms');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const result = await page.request.post(path, { form: { csrfmiddlewaretoken: csrf, ...values },
        headers: { Referer: response.url() }, maxRedirects: 0 });
    expect(result.status(), await result.text()).toBe(302);
}

async function seed(page, info, unusedCount = 8) {
    const username = `assets-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', { username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' });
    await post(page, '/banking/create/', { name: 'Asset bank' });
    await page.goto('/investments/products/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/investments/products/create/', { bank, name: 'Asset fund', purpose: 'INVESTMENT' });
    await page.goto('/investments/assets/create/');
    const product = await page.locator('#id_opening_product option').last().getAttribute('value');
    await post(page, '/investments/assets/create/', { name: 'Z saved position', code: 'SAVED',
        asset_class: 'LIQUIDITY', currency: 'BRL', valuation_mode: 'MONETARY',
        opening_balance: '100', opening_product: product, opening_quantity: '0', opening_unit_price: '0' });
    await page.goto('/investments/create/');
    const asset = await page.locator('#id_asset option').last().getAttribute('value');
    await post(page, '/investments/create/', { product, asset, kind: 'YIELD', amount: '10',
        yield_input_mode: 'YIELD_AMOUNT', fees: '0', date: '2026-09-01', reason: 'Saved operation' });
    await page.goto('/investments/operations/');
    const editor = await page.locator('#investment-movements a[href$="/edit/"]').first().getAttribute('href');
    await post(page, '/investments/products/create/', { bank, name: 'Asset cash pot', purpose: 'MONTHLY_CASH' });
    await page.goto('/investments/assets/create/');
    const cashProduct = await page.locator('#id_opening_product option').filter({ hasText: 'Asset cash pot' }).getAttribute('value');
    await post(page, '/investments/create/', { product: cashProduct, asset, kind: 'YIELD', amount: '7',
        yield_input_mode: 'YIELD_AMOUNT', fees: '0', date: '2026-09-01', reason: 'Saved cash operation' });
    for (let i = 1; i <= unusedCount; i++) {
        await post(page, '/investments/assets/create/', { name: `Unused ${i}`, code: `EMPTY${i}`,
            asset_class: 'LIQUIDITY', currency: 'BRL', valuation_mode: 'MONETARY',
            opening_balance: '0', opening_quantity: '0', opening_unit_price: '0' });
    }
    return { asset, product, editor };
}

async function expectRetainedScroll(page, top) {
    await expect.poll(async () => page.evaluate(previous => {
        const maximum = Math.max(0, document.documentElement.scrollHeight - innerHeight);
        return Math.abs(scrollY - Math.min(previous, maximum));
    }, top)).toBeLessThan(4);
}

for (const theme of ['light', 'dark']) {
    test(`investment asset archive, history editor, restore and delete (${theme})`, async ({ page }, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const data = await seed(page, info);
        await page.goto('/investments/settings/');
        const row = page.locator(`#asset-${data.asset}`);
        await expect(row.getByRole('link', { name: 'Delete', exact: true })).toHaveCount(0);
        const availability = page.locator(`#asset-availability-${data.asset}`);
        await availability.scrollIntoViewIfNeeded();
        await availability.focus();
        await page.keyboard.press('Shift+Tab');
        await expect(row.getByRole('link', { name: 'Edit', exact: true })).toBeFocused();
        await page.keyboard.press('Tab');
        await expect(availability).toBeFocused();
        expect(await availability.evaluate(el => getComputedStyle(el).outlineStyle)).not.toBe('none');
        const top = await page.evaluate(() => scrollY);
        expect(top).toBeGreaterThan(100);
        await page.keyboard.press('Space');
        await expect(availability).toHaveText('Restore');
        await expect(availability).toBeFocused();
        await expect(page.locator('#investment-archived-assets')).toHaveAttribute('open', '');
        await expectRetainedScroll(page, top);
        await expect(page.locator('#investment-active-assets')).not.toContainText('Z saved position');
        await page.screenshot({ path: info.outputPath(`archived-assets-${theme}.png`), fullPage: true });

        await page.goto('/investments/');
        await expect(page.locator('#investment-total')).toHaveText(/BRL 110[,.]00/);
        await expect(page.getByRole('link', { name: 'View operations for Z saved position' })).toHaveCount(0);
        await expect(page.locator('main')).toContainText('No active positions in this section.');
        await page.locator('#investment-operations-link').press('Enter');
        await expect(page.locator('#investment-movements')).toContainText('Saved operation');
        await expect(page.locator('#investment-movements')).not.toContainText('Saved cash operation');
        await page.goto('/investments/?section=cash');
        await expect(page.locator('#investment-total')).toHaveText(/BRL 7[,.]00/);
        await expect(page.getByRole('link', { name: 'View operations for Z saved position' })).toHaveCount(0);
        await expect(page.locator('#investment-archived-positions-note')).toContainText('Their balances remain in totals and history.');
        await expect(page.locator('main')).not.toContainText('Asset cash pot');
        await page.screenshot({ path: info.outputPath(`archived-cash-positions-${theme}.png`), fullPage: true });
        await page.locator('#investment-operations-link').press('Enter');
        await expect(page).toHaveURL(/\/investments\/operations\/\?section=cash$/);
        await expect(page.locator('#investment-movements')).toContainText('Saved cash operation');
        await page.goto(`/investments/create/?asset=${data.asset}`);
        await expect(page.locator(`#id_asset option[value="${data.asset}"]`)).toHaveCount(0);
        await expect(page.locator('#id_asset')).toHaveValue('');

        await page.goto(data.editor);
        await expect(page.locator('#id_asset')).toHaveValue(data.asset);
        await expect(page.locator('main')).toContainText('The asset is archived. You can edit this operation');
        await selectChoice(page.locator('#id_asset'), data.asset);
        await page.locator('input[name="yield_input_mode"][value="YIELD_AMOUNT"]').press('Space');
        await page.locator('#id_amount').fill('-1');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(page.locator('#id_asset')).toHaveValue(data.asset);
        await expect(page.locator('[role="alert"]').first()).toBeVisible();
        await page.locator('#id_amount').fill('13');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(page).toHaveURL(/\/investments\/operations\/$/);

        await page.goto('/investments/settings/');
        const summary = page.locator('#investment-archived-summary');
        await summary.focus();
        await page.keyboard.press('Space');
        await expect(availability).toBeVisible();
        await availability.focus();
        const restoreTop = await page.evaluate(() => scrollY);
        await page.keyboard.press('Enter');
        await expect(availability).toHaveText('Archive');
        await expect(availability).toBeFocused();
        await expectRetainedScroll(page, restoreTop);
        await expect(page.locator('#investment-archived-assets')).toHaveCount(0);
        await page.goto('/investments/?section=cash');
        await expect(page.getByRole('link', { name: 'View operations for Z saved position' }).first()).toBeVisible();
        await expect(page.locator('#investment-total')).toHaveText(/BRL 7[,.]00/);
        await expect(page.locator('#investment-archived-positions-note')).toHaveCount(0);
        await page.goto('/investments/');
        await expect(page.getByRole('link', { name: 'View operations for Z saved position' }).first()).toBeVisible();
        await expect(page.locator('#investment-total')).toHaveText(/BRL 113[,.]00/);
        await page.goto('/investments/create/');
        await selectChoice(page.locator('#id_asset'), data.asset);
        await expect(page.locator('#id_asset')).toHaveValue(data.asset);

        await page.goto('/investments/settings/');
        const unused = page.locator('#investment-active-assets > li').filter({ hasText: 'Unused 1 (' });
        const unusedId = await unused.getAttribute('id');
        await unused.getByRole('link', { name: 'Delete', exact: true }).press('Enter');
        await expect(page.locator('main')).toContainText('This action cannot be undone.');
        await page.getByRole('button', { name: 'Delete', exact: true }).press('Enter');
        await expect(page).toHaveURL(/\/investments\/settings\/$/);
        await expect(page.locator(`#${unusedId}`)).toHaveCount(0);
    });
}

test('investment asset archive and restore use native Portuguese mobile forms', async ({ browser, page }, info) => {
    const data = await seed(page, info, 1);
    const context = await browser.newContext({ storageState: await page.context().storageState(),
        javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
    await context.addCookies([{ name: 'django_language', value: 'pt-br', url: new URL(page.url()).origin }]);
    const mobile = await context.newPage();
    try {
        await mobile.goto('/investments/settings/');
        const availability = mobile.locator(`#asset-availability-${data.asset}`);
        await availability.press('Enter');
        await expect(mobile).toHaveURL(new RegExp(`archived=${data.asset}#asset-${data.asset}$`));
        await expect(availability).toHaveText('Restaurar');
        await expect(availability).toBeVisible();
        await expect(mobile.locator('main')).toContainText('Ativos arquivados');
        expect(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await mobile.screenshot({ path: info.outputPath('archived-assets-mobile-pt.png'), fullPage: true });
        await mobile.goto('/investments/?section=cash');
        await expect(mobile.locator('#investment-total')).toHaveText(/BRL 7,00/);
        await expect(mobile.locator('main')).not.toContainText('Z saved position');
        await expect(mobile.locator('main')).toContainText('Não há posições ativas nesta seção.');
        await expect(mobile.locator('#investment-archived-positions-note')).toContainText('Seus saldos continuam nos totais e no histórico.');
        expect(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await mobile.screenshot({ path: info.outputPath('archived-cash-positions-mobile-pt.png'), fullPage: true });
        await mobile.locator('#investment-operations-link').press('Enter');
        await expect(mobile.locator('#investment-movements')).toContainText('Saved cash operation');
        await mobile.goto(data.editor);
        await expect(mobile.locator('#id_asset')).toHaveValue(data.asset);
        await mobile.locator('input[name="yield_input_mode"][value="YIELD_AMOUNT"]').press('Space');
        await mobile.locator('#id_amount').fill('-1');
        await mobile.getByRole('button', { name: 'Salvar', exact: true }).press('Enter');
        await expect(mobile.locator('#id_asset')).toHaveValue(data.asset);
        await expect(mobile.locator('[role="alert"]').first()).toBeVisible();
        await mobile.goto('/investments/settings/');
        await mobile.locator('#investment-archived-summary').press('Enter');
        await availability.press('Enter');
        await expect(availability).toHaveText('Arquivar');
        await mobile.goto('/investments/?section=cash');
        await expect(mobile.locator('main')).toContainText('Z saved position');
        await expect(mobile.locator('#investment-archived-positions-note')).toHaveCount(0);
        await mobile.goto('/investments/create/');
        await mobile.locator('#id_asset').selectOption(data.asset);
        await expect(mobile.locator('#id_asset')).toHaveValue(data.asset);
        await mobile.goto('/investments/settings/');
        const unused = mobile.locator('#investment-active-assets > li').filter({ hasText: 'Unused 1 (' });
        const unusedId = await unused.getAttribute('id');
        await unused.getByRole('link', { name: 'Excluir', exact: true }).press('Enter');
        await mobile.getByRole('button', { name: 'Excluir', exact: true }).press('Enter');
        await expect(mobile.locator(`#${unusedId}`)).toHaveCount(0);
    } finally {
        await context.close();
    }
});
