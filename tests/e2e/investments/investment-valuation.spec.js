// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { selectChoice } = require('../helpers/forms');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const result = await page.request.post(path, { form: { csrfmiddlewaretoken: csrf, ...values },
        headers: { Referer: response.url() }, maxRedirects: 0 });
    expect(result.status(), (await result.text()).slice(-1000)).toBe(302);
}

async function seed(page, info) {
    const username = `valuation-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', { username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' });
    await post(page, '/banking/create/', { name: 'Valuation bank' });
    await page.goto('/investments/products/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/investments/products/create/', { bank, name: 'Local portfolio', purpose: 'INVESTMENT' });
    await page.goto('/investments/assets/create/');
    const product = await page.locator('#id_opening_product option').last().getAttribute('value');
    await post(page, '/investments/assets/create/', { name: 'Local share', code: 'LOCAL', asset_class: 'EQUITY',
        valuation_mode: 'UNITS', currency: 'BRL', opening_quantity: '2', opening_unit_price: '100',
        opening_balance: '0', opening_product: product, opening_date: '2026-09-01' });
    await post(page, '/investments/assets/create/', { name: 'Local cash', code: 'CASH', asset_class: 'LIQUIDITY',
        valuation_mode: 'MONETARY', currency: 'BRL', opening_quantity: '0', opening_unit_price: '0', opening_balance: '0' });
    await page.goto('/investments/create/');
    const asset = await page.locator('#id_asset option').filter({ hasText: 'Local share' }).getAttribute('value');
    return { asset, product };
}

async function tabTo(page, control) {
    for (let count = 0; count < 20; count++) {
        if (await control.evaluate(element => document.activeElement === element)) return;
        await page.keyboard.press('Tab');
    }
    throw new Error('Control is not reachable through the keyboard');
}

for (const theme of ['light', 'dark']) {
    test(`dated opening, observed price and explicit fee keyboard recovery (${theme})`, async ({ page }, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const { asset, product } = await seed(page, info);
        await page.goto('/investments/assets/create/');
        await expect(page.locator('#opening-date-fields')).toBeHidden();
        await page.locator('#id_name').fill('New dated share');
        await page.locator('#id_code').fill('DATED');
        await page.locator('#id_asset_class').selectOption('EQUITY');
        await page.locator('#id_currency').selectOption('BRL');
        await page.locator('#id_valuation_mode').focus();
        await page.keyboard.press('End');
        await page.keyboard.press('Tab');
        await tabTo(page, page.locator('#id_opening_quantity'));
        await expect(page.locator('#id_opening_quantity')).toBeFocused();
        await page.locator('#id_opening_quantity').fill('1');
        await page.locator('#id_opening_unit_price').fill('10');
        await selectChoice(page.locator('#id_opening_product'), product);
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(page.locator('#opening-date-fields')).toContainText('Enter the date of the opening position.');
        await expect(page.locator('#id_opening_quantity')).toHaveValue('1');
        await page.locator('#id_opening_date').fill('01/09/2026');
        await page.locator('#id_opening_quantity').fill('0');
        await expect(page.locator('#opening-date-fields')).toBeHidden();
        await expect(page.locator('#id_opening_date')).toHaveValue('');
        await page.locator('#id_opening_quantity').fill('1');
        await page.locator('#id_opening_unit_price').fill('10');
        await selectChoice(page.locator('#id_opening_product'), product);
        await page.locator('#id_opening_date').fill('01/09/2026');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(page).toHaveURL(/\/investments\/settings\/$/);

        await page.goto('/investments/prices/create/');
        await expect(page.locator('#id_asset')).toHaveValue('');
        await selectChoice(page.locator('#id_asset'), asset);
        await page.locator('#id_date').fill('10/09/2026');
        await page.locator('#id_unit_price').fill('125');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(page.locator('#id_source')).toHaveAttribute('aria-invalid', 'true');
        await expect(page.locator('#id_asset')).toHaveValue(asset);
        await page.locator('#id_source').fill('Statement consulted locally');
        await page.locator('#id_source').press('Tab');
        await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeFocused();
        await page.keyboard.press('Enter');
        await expect(page).toHaveURL(/\/investments\/prices\/$/);
        const row = page.locator('tbody tr').filter({ hasText: 'Statement consulted locally' });
        await row.getByRole('link', { name: 'Edit', exact: true }).press('Enter');
        await page.locator('#id_unit_price').fill('130');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(row).toContainText('130');

        await page.goto('/investments/create/');
        await selectChoice(page.locator('#id_product'), product);
        await selectChoice(page.locator('#id_asset'), asset);
        await page.locator('#id_kind').focus();
        await page.keyboard.press('End');
        await page.keyboard.press('Tab');
        await page.getByText('Advanced options', { exact: true }).press('Enter');
        const feeCurrency = page.locator('#id_fees_in_asset_currency');
        await expect(feeCurrency).not.toBeChecked();
        await feeCurrency.press('Space');
        await expect(feeCurrency).toBeChecked();
        await selectChoice(page.locator('#id_asset'), { label: 'Local cash (CASH)' });
        await expect(page.locator('#fee-currency-fields')).toBeHidden();
        await expect(feeCurrency).not.toBeChecked();
        await selectChoice(page.locator('#id_asset'), asset);
        await expect(feeCurrency).not.toBeChecked();
        await feeCurrency.press('Space');
        await page.locator('#id_fees').fill('2');
        await page.locator('#id_date').fill('15/09/2026');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(page.locator('#id_quantity')).toHaveAttribute('aria-invalid', 'true');
        await expect(feeCurrency).toBeChecked();
        await page.locator('#id_quantity').fill('1');
        await page.locator('#id_unit_price').fill('50');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(page).toHaveURL(/\/investments\/operations\//);
        await page.goto('/investments/');
        await page.locator('#investment-position-list:visible').getByRole('link', { name: 'Local share', exact: true }).filter({ visible: true }).press('Enter');
        const holding = page.locator('main');
        await holding.getByText('Cost, price and results', { exact: true }).press('Enter');
        await expect(holding).toContainText('252');
        await expect(holding).toContainText('Statement consulted locally');
        await page.screenshot({ path: info.outputPath(`valuation-${theme}.png`), fullPage: true });
        await page.goto('/investments/charts/');
        await expect(page.getByRole('heading', { name: 'Recorded performance history' })).toBeVisible();
        await page.setViewportSize({ width: 390, height: 740 });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: info.outputPath(`valuation-history-${theme}-mobile.png`), fullPage: true });
    });
}

test('local observed prices create, correct and delete without JavaScript', async ({ page, browser }, info) => {
    const { asset } = await seed(page, info);
    const context = await browser.newContext({ storageState: await page.context().storageState(),
        javaScriptEnabled: false, viewport: { width: 390, height: 740 } });
    try {
        const native = await context.newPage();
        await native.goto('/investments/prices/create/');
        await native.locator('#id_asset').selectOption(asset);
        await native.locator('#id_date').fill('10/09/2026');
        await native.locator('#id_unit_price').fill('125');
        await native.locator('#id_source').fill('Native local statement');
        await native.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(native).toHaveURL(/\/investments\/prices\/$/);
        await native.getByRole('link', { name: 'Edit', exact: true }).press('Enter');
        await native.locator('#id_unit_price').fill('135');
        await native.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(native.locator('tbody')).toContainText('135');
        await native.getByRole('link', { name: 'Delete', exact: true }).press('Enter');
        await native.getByRole('button', { name: 'Delete', exact: true }).press('Enter');
        await expect(native.locator('tbody')).toContainText('No observed prices.');
        expect(await native.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    } finally { await context.close(); }
});
