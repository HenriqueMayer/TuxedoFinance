// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const fs = require('node:fs/promises');
const {selectChoice} = require('./helpers/forms');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...values},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(saved.status(), await saved.text()).toBe(302);
}
async function fixture(page, info) {
    const username = `investment-depth-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    await post(page, '/accounts/settings/', {base_currency: 'BRL', date_format: 'DMY'});
    const bankName = 'Institution' + 'X'.repeat(85);
    const productName = 'Portfolio' + 'Q'.repeat(135);
    const assetName = 'Holding' + 'Z'.repeat(90);
    await post(page, '/banking/create/', {name: bankName, color: '#315D50'});
    await page.goto('/investments/products/create/');
    const bank = await page.locator('#id_bank option').filter({hasText: bankName}).getAttribute('value');
    for (let i = 0; i < 20; i++) await post(page, '/investments/products/create/', {
        bank, name: i === 19 ? productName : `Investment product ${String(i).padStart(2, '0')}`, purpose: 'INVESTMENT'});
    await page.goto('/investments/assets/create/');
    const product = await page.locator('#id_opening_product option').filter({hasText: productName}).getAttribute('value');
    for (let i = 0; i < 36; i++) await post(page, '/investments/assets/create/', {
        name: i === 35 ? assetName : `Catalogue asset ${String(i).padStart(2, '0')}`,
        code: `AUDIT${i}`, asset_class: 'EQUITY', currency: 'BRL', valuation_mode: 'UNITS',
        opening_quantity: '1.12345678', opening_unit_price: '10.87654321', opening_balance: '0',
        opening_product: product, opening_date: '2020-01-01'});
    await page.goto('/investments/settings/');
    const assetRow = page.locator('#investment-active-assets > li').filter({hasText: '(AUDIT35)'});
    const asset = (await assetRow.getAttribute('id')).replace('asset-', '');
    await post(page, '/investments/prices/create/', {asset, date: '2021-01-01',
        unit_price: '12.12345678', source: 'A local statement with a longer source description for a dated observed unit price'});
    return {bank, product, asset, bankName, productName, assetName};
}
async function textBounds(locator) {
    return locator.evaluate(element => {
        const range = document.createRange(); range.selectNodeContents(element);
        const text = range.getBoundingClientRect();
        return {left: text.left, right: text.right, width: text.width,
            viewport: innerWidth, scroll: document.documentElement.scrollWidth};
    });
}

for (const theme of ['light', 'dark']) {
    test(`deep investment catalogue and complete form review (${theme})`, async ({page}, info) => {
        test.setTimeout(90000);
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const data = await fixture(page, info);
        const measurements = [];
        for (const width of [1280, 390]) {
            await page.setViewportSize({width, height: 900});
            await page.goto('/investments/settings/');
            await expect(page.locator('#investment-products [id^="product-"]')).toHaveCount(20);
            await expect(page.locator('#investment-active-assets > li')).toHaveCount(36);
            const bank = page.locator('#investment-products h3').filter({hasText: data.bankName});
            const product = page.locator(`#product-${data.product} strong`);
            const row = page.locator(`#asset-${data.asset}`);
            measurements.push({width, bank: await textBounds(bank), product: await textBounds(product),
                asset: await textBounds(row.locator('strong'))});
            await page.screenshot({path: info.outputPath(`catalogue-top-${theme}-${width}.png`)});
            const shortRow = page.locator('#investment-products li[id^="product-"]').first();
            const shortName = await shortRow.locator('strong').boundingBox();
            const shortAction = await shortRow.getByRole('link', {name: 'Edit', exact: true}).boundingBox();
            // When the name and actions fit, the catalogue keeps one row.
            expect(shortAction.y).toBeLessThan(shortName.y + shortName.height + 12);
            await shortRow.screenshot({path: info.outputPath(`catalogue-short-row-${theme}-${width}.png`)});
            const menu = row.locator('details.compact-menu');
            await menu.locator(':scope > summary').press('Enter');
            await page.keyboard.press('Tab');
            await expect(menu.getByRole('link', {name: 'Observed prices', exact: true})).toBeFocused();
            measurements[measurements.length - 1].menu = await textBounds(menu.locator('.secondary-actions-panel'));
            const menuTarget = await menu.getByRole('link', {name: 'Observed prices', exact: true}).boundingBox();
            expect(menuTarget.height).toBeGreaterThanOrEqual(44);
            expect(menuTarget.y).toBeGreaterThanOrEqual(64);
            expect(menuTarget.y + menuTarget.height).toBeLessThanOrEqual(width < 640 ? 827 : 900);
            await page.screenshot({path: info.outputPath(`catalogue-row-menu-${theme}-${width}.png`)});
            await page.keyboard.press('Escape');
            await row.getByRole('link', {name: 'Edit', exact: true}).press('Enter');
            await expect(page.locator('#id_name')).toHaveValue(data.assetName);
            await page.locator('#id_code').fill('AUDIT0');
            await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
            await expect(page.locator('#id_code')).toHaveAttribute('aria-invalid', 'true');
            await expect(page.locator('#id_opening_quantity')).toHaveValue('1.12345678');
            await expect(page.locator('#id_opening_unit_price')).toHaveValue('10.87654321');
            await page.locator('#id_opening_product-search').focus();
            const openingChoice = page.locator('#id_opening_product-search').locator('..').getByRole('option').first();
            expect((await openingChoice.boundingBox()).height).toBeGreaterThanOrEqual(44);
            measurements[measurements.length - 1].choice = await textBounds(openingChoice);
            measurements[measurements.length - 1].choiceOverflow = await openingChoice.evaluate(element =>
                Math.max(element.scrollWidth - element.clientWidth, ...Array.from(element.children, child => child.scrollWidth - child.clientWidth)));
            await page.screenshot({path: info.outputPath(`complete-bound-${theme}-${width}.png`)});
            await page.locator('#id_opening_product-search').fill(data.productName);
            await page.locator('#id_opening_product-search').press('ArrowDown');
            await page.locator('#id_opening_product-search').press('Enter');
            await expect(page.locator('#id_opening_product')).toHaveValue(data.product);
            await expect(page.locator('#id_opening_product-search')).toBeFocused();
            await page.goto('/investments/assets/create/');
            await page.locator('#id_valuation_mode').selectOption('UNITS');
            await page.locator('#id_opening_quantity').fill('2.12345678');
            await page.locator('#id_opening_unit_price').fill('11.12345678');
            await selectChoice(page.locator('#id_opening_product'), data.product);
            await page.locator('#id_opening_date').fill('01/01/2020');
            await page.locator('#id_valuation_mode').selectOption('MONETARY');
            await expect(page.locator('#id_opening_quantity')).toHaveValue('0');
            await expect(page.locator('#id_opening_product')).toHaveValue('');
            await expect(page.locator('#id_opening_date')).toHaveValue('');
            await page.locator('#id_opening_balance').fill('100');
            await page.screenshot({path: info.outputPath(`complete-monetary-${theme}-${width}.png`)});
            await page.goto(`/investments/positions/${data.product}/${data.asset}/`);
            measurements[measurements.length - 1].position = await textBounds(page.locator('main h1'));
            await page.screenshot({path: info.outputPath(`position-${theme}-${width}.png`)});
            await page.getByRole('link', {name: 'Update', exact: true}).press('Enter');
            await expect(page).toHaveURL(url => url.pathname === `/investments/positions/${data.product}/${data.asset}/update/`);
            measurements[measurements.length - 1].update = await textBounds(page.locator('main h1'));
            await page.screenshot({path: info.outputPath(`position-update-${theme}-${width}.png`)});
            await page.goto(`/investments/prices/?asset=${data.asset}`);
            const search = page.locator('#investment-price-asset-search');
            await search.fill('Catalogue asset');
            await search.press('ArrowDown');
            await page.screenshot({path: info.outputPath(`price-choice-${theme}-${width}.png`)});
            await search.press('Enter');
            await expect(page.locator('#investment-price-asset')).not.toHaveValue(data.asset);
            await expect(page.locator('#departure-confirm')).toBeHidden();
        }
        await info.attach('current-viewport-measurements', {body: JSON.stringify(measurements, null, 2), contentType: 'application/json'});
        await fs.writeFile(info.outputPath('viewport-measurements.json'), JSON.stringify(measurements, null, 2));
        expect(errors).toEqual([]);
        expect(measurements.map(item => item.choiceOverflow)).toEqual([0, 0]);
        expect(measurements.flatMap(item => ['bank', 'product', 'asset', 'position', 'update', 'menu', 'choice']
            .filter(name => item[name].right > item.width + 1 || item[name].left < -1 || item[name].scroll > item.width)
            .map(name => ({width: item.width, name, ...item[name]})))).toEqual([]);
    });
}
