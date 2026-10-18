// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {selectChoice} = require('./helpers/forms');

async function post(page, path, data) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...data},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(saved.status(), await saved.text()).toBe(302);
}
async function signup(page, info) {
    const username = `investment-subareas-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    await post(page, '/accounts/settings/', {base_currency: 'BRL', date_format: 'DMY'});
    await post(page, '/banking/create/', {name: 'Local bank', color: '#315D50'});
}
async function fits(page) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

for (const theme of ['light', 'dark']) for (const width of [1280, 390]) {
    test(`complete investment registration, catalogue and price consultation (${theme}, ${width})`, async ({page}, info) => {
        test.setTimeout(60000);
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({width, height: 900});
        await signup(page, info);
        await page.goto('/investments/settings/');
        await page.locator('#investment-products').getByRole('link', {name: 'New product', exact: true}).press('Enter');
        await expect(page.getByRole('group', {name: 'Institution and purpose', exact: true})).toBeVisible();
        await selectChoice(page.locator('#id_bank'), {label: 'Local bank'});
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.locator('#id_name')).toHaveAttribute('aria-invalid', 'true');
        await page.locator('#id_name').fill('Brokerage');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).toHaveURL(/\/investments\/settings\/#investment-products$/);
        await page.locator('#investment-assets').getByRole('link', {name: 'New asset', exact: true}).press('Enter');
        await expect(page.getByRole('group', {name: 'Investment details', exact: true})).toBeVisible();
        await expect(page.getByRole('group', {name: 'Valuation and opening position', exact: true})).toBeVisible();
        await expect(page.locator('#id_valuation_mode')).toHaveValue('');
        await expect(page.locator('#id_opening_balance')).toBeHidden();
        await page.locator('#id_name').fill('Fractional fund');
        await page.locator('#id_code').fill('FRACTION');
        await page.locator('#id_asset_class').selectOption('EQUITY');
        await page.locator('#id_currency').selectOption('BRL');
        await page.locator('#id_valuation_mode').focus();
        await page.keyboard.press('End');
        await expect(page.locator('#id_opening_quantity')).toBeVisible();
        await expect(page.locator('#id_opening_unit_price')).toBeHidden();
        await page.locator('#id_opening_quantity').fill('1.12345678');
        await page.keyboard.press('Tab');
        await expect(page.getByRole('button', {name: 'Explain Opening unit price', exact: true})).toBeFocused();
        await page.keyboard.press('Tab');
        await expect(page.locator('#id_opening_unit_price')).toBeFocused();
        await page.locator('#id_opening_unit_price').fill('100.87654321');
        const product = await page.locator('#id_opening_product option').filter({hasText: 'Brokerage'}).getAttribute('value');
        await selectChoice(page.locator('#id_opening_product'), product);
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.locator('#id_opening_date')).toHaveAttribute('aria-invalid', 'true');
        await expect(page.locator('#id_opening_quantity')).toHaveValue('1.12345678');
        await expect(page.locator('#id_opening_unit_price')).toHaveValue('100.87654321');
        await page.locator('#id_opening_date').fill('01/01/2020');
        await fits(page);
        await page.screenshot({path: info.outputPath(`complete-registration-${theme}-${width}.png`), fullPage: true});
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).toHaveURL(/\/investments\/settings\/#investment-assets$/);
        const row = page.locator('#investment-active-assets > li').filter({hasText: 'Fractional fund (FRACTION)'});
        const asset = (await row.getAttribute('id')).replace('asset-', '');
        await expect(page.locator('#investment-products .bank-marker')).toHaveAttribute('style', /#315D50/);
        await row.getByRole('link', {name: 'Edit', exact: true}).press('Enter');
        await expect(page.locator('main input[name="next"]')).toHaveValue(`/investments/settings/#asset-${asset}`);
        await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
        await expect(page).toHaveURL(new RegExp(`/investments/settings/#asset-${asset}$`));
        const menu = row.locator('details.compact-menu');
        await menu.locator(':scope > summary').hover();
        await expect(menu).not.toHaveAttribute('open', '');
        await menu.locator(':scope > summary').focus();
        await expect(menu).not.toHaveAttribute('open', '');
        await page.keyboard.press('Space');
        await expect(menu).toHaveAttribute('open', '');
        await page.keyboard.press('Tab');
        await expect(menu.getByRole('link', {name: 'Observed prices', exact: true})).toBeFocused();
        await page.keyboard.press('Escape');
        await expect(menu).not.toHaveAttribute('open', '');
        await fits(page);
        await page.screenshot({path: info.outputPath(`catalogue-${theme}-${width}.png`), fullPage: true});
        await menu.locator(':scope > summary').press('Enter');
        await menu.getByRole('link', {name: 'Observed prices', exact: true}).press('Enter');
        await expect(page.locator('#investment-price-asset')).toHaveValue(asset);
        await page.getByRole('link', {name: 'New observation', exact: true}).press('Enter');
        await expect(page.locator('#id_asset')).toHaveValue(asset);
        await page.locator('#id_date').fill('01/09/2021');
        await page.locator('#id_unit_price').fill('123.12345678');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.locator('#id_source')).toHaveAttribute('aria-invalid', 'true');
        await expect(page.locator('#id_unit_price')).toHaveValue('123.12345678');
        await page.locator('#id_source').fill('Local statement');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname === '/investments/prices/' && url.searchParams.get('asset') === asset);
        await expect(page.locator('#investment-price-results')).toContainText(/123[,.]12345678/);

        await post(page, '/investments/assets/create/', {name: 'Second fund', code: 'SECOND', asset_class: 'EQUITY',
            currency: 'BRL', valuation_mode: 'UNITS', opening_balance: '0', opening_quantity: '0', opening_unit_price: '0'});
        await page.goto('/investments/prices/');
        const second = await page.locator('#investment-price-asset option').filter({hasText: 'Second fund'}).getAttribute('value');
        await post(page, '/investments/prices/create/', {asset: second, date: '2021-09-01', unit_price: '200', source: 'Second statement'});
        await page.goto(`/investments/prices/?asset=${asset}`);
        await selectChoice(page.locator('#investment-price-asset'), second);
        await expect(page).toHaveURL(url => url.searchParams.get('asset') === second);
        await expect(page.locator('#investment-price-results')).toContainText('Second statement');
        await expect(page.locator('#investment-price-results')).not.toContainText('Local statement');
        await expect(page.locator('#investment-price-asset-search')).toBeFocused();
        await expect(page.locator('#departure-confirm')).toBeHidden();
        const create = new URL(await page.locator('#investment-price-create').getAttribute('href'), page.url());
        expect(create.searchParams.get('asset')).toBe(second);
        expect(create.searchParams.get('next')).toBe(`/investments/prices/?asset=${second}`);
        await page.goBack();
        await expect(page.locator('#investment-price-asset')).toHaveValue(asset);
        await expect(page.locator('#investment-price-results')).toContainText('Local statement');
        await page.goForward();
        await expect(page.locator('#investment-price-asset')).toHaveValue(second);
        await page.getByRole('link', {name: 'Clear filters', exact: true}).press('Enter');
        await expect(page).toHaveURL(/\/investments\/prices\/$/);
        await expect(page.locator('#investment-price-results tbody tr')).toHaveCount(2);
        await fits(page);
        await page.screenshot({path: info.outputPath(`prices-${theme}-${width}.png`), fullPage: true});
        await page.goto('/investments/prices/?asset=invalid');
        await expect(page.locator('#investment-price-asset')).toHaveAttribute('aria-invalid', 'true');
        await expect(page.locator('#investment-price-results')).toContainText('No observed prices.');
        await page.getByRole('link', {name: 'Clear filters', exact: true}).press('Enter');
        await expect(page.locator('#investment-price-results tbody tr')).toHaveCount(2);
        await page.goto(`/investments/positions/${product}/${asset}/`);
        const breakdown = page.locator('details').filter({has: page.locator('summary').filter({hasText: 'Cost, price and results'})});
        await expect(breakdown).toHaveAttribute('open', '');
        await expect(breakdown).toContainText('Realized result');
        await expect(breakdown).toContainText('Local statement');
        await fits(page);
        await page.screenshot({path: info.outputPath(`position-${theme}-${width}.png`), fullPage: true});
        expect(errors).toEqual([]);
    });
}

