// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { selectChoice } = require('./helpers/forms');

async function post(page, path, fields) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {
        form: { csrfmiddlewaretoken: csrf, ...fields },
        headers: { Referer: response.url() }, maxRedirects: 0,
    });
    expect(saved.status(), await saved.text()).toBe(302);
}

async function seed(page, info) {
    const username = `bank-integrity-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', { username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' });
    await post(page, '/banking/create/', { name: 'Integrity bank' });
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    for (const [name, amount] of [['Integrity source', '1000'], ['Integrity target', '0']]) {
        await post(page, '/banking/accounts/create/', { bank, name, currency: 'BRL',
            opening_balance: amount, opening_date: '2026-01-15', reserved_amount: '0', planning_enabled: 'on' });
    }
    await page.goto('/banking/transfers/create/');
    const source = await page.locator('#id_source_account option').filter({ hasText: 'Integrity source' }).getAttribute('value');
    const target = await page.locator('#id_destination_account option').filter({ hasText: 'Integrity target' }).getAttribute('value');
    await post(page, '/investments/products/create/', { bank, name: 'Integrity product', purpose: 'INVESTMENT' });
    await page.goto('/investments/assets/create/');
    const product = await page.locator('#id_opening_product option').filter({ hasText: 'Integrity product' }).getAttribute('value');
    await post(page, '/investments/assets/create/', { name: 'Integrity holding', code: 'INTEGRITY',
        asset_class: 'LIQUIDITY', currency: 'BRL', valuation_mode: 'MONETARY',
        opening_balance: '0', opening_quantity: '0', opening_unit_price: '0' });
    await page.goto('/investments/create/');
    const asset = await page.locator('#id_asset option').filter({ hasText: 'Integrity holding' }).getAttribute('value');
    return { bank, source, target, product, asset };
}

async function expectBalances(page, ids, source, target) {
    // Inspect cash independently while retaining the bound invalid form and
    // its keyboard context in the original page.
    const audit = await page.context().newPage();
    try {
        await audit.goto(`/banking/${ids.bank}/`);
        await expect(audit.locator(`#account-row-${ids.source} [data-account-balance]`))
            .toHaveText(new RegExp(`BRL\\s*${source}[,.]00`));
        await expect(audit.locator(`#account-row-${ids.target} [data-account-balance]`))
            .toHaveText(new RegExp(`BRL\\s*${target}[,.]00`));
    } finally {
        await audit.close();
    }
}

async function submitTransferByKeyboard(page) {
    await page.locator('#id_notes').focus();
    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeFocused();
    await page.keyboard.press('Enter');
}

async function expectTransferFields(page, ids, destinationAmount, day) {
    await expect(page.locator('#id_source_account')).toHaveValue(ids.source);
    await expect(page.locator('#id_destination_account')).toHaveValue(ids.target);
    await expect(page.locator('#id_source_amount')).toHaveValue('100');
    await expect(page.locator('#id_destination_amount')).toHaveValue(destinationAmount);
    await expect(page.locator('#id_date')).toHaveValue(day);
    await expect(page.locator('#id_notes')).toHaveValue('Keyboard integrity transfer');
}

async function transferRecovery(page, ids, info, native = false) {
    await page.goto('/banking/transfers/create/');
    if (native) {
        await expect(page.locator('#id_source_account')).toBeVisible();
        await expect(page.locator('#id_source_account-search')).toHaveCount(0);
    }
    await selectChoice(page.locator('#id_source_account'), ids.source);
    await selectChoice(page.locator('#id_destination_account'), ids.target);
    await page.locator('#id_source_amount').fill('100');
    await page.locator('#id_destination_amount').fill('150');
    await page.locator('#id_date').fill('15/01/2026');
    await page.locator('#id_notes').fill('Keyboard integrity transfer');
    await submitTransferByKeyboard(page);
    await expect(page.locator('#id_destination_amount-error-1')).toContainText(
        'Transfers in the same currency require equal source and destination amounts.');
    await expect(page.locator('#id_destination_amount')).toHaveAttribute('aria-invalid', 'true');
    await expectTransferFields(page, ids, '150', '15/01/2026');
    await expectBalances(page, ids, '1[.,\\s]000', '0');
    await page.locator('#id_destination_amount').focus();
    await expect(page.locator('#id_destination_amount')).toBeFocused();
    if (!native) {
        expect(await page.locator('#id_destination_amount').evaluate(element => getComputedStyle(element).boxShadow)).not.toBe('none');
    }
    await page.screenshot({ path: info.outputPath(`unequal-transfer-${native ? 'native' : 'enhanced'}.png`), fullPage: true });

    await page.locator('#id_destination_amount').fill('100');
    await page.locator('#id_date').fill('14/01/2026');
    await submitTransferByKeyboard(page);
    await expect(page.locator('#id_date-error-1')).toContainText('The operation cannot precede the account opening balance date.');
    await expectTransferFields(page, ids, '100', '14/01/2026');
    await expectBalances(page, ids, '1[.,\\s]000', '0');
    await page.locator('#id_date').fill('15/01/2026');
    await submitTransferByKeyboard(page);
    await expect(page).toHaveURL(/\/banking\/$/);
    await expectBalances(page, ids, '900', '100');
}

async function investmentRecovery(page, ids, native = false) {
    await page.goto('/investments/create/');
    await selectChoice(page.locator('#id_product'), ids.product);
    await selectChoice(page.locator('#id_asset'), ids.asset);
    await page.locator('#id_kind').selectOption('DEPOSIT');
    await page.locator('#id_date').fill('14/01/2026');
    await page.locator('#id_amount').fill('25');
    await page.locator('#id_funding_source').selectOption('ACCOUNT');
    await selectChoice(page.locator('#id_source_account'), ids.source);
    // Monetary operations derive their cash leg from the entered amount on
    // the server. Enhanced forms hide the separate unit-operation control;
    // the native fallback can leave that optional control empty as well.
    if (!native) await expect(page.locator('#cash-fields')).toBeHidden();
    await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
    await expect(page.locator('#id_date-error-1')).toContainText('The operation cannot precede the account opening balance date.');
    await expect(page.locator('#id_product')).toHaveValue(ids.product);
    await expect(page.locator('#id_asset')).toHaveValue(ids.asset);
    await expect(page.locator('#id_kind')).toHaveValue('DEPOSIT');
    await expect(page.locator('#id_source_account')).toHaveValue(ids.source);
    await expect(page.locator('#id_amount')).toHaveValue('25');
    if (!native) await expect(page.locator('#cash-fields')).toBeHidden();
    await expectBalances(page, ids, '900', '100');
    await page.locator('#id_date').fill('15/01/2026');
    await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
    await expect(page).toHaveURL(/\/investments\/operations\/$/);
    await expect(page.locator('#investment-movements ul > li')).toHaveCount(1);
    await expectBalances(page, ids, '875', '100');
}

for (const theme of ['light', 'dark']) {
    test(`bank cash integrity errors preserve keyboard choices and recover (${theme})`, async ({ page }, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const ids = await seed(page, info);
        await transferRecovery(page, ids, info);
        await investmentRecovery(page, ids);
    });
}

test('bank transfer and investment integrity recover without JavaScript', async ({ browser }, info) => {
    const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
    try {
        const page = await context.newPage();
        const ids = await seed(page, info);
        await transferRecovery(page, ids, info, true);
        await investmentRecovery(page, ids, true);
    } finally {
        await context.close();
    }
});
