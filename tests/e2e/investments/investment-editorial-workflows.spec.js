// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function post(page, path, fields, csrfPath = path) {
    const response = await page.request.get(csrfPath);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...fields},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(saved.status(), await saved.text()).toBe(302);
}

async function seed(page, info) {
    const username = `investment-editorial-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    await post(page, '/accounts/settings/', {base_currency: 'BRL', date_format: 'DMY'});
    await post(page, '/banking/create/', {name: 'Editorial bank', color: '#315D50'});
    await page.goto('/investments/products/create/');
    const bank = await page.locator('#id_bank option').filter({hasText: /^Editorial bank$/}).getAttribute('value');
    await post(page, '/investments/products/create/', {bank, name: 'Portfolio', purpose: 'INVESTMENT'});
    await post(page, '/investments/products/create/', {bank, name: 'Cash', purpose: 'MONTHLY_CASH'});
    await page.goto('/investments/assets/create/');
    const portfolio = await page.locator('#id_opening_product option').filter({hasText: 'Portfolio'}).getAttribute('value');
    const cashProduct = await page.locator('#id_opening_product option').filter({hasText: /Cash$/}).getAttribute('value');
    const common = {opening_date: '2020-01-01', opening_quantity: '0', opening_unit_price: '0',
        opening_balance: '0', currency: 'BRL', asset_class: 'LIQUIDITY'};
    await post(page, '/investments/assets/create/', {...common, name: 'Local share', code: 'LOCAL',
        valuation_mode: 'UNITS', asset_class: 'EQUITY', opening_product: portfolio,
        opening_quantity: '2', opening_unit_price: '200'});
    await post(page, '/investments/assets/create/', {...common, name: 'Cash reserve', code: 'CASH',
        valuation_mode: 'MONETARY', opening_product: cashProduct, opening_balance: '100'});
    await post(page, '/investments/assets/create/', {...common, name: 'Foreign holding', code: 'FOREIGN',
        valuation_mode: 'MONETARY', opening_product: portfolio, opening_balance: '10', currency: 'USD'});
    await post(page, '/banking/exchange-rates/create/', {from_currency: 'USD', to_currency: 'BRL',
        rate: '5', effective_date: '2020-01-01'});
    await page.goto('/investments/create/');
    const cashAsset = await page.locator('#id_asset option').filter({hasText: /^Cash reserve/}).getAttribute('value');
    const share = await page.locator('#id_asset option').filter({hasText: /^Local share/}).getAttribute('value');
    return {cashProduct, cashAsset, portfolio, share};
}

async function fits(page) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

for (const theme of ['light', 'dark']) for (const width of [1280, 390]) {
    test(`investment scopes, compact entries and contextual recovery (${theme}, ${width})`, async ({page}, info) => {
        // This journey visits several native editors after one owned fixture.
        test.setTimeout(60000);
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({width, height: 900});
        const data = await seed(page, info);
        await page.goto('/analytics/investments/?total_offset=-1&flow_offset=0');
        const performance = page.locator('#investment-performance');
        const cost = performance.locator('dd').first();
        await expect(cost).toContainText(/550[,.]00/);
        await expect(performance).toContainText('Results are limited');
        const scope = page.locator('#investment-chart-scope');
        await scope.focus();
        await scope.press('End');
        await expect(page).toHaveURL(url => url.searchParams.get('scope') === 'cash');
        await expect(cost).toContainText(/100[,.]00/);
        await expect(performance).not.toContainText('Results are limited');
        await expect(scope).toBeFocused();
        expect(new URL(page.url()).searchParams.get('total_offset')).toBe('-1');
        await expect(page.locator('#departure-confirm')).toBeHidden();
        await page.screenshot({path: info.outputPath(`investment-analysis-${theme}-${width}.png`)});
        await page.goBack();
        await expect(cost).toContainText(/550[,.]00/);
        await page.goForward();
        await expect(cost).toContainText(/100[,.]00/);

        const rateOrigin = '/investments/?scope=portfolio&q=Foreign';
        await page.goto(rateOrigin);
        const marker = page.locator('#investment-position-list article:visible .investment-icon-action').first();
        await expect(marker).toContainText('💰');
        await page.locator('#position-value-details > summary').press('Enter');
        const rate = page.locator('#position-value-details a[href*="exchange-rates/"][href*="/edit/"]');
        await rate.press('Enter');
        const rateDestination = rateOrigin + '#position-value-summary';
        await expect(page.locator('main input[name="next"]')).toHaveValue(rateDestination);
        await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === rateDestination);

        const origin = '/investments/?scope=cash&q=Cash';
        await page.goto(origin);
        let row = page.locator('#investment-position-list article:visible');
        await row.getByRole('link', {name: 'Update', exact: true}).press('Enter');
        await page.getByRole('link', {name: 'Record yield', exact: true}).press('Enter');
        const rowOrigin = `${origin}#position-${data.cashProduct}-${data.cashAsset}${width < 640 ? '-mobile' : ''}`;
        await expect(page.locator('main input[name="next"]')).toHaveValue(rowOrigin);
        await expect(page.locator('#id_amount')).toBeHidden();
        await page.getByRole('radio', {name: 'Enter the yield amount', exact: true}).press('Space');
        await page.locator('#id_date').fill('10/01/2026');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.locator('#id_amount')).toHaveAttribute('aria-invalid', 'true');
        await expect(page.locator('main input[name="next"]')).toHaveValue(rowOrigin);
        await page.locator('#id_amount').fill('5');
        await fits(page);
        await page.screenshot({path: info.outputPath(`investment-operation-${theme}-${width}.png`), fullPage: true});
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === rowOrigin);
        row = page.locator('#investment-position-list article:visible');
        await expect(row).toContainText(/105[,.]00/);
        await expect(row).toBeInViewport();

        await page.locator('main').getByRole('link', {name: 'Add investment', exact: true}).first().press('Enter');
        await expect(page.locator('#id_new_institution')).not.toBeChecked();
        await expect(page.locator('#id_valuation_mode')).toHaveValue('');
        await page.locator('#id_valuation_mode').focus();
        await page.keyboard.press('End');
        await page.keyboard.press('Tab');
        await expect(page.locator('#id_opening_quantity')).toBeVisible();
        await expect(page.locator('#id_opening_unit_price')).toBeVisible();
        await fits(page);
        await page.screenshot({path: info.outputPath(`investment-guided-${theme}-${width}.png`), fullPage: true});
        await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
        await expect(page.locator('#departure-confirm')).toBeVisible();
        await page.locator('[data-departure-leave]').press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);

        const priceOrigin = `/investments/prices/?asset=${data.share}&page=1`;
        await page.goto(priceOrigin);
        await expect(page.getByText('Local share · LOCAL', {exact: false}).first()).toBeVisible();
        await page.getByRole('link', {name: 'New observation', exact: true}).press('Enter');
        await expect(page.locator('#id_asset')).toHaveValue(data.share);
        await page.locator('#id_date').fill('10/01/2026');
        await page.locator('#id_unit_price').fill('123.12345678');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.locator('#id_source')).toHaveAttribute('aria-invalid', 'true');
        await expect(page.locator('#id_unit_price')).toHaveValue('123.12345678');
        await expect(page.locator('main input[name="next"]')).toHaveValue(priceOrigin);
        await page.locator('#id_source').fill('Local statement');
        await fits(page);
        await page.screenshot({path: info.outputPath(`investment-price-${theme}-${width}.png`), fullPage: true});
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search === priceOrigin);
        await page.locator('tbody').getByRole('link', {name: 'Edit', exact: true}).press('Enter');
        await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search === priceOrigin);
        await page.getByRole('link', {name: 'Clear filters', exact: true}).press('Enter');
        await expect(page).toHaveURL(/\/investments\/prices\/$/);
        await fits(page);
        expect(errors).toEqual([]);
    });
}