test('complete investment configuration and price filters keep their native mobile path', async ({page, browser}, info) => {
    await signup(page, info);
    await page.goto('/investments/products/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/investments/products/create/', {bank, name: 'Native brokerage', purpose: 'INVESTMENT'});
    const context = await browser.newContext({storageState: await page.context().storageState(),
        javaScriptEnabled: false, viewport: {width: 390, height: 844}});
    try {
        await context.addCookies([{name: 'django_language', value: 'pt-br', url: new URL(page.url()).origin}]);
        const native = await context.newPage();
        await native.goto('/investments/settings/');
        await native.locator('#investment-assets').getByRole('link', {name: 'Novo ativo', exact: true}).press('Enter');
        await expect(native.getByRole('group', {name: 'Dados do investimento', exact: true})).toBeVisible();
        await native.locator('#id_name').fill('Native units');
        await native.locator('#id_code').fill('NATIVE');
        await native.locator('#id_asset_class').selectOption('EQUITY');
        await native.locator('#id_currency').selectOption('BRL');
        await native.locator('#id_valuation_mode').selectOption('UNITS');
        await native.locator('#id_opening_quantity').fill('1.12345678');
        await native.locator('#id_opening_unit_price').fill('2.23456789');
        await native.locator('#id_opening_product').selectOption({label: 'Local bank - Native brokerage'});
        await native.getByRole('button', {name: 'Salvar', exact: true}).press('Enter');
        await expect(native.locator('#id_opening_date')).toHaveAttribute('aria-invalid', 'true');
        await expect(native.locator('#id_opening_quantity')).toHaveValue('1.12345678');
        await native.locator('#id_opening_date').fill('01/01/2020');
        await native.getByRole('button', {name: 'Salvar', exact: true}).press('Enter');
        await expect(native).toHaveURL(/\/investments\/settings\/#investment-assets$/);
        const row = native.locator('#investment-active-assets > li');
        const asset = (await row.getAttribute('id')).replace('asset-', '');
        await row.locator('details.compact-menu > summary').press('Enter');
        await row.getByRole('link', {name: 'Cotações observadas', exact: true}).press('Enter');
        await expect(native.locator('#investment-price-asset')).toHaveValue(asset);
        await native.locator('#investment-price-asset').selectOption('');
        await native.locator('[data-live-submit]').press('Enter');
        await expect(native).toHaveURL(/\/investments\/prices\/\?asset=$/);
        await fits(native);
        await native.screenshot({path: info.outputPath('prices-native-mobile.png'), fullPage: true});
    } finally { await context.close(); }
});
