// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const result = await page.request.post(path, { form: { csrfmiddlewaretoken: csrf, ...values },
        headers: { Referer: response.url() }, maxRedirects: 0 });
    expect(result.status(), await result.text()).toBe(302);
}

async function seed(page, info) {
    const username = `fx-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', { username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' });
    await post(page, '/banking/create/', { name: 'FX bank' });
    await page.goto('/investments/products/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/investments/products/create/', { bank, name: 'Dollar product', purpose: 'INVESTMENT' });
    await page.goto('/investments/assets/create/');
    const product = await page.locator('#id_opening_product option').last().getAttribute('value');
    const openingDate = '2025-01-01';
    await post(page, '/investments/assets/create/', { name: 'Dollar position', code: 'USD',
        asset_class: 'LIQUIDITY', currency: 'USD', valuation_mode: 'MONETARY',
        opening_date: openingDate, opening_balance: '100', opening_product: product, opening_quantity: '0', opening_unit_price: '0' });
    const today = new Date().toISOString().slice(0, 10);
    const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
    await post(page, '/banking/exchange-rates/create/', { from_currency: 'USD', to_currency: 'BRL',
        rate: '5', effective_date: today });
    await page.goto('/investments/create/');
    const asset = await page.locator('#id_asset option').last().getAttribute('value');
    await post(page, '/investments/create/', { product, asset, kind: 'YIELD', yield_input_mode: 'YIELD_AMOUNT',
        amount: '10', fees: '0', date: yesterday });
    return { product, asset, today, yesterday, openingDate };
}

async function tabTo(page, control) {
    for (let i = 0; i < 90; i++) {
        if (await control.evaluate(el => document.activeElement === el)) return;
        await page.keyboard.press('Tab');
    }
    throw new Error('Control not reachable by keyboard');
}

async function commitDateFilterAtKeyboardLocation(page, control) {
    let release, intercepted, completed;
    let hasRequest = false;
    const responseGate = new Promise(resolve => { release = resolve; });
    const requestSeen = new Promise(resolve => { intercepted = resolve; });
    const requestHandled = new Promise(resolve => { completed = resolve; });
    const matches = url => url.pathname === '/investments/operations/' && url.searchParams.has('date_to');
    const hold = async route => {
        hasRequest = true;
        intercepted();
        try {
            await responseGate;
            await route.continue();
        } finally { completed(); }
    };
    await page.route(matches, hold);
    try {
        // Native Tab reveals the adjacent calendar control and may scroll to
        // it. Measure that user-selected location before releasing the GET;
        // the assertion below then isolates background-update preservation.
        await control.press('Tab');
        await page.keyboard.press('Shift+Tab');
        await requestSeen;
        return await page.evaluate(() => scrollY);
    } finally {
        release();
        // Unrouting an active handler can automatically continue it. Wait for
        // our continuation before removal so each real GET is handled once.
        if (hasRequest) await requestHandled;
        await page.unroute(matches, hold);
    }
}

for (const theme of ['light', 'dark']) {
    test(`current FX, dated history recovery and position shortcuts (${theme})`, async ({ page }, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const data = await seed(page, info);
        await page.goto('/investments/');
        await expect(page.locator('#investment-total')).toHaveText(/BRL 550[,.]00/);
        await expect(page.locator('#investment-fx-warning')).toHaveCount(0);
        const rates = page.locator('main summary').filter({ hasText: 'Value details' });
        await rates.press('Enter');
        await expect(page.locator('main')).toContainText('USD/BRL');
        await page.screenshot({ path: info.outputPath(`portfolio-${theme}.png`), fullPage: true });
        const position = page.getByRole('link', { name: 'Dollar position', exact: true }).filter({ visible: true });
        await position.press('Enter');
        await expect(page).toHaveURL(new RegExp(`/positions/${data.product}/${data.asset}/`));
        await page.getByRole('link', { name: 'Full history', exact: true }).press('Enter');
        await expect(page).toHaveURL(new RegExp(`product=${data.product}.*asset=${data.asset}`));
        await expect(page.locator('#investment-movements li')).toHaveCount(1);
        await page.goBack();
        await page.goBack();
        await expect(page).toHaveURL(/\/investments\/$/);
        await position.press('Enter');
        await page.locator('main header').getByRole('link', { name: 'Update', exact: true }).press('Enter');
        await page.getByRole('link', { name: 'Record yield', exact: true }).press('Enter');
        await expect(page.locator('#id_product')).toHaveValue(data.product);
        await expect(page.locator('#id_asset')).toHaveValue(data.asset);
        await expect(page.locator('#id_kind')).toHaveValue('YIELD');
        await page.goto('/investments/');
        await page.goto('/analytics/investments/');
        const warning = page.locator('#investment-chart-fx-warning');
        await expect(warning).toContainText('Historical conversion incomplete');
        await warning.locator('summary').press('Enter');
        // The dated baseline and each missing valuation cutoff have their own
        // rate link. Recover the declared baseline rather than an arbitrary row.
        const opening = warning.locator('li').filter({
            has: page.locator(`a[href*="effective_date=${data.openingDate}"]`),
        });
        await expect(opening).toHaveCount(1);
        await expect(opening).toContainText('Opening position:');
        const chartsOrigin = '/analytics/investments/#investments-charts';
        const register = opening.getByRole('link', { name: 'Register exchange rate' });
        const target = new URL(await register.getAttribute('href'), page.url());
        // Context is another query parameter, not part of the dated rate value.
        expect(target.searchParams.get('effective_date')).toBe(data.openingDate);
        expect(target.searchParams.get('from_currency')).toBe('USD');
        expect(target.searchParams.get('to_currency')).toBe('BRL');
        expect(target.searchParams.get('next')).toBe(chartsOrigin);
        await register.press('Enter');
        await expect(page).toHaveURL(url => url.pathname === '/banking/exchange-rates/create/'
            && url.searchParams.get('effective_date') === data.openingDate
            && url.searchParams.get('next') === chartsOrigin);
        await expect(page.locator('#id_from_currency')).toHaveValue('USD');
        await expect(page.locator('#id_to_currency')).toHaveValue('BRL');
        await expect(page.locator('#id_effective_date')).toHaveValue('01/01/2025');
        await expect(page.locator('[data-preferred-date-field]').filter({has: page.locator('#id_effective_date')})
            .locator('[data-native-date-picker]')).toHaveValue(data.openingDate);
        await expect(page.locator('#id_rate')).toHaveValue('');
        await page.locator('#id_rate').fill('0');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(page.locator('[data-field-error]')).toBeVisible();
        await expect(page.locator('#id_from_currency')).toHaveValue('USD');
        await expect(page.locator('main input[name="next"]')).toHaveValue(chartsOrigin);
        await page.locator('#id_rate').fill('5');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        // Saving returns to the chart that requested recovery, not the rate list.
        await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === chartsOrigin);
        const details = warning.locator('details');
        if (!(await details.evaluate(node => node.open))) await warning.locator('summary').press('Enter');
        await expect(details).toHaveAttribute('open');
        await expect(warning.locator('li')).toHaveCount(1);
        await expect(warning).not.toContainText('Opening position:');
        const openOperation = warning.getByRole('link', { name: 'Open operation' });
        expect(new URL(await openOperation.getAttribute('href'), page.url()).searchParams.get('next'))
            .toBe(chartsOrigin);
        await openOperation.press('Enter');
        const capture = page.locator('#id_capture_missing_fx');
        await expect(capture).not.toBeChecked();
        await expect(page.locator('main input[name="next"]')).toHaveValue(chartsOrigin);
        const help = page.getByRole('button', { name: 'Explain Record the missing historical conversion' });
        await help.hover();
        await expect(page.locator('#id_capture_missing_fx-help')).toBeVisible();
        await page.mouse.move(2, 2);
        await expect(page.locator('#id_capture_missing_fx-help')).toBeHidden();
        await tabTo(page, help);
        await expect(page.locator('#id_capture_missing_fx-help')).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(page.locator('#id_capture_missing_fx-help')).toBeHidden();
        await tabTo(page, capture);
        await page.keyboard.press('Space');
        await expect(capture).toBeChecked();
        await expect(capture).toBeFocused();
        await page.screenshot({ path: info.outputPath(`capture-${theme}.png`), fullPage: true });
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === chartsOrigin);
        await expect(warning).toHaveCount(0);
        await page.goto('/investments/');
        await expect(page.locator('#investment-total')).toHaveText(/BRL 550[,.]00/);
    });

    test(`operation date/currency filters retain errors, focus and GET navigation (${theme})`, async ({ page }, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({ width: 1280, height: 620 });
        const data = await seed(page, info);
        await page.goto('/investments/operations/');
        await expect(page.locator('#investment-extra-filters')).not.toHaveAttribute('open');
        await page.locator('#investment-extra-filters summary').press('Enter');
        await page.locator('#investment-currency').selectOption('USD');
        await page.locator('#investment-asset-class').selectOption('LIQUIDITY');
        await expect(page).toHaveURL(url => url.searchParams.get('asset_class') === 'LIQUIDITY');
        await page.locator('#investment-date-from').fill(data.today);
        await page.locator('#investment-date-from').press('Tab');
        await expect(page).toHaveURL(url => url.searchParams.get('date_from') === data.today);
        await page.locator('#investment-date-to').fill(data.yesterday);
        const scrollBefore = await commitDateFilterAtKeyboardLocation(page, page.locator('#investment-date-to'));
        expect(scrollBefore).toBeGreaterThan(0);
        await expect(page.getByRole('alert')).toContainText('The end date must be on or after the start date.');
        await expect(page.locator('#investment-date-to')).toBeFocused();
        await expect(page.locator('#investment-movements')).not.toHaveClass(/htmx-settling/);
        await expect.poll(() => page.evaluate(() => scrollY)).toBe(scrollBefore);
        await expect(page.locator('#investment-movements > div ul li')).toHaveCount(0);
        await expect(page.locator('#investment-currency')).toHaveValue('USD');
        await expect(page.locator('#investment-extra-filters')).toHaveAttribute('open');
        await page.locator('#investment-date-from').fill(data.yesterday);
        await page.locator('#investment-date-to').press('Tab');
        await page.keyboard.press('Shift+Tab');
        await expect(page.getByRole('alert')).toHaveCount(0);
        await expect(page.locator('#investment-movements li')).toHaveCount(1);
        await page.locator('#investment-currency').selectOption('BRL');
        await expect(page.locator('#investment-movements')).toContainText('No matching operations.');
        await page.getByRole('link', { name: 'Clear filters', exact: true }).press('Enter');
        await expect(page.locator('#investment-currency')).toHaveValue('');
        await expect(page.locator('#investment-movements li')).toHaveCount(1);
        await page.setViewportSize({ width: 390, height: 740 });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: info.outputPath(`filters-mobile-${theme}.png`), fullPage: true });
    });
}

test('Portuguese mobile investment diagnostics and filters work without JavaScript', async ({ page, browser }, info) => {
    const data = await seed(page, info);
    await page.context().addCookies([{ name: 'django_language', value: 'pt-br', url: new URL(page.url()).origin }]);
    const context = await browser.newContext({ storageState: await page.context().storageState(),
        javaScriptEnabled: false, viewport: { width: 390, height: 740 } });
    try {
        const mobile = await context.newPage();
        await mobile.goto('/investments/');
        await expect(mobile.locator('#investment-fx-warning')).toHaveCount(0);
        await expect(mobile.locator('#investment-total')).toContainText('550,00');
        await mobile.goto('/analytics/investments/');
        const warning = mobile.locator('#investment-chart-fx-warning');
        await warning.locator('summary').press('Enter');
        await expect(warning).toContainText('Posição inicial:');
        await warning.getByRole('link', { name: 'Abrir operação' }).press('Enter');
        const capture = mobile.locator('#id_capture_missing_fx');
        await expect(capture).not.toBeChecked();
        await capture.press('Space');
        await mobile.getByRole('button', { name: 'Salvar', exact: true }).press('Enter');
        await expect(mobile.getByRole('alert')).toContainText('Primeiro, cadastre uma taxa de câmbio');
        await expect(capture).toBeChecked();
        await mobile.goto('/investments/operations/');
        await mobile.locator('#investment-extra-filters summary').press('Enter');
        await mobile.locator('#investment-currency').selectOption('USD');
        await mobile.locator('#investment-date-from').fill(data.yesterday);
        await mobile.locator('#investment-date-to').fill(data.yesterday);
        await mobile.getByRole('button', { name: 'Filtrar', exact: true }).press('Enter');
        await expect(mobile.locator('#investment-movements li')).toHaveCount(1);
        expect(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await mobile.screenshot({ path: info.outputPath('fx-native-pt.png'), fullPage: true });
    } finally { await context.close(); }
});