test('investment result scopes and price editors retain native mobile submission', async ({browser}, info) => {
    test.setTimeout(60000);
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 390, height: 900}});
    try {
        const page = await context.newPage();
        const data = await seed(page, info);
        await page.goto('/analytics/investments/?total_offset=-1&flow_offset=0');
        await page.locator('#investment-chart-scope').selectOption('cash');
        await page.getByRole('button', {name: 'Filter', exact: true}).press('Enter');
        await expect(page.locator('#investment-performance dd').first()).toContainText(/100[,.]00/);
        const origin = `/investments/prices/?asset=${data.share}`;
        await page.goto(origin);
        await page.getByRole('link', {name: 'New observation', exact: true}).press('Enter');
        await expect(page.locator('#id_asset')).toHaveValue(data.share);
        await page.locator('#id_date').fill('10/01/2026');
        await page.locator('#id_unit_price').fill('123.12345678');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.locator('#id_source')).toHaveAttribute('aria-invalid', 'true');
        await expect(page.locator('#id_unit_price')).toHaveValue('123.12345678');
        await page.locator('#id_source').fill('Native local statement');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);
        await fits(page);
    } finally {
        await context.close();
    }
});

for (const theme of ['light', 'dark']) for (const width of [1280, 390]) {
    test(`archived investment shortcut reveals its configuration record (${theme}, ${width})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({width, height: 900});
        const data = await seed(page, info);
        for (let index = 1; index <= 8; index++) {
            await post(page, '/investments/assets/create/', {name: `Additional holding ${index}`,
                code: `ADD${index}`, valuation_mode: 'MONETARY', asset_class: 'LIQUIDITY', currency: 'BRL',
                opening_balance: '0', opening_quantity: '0', opening_unit_price: '0'});
        }
        await post(page, `/investments/assets/${data.share}/archive/`, {}, '/investments/settings/');
        await page.goto(`/investments/positions/${data.portfolio}/${data.share}/`);
        await page.getByRole('link', {name: 'Review configuration', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.hash === `#asset-${data.share}`);
        await expect(page.locator('#investment-archived-assets')).toHaveAttribute('open', '');
        await expect(page.locator(`#asset-${data.share} strong`)).toBeInViewport();
        await fits(page);
        await page.screenshot({path: info.outputPath(`investment-config-anchor-${theme}-${width}.png`)});
    });
}
