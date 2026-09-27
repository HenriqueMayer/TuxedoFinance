// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const result = await page.request.post(path, {
        form: { csrfmiddlewaretoken: csrf, ...values },
        headers: { Referer: response.url() }, maxRedirects: 0,
    });
    expect(result.status(), path).toBe(302);
}

async function seed(page, info, count = 12) {
    const username = `operations-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', { username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' });
    await post(page, '/banking/create/', { name: 'Operations bank' });
    await page.goto('/investments/products/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/investments/products/create/', { bank, name: 'Portfolio fund', purpose: 'INVESTMENT' });
    await page.goto('/investments/assets/create/');
    const product = await page.locator('#id_opening_product option').last().getAttribute('value');
    await post(page, '/investments/assets/create/', { name: 'Stored balance', code: 'BAL',
        asset_class: 'LIQUIDITY', currency: 'BRL', valuation_mode: 'MONETARY',
        opening_balance: '1000', opening_product: product, opening_quantity: '0', opening_unit_price: '0' });
    await page.goto('/investments/create/');
    const asset = await page.locator('#id_asset option').last().getAttribute('value');
    for (let i = 1; i <= count; i++) {
        await post(page, '/investments/create/', { product, asset, kind: 'YIELD', yield_input_mode: 'YIELD_AMOUNT',
            amount: '10', fees: '0', date: '2026-09-01', reason: `Operation ${String(i).padStart(2, '0')}` });
    }
    await post(page, '/investments/products/create/', { bank, name: 'Cash pot', purpose: 'MONTHLY_CASH' });
    await page.goto('/investments/create/');
    const cash = await page.locator('#id_product option').filter({ hasText: 'Cash pot' }).getAttribute('value');
    await post(page, '/investments/create/', { product: cash, asset, kind: 'YIELD', yield_input_mode: 'YIELD_AMOUNT',
        amount: '5', fees: '0', date: '2026-09-01', reason: 'Pot yield' });
}

for (const theme of ['light', 'dark']) {
    test(`operations navigation, scoped history and keyboard filters (${theme})`, async ({ page }, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await seed(page, info);
        await page.goto('/investments/');
        await expect(page.locator('#investment-movements')).toHaveCount(0);
        const link = page.locator('#investment-operations-link');
        await expect(page.locator('#investments-charts')).toHaveCount(0);
        await link.scrollIntoViewIfNeeded();
        await page.screenshot({ path: info.outputPath(`portfolio-charts-${theme}.png`) });
        await link.focus();
        await page.keyboard.press('Enter');
        await expect(page).toHaveURL(/operations\/\?section=portfolio$/);
        const tabs = page.getByRole('navigation', { name: 'Investment sections' });
        await expect(tabs.getByRole('link', { name: 'Operations', exact: true })).toHaveAttribute('aria-current', 'page');
        await expect(tabs.getByRole('button', { name: 'Simulate returns' })).toHaveAttribute('aria-disabled', 'true');
        await expect(page.locator('#investments-charts')).toHaveCount(0);
        const history = page.locator('#investment-movements');
        await expect(history).toContainText('Page 1 of 2');
        await expect(history).not.toContainText('Pot yield');
        await history.getByRole('link', { name: 'Next', exact: true }).press('Enter');
        await expect(history).toContainText('Page 2 of 2');
        await expect(page.locator('#investment-purpose')).toHaveValue('portfolio');
        await page.locator('#investment-search').fill('Operation 01');
        await page.locator('#investment-search').press('Enter');
        await expect(history.locator('ul > li')).toHaveCount(1);
        await expect(history).toContainText('Operation 01');
        await expect(page.locator('#investment-search')).toBeFocused();
        await page.locator('#investment-search').fill('');
        await page.locator('#investment-purpose').focus();
        await page.keyboard.press('End');
        await page.keyboard.press('Tab');
        await history.getByRole('button', { name: 'Filter', exact: true }).press('Enter');
        await expect(history).toContainText('Pot yield');
        await expect(history.locator('ul > li')).toHaveCount(1);
        await history.getByRole('link', { name: 'Clear filters', exact: true }).press('Enter');
        await expect(page.locator('#investment-purpose')).toHaveValue('');
        await expect(history).toContainText('Page 1 of 2');
        const menu = page.getByRole('navigation', { name: 'Main navigation' }).locator('[data-nav-item="investments"]');
        await menu.locator(':scope > a').hover();
        await expect(menu.getByRole('link', { name: 'Operations', exact: true })).toBeVisible();
        // The menu reloads the same URL after Clear filters. A URL assertion
        // alone can pass while the old tabs are still being replaced by HTMX.
        await Promise.all([
            page.waitForResponse(response => response.request().method() === 'GET'
                && new URL(response.url()).pathname === '/investments/operations/'
                && new URL(response.url()).search === ''),
            menu.getByRole('link', { name: 'Operations', exact: true }).press('Enter'),
        ]);
        await expect(page.locator('body')).not.toHaveAttribute('aria-busy', 'true');
        await expect(page.locator('body')).not.toHaveClass(/htmx-settling/);
        await expect(page).toHaveURL(/\/investments\/operations\/$/);
        await tabs.getByRole('link', { name: 'Remunerated cash', exact: true }).press('Enter');
        await expect(page).toHaveURL(/\/investments\/\?section=cash$/);
        await page.locator('#investment-operations-link').press('Enter');
        await expect(page).toHaveURL(/operations\/\?section=cash$/);
        await expect(history).toContainText('Pot yield');
        await page.mouse.move(4, 80);
        await page.screenshot({ path: info.outputPath(`operations-${theme}.png`), fullPage: true });
    });
}

test('operations remain usable on mobile without JavaScript', async ({ page, browser }, info) => {
    await seed(page, info, 1);
    const context = await browser.newContext({ storageState: await page.context().storageState(),
        javaScriptEnabled: false, viewport: { width: 390, height: 740 } });
    try {
        const mobile = await context.newPage();
        await mobile.goto('/investments/');
        await mobile.locator('#investment-operations-link').press('Enter');
        await expect(mobile).toHaveURL(/operations\/\?section=portfolio$/);
        await mobile.locator('#investment-purpose').selectOption('cash');
        await mobile.getByRole('button', { name: 'Filter', exact: true }).press('Enter');
        await expect(mobile.locator('#investment-movements')).toContainText('Pot yield');
        await expect(mobile.locator('#investment-movements')).not.toContainText('Operation 01');
        expect(await mobile.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
        await mobile.evaluate(() => window.scrollTo(0, 0));
        await mobile.screenshot({ path: info.outputPath('operations-mobile-native.png'), fullPage: true });
    } finally { await context.close(); }
});

for (const theme of ['light', 'dark']) {
    test(`investment chart scopes and contextual operation labels (${theme})`, async ({ page }, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await seed(page, info, 1);
        await page.goto('/investments/charts/');
        const chart = page.locator('[data-chart-selection]').first();
        await chart.locator('[data-point]').last().press('Enter');
        await expect(chart.locator('[data-selection-values]')).toContainText('1,015.00');
        await page.locator('#investment-chart-scope').focus();
        await page.keyboard.press('End');
        await expect(page).toHaveURL(/scope=cash/);
        await chart.locator('[data-point]').last().press('Enter');
        await expect(chart.locator('[data-selection-values]')).toContainText('5.00');
        await chart.getByRole('link', { name: 'Next window' }).press('Enter');
        await expect(page).toHaveURL(/scope=cash/);
        await expect(page).toHaveURL(/total_offset=1/);
        await expect(page.locator('#investment-chart-scope')).toHaveValue('cash');
        await page.locator('#investment-chart-scope').focus();
        await page.keyboard.press('ArrowUp');
        await expect(page).toHaveURL(/scope=portfolio/);
        await chart.locator('[data-point]').last().press('Enter');
        await expect(chart.locator('[data-selection-values]')).toContainText('1,010.00');
        await page.setViewportSize({ width: 390, height: 740 });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: info.outputPath(`investment-charts-${theme}.png`), fullPage: true });
        await page.goto('/investments/create/');
        const { selectChoice } = require('./helpers/forms');
        await selectChoice(page.locator('#id_product'), { label: 'Operations bank - Portfolio fund' });
        await selectChoice(page.locator('#id_asset'), { label: 'Stored balance (BAL)' });
        await page.locator('#id_kind').focus();
        await page.keyboard.press('End');
        await page.keyboard.press('Tab');
        await page.getByRole('radio', { name: 'Enter the yield amount' }).press('Space');
        await expect(page.getByLabel('Yield amount', { exact: true })).toBeVisible();
        await page.locator('#id_kind').focus();
        await page.keyboard.press('ArrowUp');
        await page.keyboard.press('Tab');
        await expect(page.getByLabel('Withdrawal amount', { exact: true })).toBeVisible();
        await expect(page.locator('#asset-mode-status')).toContainText('withdrawal amount');
        const help = page.getByRole('button', { name: 'Explain Withdrawal amount', exact: true });
        await help.hover();
        await expect(page.locator('#id_amount-help')).toBeVisible();
        await page.locator('#yield-preview').evaluate(target => {
            document.dispatchEvent(new CustomEvent('htmx:beforeSwap', { detail: { target } }));
        });
        await expect(page.locator('#id_amount-help')).toBeVisible();
        await page.mouse.move(2, 2);
        await expect(page.locator('#id_amount-help')).toBeHidden();
        await help.focus();
        await expect(page.locator('#id_amount-help')).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(page.locator('#id_amount-help')).toBeHidden();
        await page.getByLabel('Withdrawal amount', { exact: true }).fill('0');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(page.locator('#id_amount-error-1')).toBeVisible();
        await expect(page.getByLabel('Withdrawal amount', { exact: true })).toBeVisible();
        await page.locator('#id_kind').focus();
        await page.keyboard.press('ArrowUp');
        await page.keyboard.press('Tab');
        await expect(page.getByLabel('Deposit amount', { exact: true })).toBeVisible();
        await expect(page.locator('#asset-mode-status')).toContainText('deposit amount');
        await page.screenshot({ path: info.outputPath(`operation-copy-${theme}.png`), fullPage: true });
    });
}

test('chart scopes retain native GET filtering without JavaScript', async ({ page, browser }, info) => {
    await seed(page, info, 1);
    const context = await browser.newContext({ storageState: await page.context().storageState(), javaScriptEnabled: false });
    try {
        const native = await context.newPage();
        await native.goto('/investments/charts/');
        await native.locator('#investment-chart-scope').selectOption('cash');
        await native.getByRole('button', { name: 'Filter', exact: true }).press('Enter');
        await expect(native.locator('#investment-chart-scope')).toHaveValue('cash');
        const chart = native.locator('[data-chart-selection]').first();
        await expect(chart.locator('[data-point]').last()).toHaveAttribute('aria-label', /5,00/);
        await chart.getByRole('link', { name: 'Next window' }).press('Enter');
        await expect(native).toHaveURL(/scope=cash/);
    } finally { await context.close(); }
});

for (const theme of ['light', 'dark']) {
    test(`Portuguese investment and planning controls (${theme})`, async ({ browser }, info) => {
        const context = await browser.newContext({ locale: 'pt-BR', viewport: { width: 1280, height: 900 } });
        const page = await context.newPage();
        page.on('dialog', dialog => dialog.accept());
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        try {
            await seed(page, info, 1);
            await page.goto('/investments/charts/');
            await expect(page.getByRole('navigation', { name: 'Seções de investimentos' }).getByRole('link', { name: 'Gráficos' })).toHaveAttribute('aria-current', 'page');
            await expect(page.locator('#investment-chart-scope option:checked')).toHaveText('Geral');
            await page.locator('#investment-chart-scope').selectOption('cash');
            await expect(page).toHaveURL(/scope=cash/);
            await page.goBack();
            await expect(page.locator('#investment-chart-scope')).toHaveValue('');
            await page.screenshot({ path: info.outputPath(`graficos-${theme}.png`), fullPage: true });
            await page.goto('/investments/create/');
            const { selectChoice } = require('./helpers/forms');
            await selectChoice(page.locator('#id_asset'), { label: 'Stored balance (BAL)' });
            await page.locator('#id_kind').selectOption('WITHDRAWAL');
            await expect(page.getByLabel('Valor do resgate', { exact: true })).toBeVisible();
            await expect(page.locator('#asset-mode-status')).toContainText('valor do resgate em BRL');
            await page.goto('/sandbox/');
            await page.locator('#id_gross_salary').fill('5000');
            const month = page.locator('#id_planning_month');
            await month.evaluate(input => {
                const open = input.showPicker;
                input.showPicker = function () { this.dataset.openedPicker = 'true'; return open.call(this); };
            });
            await month.click({ position: { x: 30, y: 20 } });
            await expect(month).toHaveAttribute('data-opened-picker', 'true');
            await page.keyboard.press('Escape');
            await month.fill('2026-10');
            await expect(page.locator('[data-planning-month]')).toHaveText('Outubro 2026');
            const reserve = page.locator('[data-variable-row]').first();
            await reserve.locator('[name="variable_label"]').fill('Reserva');
            await reserve.locator('[name="variable_type"]').selectOption('percent');
            await reserve.locator('[name="variable_value"]').fill('10');
            await page.locator('#budget-calculate').press('Enter');
            await expect(page.getByText('R$ 3.998,49', { exact: true })).toBeVisible();
            await expect(page.locator('#budget-forecast')).toBeHidden();
            await page.evaluate(() => window.scrollTo(0, 0));
            await page.screenshot({ path: info.outputPath(`planejamento-${theme}.png`), fullPage: true });
            await page.goto('/sandbox/simulation/');
            await page.locator('#id_initial_balance').fill('1000');
            await page.locator('#id_rate_period').selectOption('annual');
            await page.locator('#id_rate').fill('12');
            await page.getByRole('button', { name: '2 anos', exact: true }).press('Enter');
            await expect(page.locator('label[for="id_rate"]')).toContainText('Taxa anual efetiva (%)');
            await expect(page.locator('#simulation-result')).toContainText('1.254,40');
            await page.locator('#id_rate_period').selectOption('monthly');
            await expect(page.locator('label[for="id_rate"]')).toContainText('Taxa mensal efetiva (%)');
            await page.locator('#id_rate').fill('1');
            await expect(page.locator('#simulation-result')).toContainText('1.269,74');
            await page.evaluate(() => window.scrollTo(0, 0));
            await page.screenshot({ path: info.outputPath(`simulacao-${theme}.png`), fullPage: true });
        } finally { await context.close(); }
    });
}
