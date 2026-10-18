// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {selectChoice} = require('./helpers/forms');

async function post(page, path, fields) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...fields},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(saved.status(), await saved.text()).toBe(302);
}

async function seed(page, info) {
    const username = `allocation-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    await post(page, '/accounts/settings/', {base_currency: 'BRL', date_format: 'DMY'});
    await post(page, '/banking/create/', {name: 'Allocation bank'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: 'Allocation cash', currency: 'BRL',
        opening_balance: '1000', opening_date: '2025-01-01'});
    await post(page, '/categories/create/', {name: 'Salary', transaction_type: 'INCOME'});
    for (const name of ['Alpha', 'Beta', 'Gamma']) await post(page, '/categories/create/', {name, transaction_type: 'EXPENSE'});
    await page.goto('/transactions/create/');
    const account = await page.locator('#id_bank_account option').last().getAttribute('value');
    const categories = [];
    for (const name of ['Alpha', 'Beta', 'Gamma']) categories.push(await page.locator('#id_category option').filter({hasText: new RegExp(`^${name}$`)}).getAttribute('value'));
    return {account, categories};
}

async function start(page) {
    await page.locator('#id_title').fill('Shared purchase');
    await page.locator('#id_amount').fill('100.00');
    await selectChoice(page.locator('#id_transaction_type'), 'EXPENSE');
    await page.locator('#id_split_categories').press('Space');
}

async function amounts(page, expected) {
    const rows = page.locator('[data-allocation-rows] > [data-split-row]:visible');
    await expect(rows).toHaveCount(expected.length);
    for (let index = 0; index < expected.length; index++) await expect(rows.nth(index).locator('[name$="-amount"]')).toHaveValue(expected[index]);
}

for (const theme of ['light', 'dark']) {
for (const width of [390, 1440]) {
    test(`category allocation distributes cents, fixes edits and recovers caps (${width}, ${theme})`, async ({page}, info) => {
        await page.setViewportSize({width, height: 900});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const data = await seed(page, info);
        await start(page);
        await amounts(page, ['50.00', '50.00']);
        const add = page.getByRole('button', {name: 'Add category', exact: true});
        await expect(add).toHaveAttribute('type', 'button');
        await expect(page.locator('#category-split-fields [data-allocation-add]')).toBeVisible();
        const rowsBox = await page.locator('[data-allocation-rows]').boundingBox();
        const addBox = await add.boundingBox();
        const paymentBox = await page.locator('.entry-payment-section').boundingBox();
        expect(addBox.y - rowsBox.y - rowsBox.height).toBeGreaterThanOrEqual(8);
        expect(addBox.y - rowsBox.y - rowsBox.height).toBeLessThanOrEqual(32);
        expect(addBox.y + addBox.height).toBeLessThanOrEqual(paymentBox.y);
        await page.locator('[data-allocation-rows] > [data-split-row]').last()
            .getByRole('button', {name: 'Remove category', exact: true}).focus();
        await page.keyboard.press('Tab');
        await expect(add).toBeFocused();
        await page.keyboard.press('Tab');
        await expect(page.locator('#id_payment_channel input[value="ACCOUNT"]')).toBeFocused();
        await page.keyboard.press('Shift+Tab');
        await expect(add).toBeFocused();
        await page.keyboard.press('Enter');
        await amounts(page, ['33.34', '33.33', '33.33']);
        await expect(page.locator('#id_splits-2-category-search')).toBeFocused();
        await page.locator('#id_splits-0-amount').fill('25.01');
        await amounts(page, ['25.01', '37.50', '37.49']);
        await page.locator('#id_splits-1-amount').fill('50.00');
        await amounts(page, ['25.01', '50.00', '24.99']);
        await expect(page.locator('[data-allocation-remainder]:visible')).toHaveCount(1);
        await page.locator('#id_splits-1-amount').fill('80.00');
        await expect(page.locator('#id_splits-1-amount')).toHaveValue('80.00');
        await expect(page.locator('[data-allocation-row-error]:visible')).toContainText('74.98');
        await page.locator('#id_title').press('Enter');
        await expect(page.locator('#id_splits-1-amount')).toBeFocused();
        await expect(page.locator('#id_splits-1-amount')).toHaveCSS('border-radius', '8px');
        await page.locator('#id_splits-1-amount').fill('50.00');
        await page.locator('#id_amount').fill('90.00');
        await amounts(page, ['25.01', '50.00', '14.99']);
        await page.locator('[data-split-row]').nth(1).getByRole('button', {name: 'Remove category', exact: true}).press('Enter');
        await amounts(page, ['25.01', '64.99']);
        await expect(page.locator('#id_splits-1-DELETE')).toBeChecked();
        await expect(page.locator('[data-allocation-delete]:visible')).toHaveCount(0);
        await page.getByRole('button', {name: 'Add category', exact: true}).press('Enter');
        await amounts(page, ['25.01', '32.50', '32.49']);
        await page.locator('#id_splits-0-amount').fill('');
        await page.locator('#id_splits-0-amount').press('Tab');
        await amounts(page, ['30.00', '30.00', '30.00']);
        // A deliberate conditional reset removes obsolete alerts, but must not
        // prevent a new recoverable amount error when the section opens again.
        await page.locator('#id_splits-0-amount').fill('90.00');
        await expect(page.locator('[data-allocation-row-error]:visible')).toContainText('89.98');
        await page.locator('#id_split_categories').press('Space');
        await expect(page.locator('[data-allocation-rows]')).toBeHidden();
        await page.locator('#id_split_categories').press('Space');
        await amounts(page, ['45.00', '45.00']);
        await page.locator('#id_splits-0-amount').fill('90.00');
        await expect(page.locator('[data-allocation-row-error]:visible')).toContainText('89.99');
        await expect(page.locator('#id_splits-0-amount')).toHaveValue('90.00');
        await page.locator('#id_splits-0-amount').fill('25.01');
        await amounts(page, ['25.01', '64.99']);
        await page.getByRole('button', {name: 'Add category', exact: true}).press('Enter');
        for (let index = 0; index < 3; index++) await selectChoice(page.locator(`#id_splits-${index}-category`), data.categories[index]);
        const beforeHint = await page.locator('[data-allocation-rows]').boundingBox();
        await expect(page.locator('[data-allocation-remainder]:visible')).toHaveCount(0);
        await page.locator('#id_splits-1-amount').fill('32.50');
        await page.locator('#id_splits-1-amount').press('Tab');
        await amounts(page, ['25.01', '32.50', '32.49']);
        expect(Math.abs((await page.locator('[data-allocation-rows]').boundingBox()).height - beforeHint.height)).toBeLessThan(1);
        const hint = page.locator('[data-allocation-remainder]:visible');
        await expect(hint).toHaveCount(1);
        const labelBox = await page.locator('label[for="id_splits-2-amount"]').boundingBox();
        const hintBox = await hint.boundingBox();
        expect(hintBox.y >= labelBox.y + labelBox.height || hintBox.x >= labelBox.x + labelBox.width).toBe(true);
        if (width === 390) {
            for (let index = 0; index < 3; index++) {
                const row = page.locator('[data-allocation-rows] > [data-split-row]').nth(index);
                const amountBox = await row.locator('[name$="-amount"]').boundingBox();
                const removeBox = await row.getByRole('button', {name: 'Remove category', exact: true}).boundingBox();
                expect(removeBox.x - amountBox.x - amountBox.width).toBeGreaterThanOrEqual(8);
            }
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({path: info.outputPath(`allocation-${width}-${theme}.png`), fullPage: true});
        await page.locator('[data-allocation-rows]').screenshot({path: info.outputPath(`allocation-rows-${width}-${theme}.png`)});
        await page.locator('[data-allocation-section]').screenshot({path: info.outputPath(`allocation-section-${width}-${theme}.png`)});
    });
}
    test(`allocation modes and extra rows survive invalid POST and authorized Back (${theme})`, async ({page}, info) => {
        await page.setViewportSize({width: 390, height: 900});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.addLocatorHandler(page.locator('#departure-confirm[open]'), async () => page.locator('[data-departure-leave]').click());
        const data = await seed(page, info);
        await start(page);
        await page.getByRole('button', {name: 'Add category', exact: true}).press('Enter');
        for (let index = 0; index < 3; index++) await selectChoice(page.locator(`#id_splits-${index}-category`), data.categories[index]);
        await page.locator('#id_splits-0-amount').fill('25.01');
        await selectChoice(page.locator('#id_payment_channel'), 'ACCOUNT');
        await selectChoice(page.locator('#id_bank_account'), data.account);
        await page.locator('#id_date').fill('17/10/2026');
        await page.locator('#id_title').fill('');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.locator('#id_title-error-1')).toBeVisible();
        await amounts(page, ['25.01', '37.50', '37.49']);
        const state = JSON.parse(await page.locator('[data-allocation-state]').inputValue());
        expect(state.rows.map(row => row.mode)).toEqual(['fixed', 'auto', 'auto']);
        await page.locator('#id_title').fill('Shared purchase');
        await page.locator('#app-mobile-home-link').press('Enter');
        await expect(page).toHaveURL(/\/dashboard\/$/);
        await page.goBack();
        await expect(page).toHaveURL(/\/transactions\/create\/$/);
        await amounts(page, ['25.01', '37.50', '37.49']);
        await expect(page.locator('#id_splits-2-category')).toHaveValue(data.categories[2]);
        await page.locator('#id_amount').fill('90.01');
        await amounts(page, ['25.01', '32.50', '32.50']);
        // Adding a category is now earlier in DOM order, but remains a plain
        // button: implicit Enter in a field must still submit the real Save.
        await page.locator('#id_title').press('Enter');
        await expect(page.getByText('Transaction "Shared purchase" created.', {exact: true})).toBeVisible();
        await page.locator('main').getByRole('link', {name: 'Edit', exact: true}).press('Enter');
        await amounts(page, ['25.01', '32.50', '32.50']);
        await page.goto((await page.url()).replace('/edit/', '/split/'));
        await amounts(page, ['25.01', '32.50', '32.50']);
        await expect(page.locator('[data-allocation-remainder]:visible')).toHaveCount(0);
    });

    test(`invalid allocation precision remains editable after an authorized Back (${theme})`, async ({page}, info) => {
        await page.setViewportSize({width: 390, height: 900});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.addLocatorHandler(page.locator('#departure-confirm[open]'), async () => page.locator('[data-departure-leave]').click());
        const data = await seed(page, info);
        await start(page);
        for (let index = 0; index < 2; index++) await selectChoice(page.locator(`#id_splits-${index}-category`), data.categories[index]);
        await selectChoice(page.locator('#id_payment_channel'), 'ACCOUNT');
        await selectChoice(page.locator('#id_bank_account'), data.account);
        await page.locator('#id_date').fill('17/10/2026');
        await page.locator('#id_splits-0-amount').fill('50.001');
        // Exercise the authoritative server recovery path even if progressive
        // validation is bypassed. The request still uses native named fields.
        await Promise.all([
            page.waitForNavigation(),
            page.locator('form[data-category-allocation]').evaluate(form => form.submit()),
        ]);
        await expect(page.locator('#id_splits-0-amount')).toHaveAttribute('type', 'text');
        await expect(page.locator('#id_splits-0-amount')).toHaveValue('50.001');
        await expect(page.locator('#id_splits-0-amount-error-1')).toBeVisible();
        await page.locator('#id_title').fill('Recovered purchase');
        await page.locator('#app-mobile-home-link').press('Enter');
        await expect(page).toHaveURL(/\/dashboard\/$/);
        await page.goBack();
        await expect(page).toHaveURL(/\/transactions\/create\/$/);
        await expect(page.locator('#id_splits-0-amount')).toHaveAttribute('type', 'text');
        await expect(page.locator('#id_splits-0-amount')).toHaveValue('50.001');
        await expect(page.locator('#id_splits-0-category')).toHaveValue(data.categories[0]);
        await page.locator('#id_splits-0-amount').fill('50.00');
        await page.locator('#id_splits-0-amount').press('Tab');
        await amounts(page, ['50.00', '50.00']);
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.getByText('Transaction "Recovered purchase" created.', {exact: true})).toBeVisible();
    });
}

test('new allocation rows inherit category eligibility and keep bound recovery values', async ({page}, info) => {
    await page.setViewportSize({width: 390, height: 900});
    const data = await seed(page, info);
    await start(page);
    await page.getByRole('button', {name: 'Add category', exact: true}).press('Enter');
    for (let index = 0; index < 3; index++) {
        const salary = page.locator(`#id_splits-${index}-category option`).filter({hasText: /^Salary$/});
        await expect(salary).toHaveJSProperty('hidden', true);
        await selectChoice(page.locator(`#id_splits-${index}-category`), data.categories[index]);
    }
    await selectChoice(page.locator('#id_payment_channel'), 'ACCOUNT');
    await selectChoice(page.locator('#id_bank_account'), data.account);
    await page.locator('#id_date').fill('17/10/2026');
    await page.locator('#id_title').fill('');
    await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
    await expect(page.locator('#id_title-error-1')).toBeVisible();
    await page.getByRole('button', {name: 'Add category', exact: true}).press('Enter');
    await expect(page.locator('#id_title-error-1')).toBeVisible();
    for (let index = 0; index < 3; index++) await expect(page.locator(`#id_splits-${index}-category`)).toHaveValue(data.categories[index]);
    await expect(page.locator('#id_splits-3-category option').filter({hasText: /^Salary$/})).toHaveJSProperty('hidden', true);
    await page.locator('#id_splits-3-category-search').fill('Salary');
    await expect(page.locator('#id_splits-3-category-search').locator('..').getByRole('option')).toHaveCount(0);
    await page.locator('#id_splits-3-category-search').press('Escape');
    await selectChoice(page.locator('#id_transaction_type'), 'INCOME');
    for (let index = 0; index < 4; index++) {
        await expect(page.locator(`#id_splits-${index}-category`)).toHaveValue('');
        await expect(page.locator(`#id_splits-${index}-category option`).filter({hasText: /^Alpha$/})).toHaveJSProperty('hidden', true);
        await expect(page.locator(`#id_splits-${index}-category option`).filter({hasText: /^Salary$/})).toHaveJSProperty('hidden', false);
    }
    await selectChoice(page.locator('#id_splits-3-category'), {label: 'Salary'});
    await expect(page.locator('#id_splits-3-category')).not.toHaveValue('');
    await selectChoice(page.locator('#id_transaction_type'), 'EXPENSE');
    await expect(page.locator('#id_splits-3-category')).toHaveValue('');
    await expect(page.locator('#id_splits-3-category option').filter({hasText: /^Salary$/})).toHaveJSProperty('hidden', true);
    await expect(page.locator('#id_title-error-1')).toBeVisible();
});

test('native allocation retains manual controls, invalid text and exact saved totals without JavaScript', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 390, height: 900}});
    const page = await context.newPage();
    try {
        const data = await seed(page, info);
        await start(page);
        const add = page.getByRole('button', {name: 'Add category', exact: true});
        await expect(add).toHaveJSProperty('type', 'submit');
        expect(await add.evaluate(button => {
            const save = button.form.querySelector('button[type="submit"]');
            return Boolean(save.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING);
        })).toBe(true);
        await selectChoice(page.locator('#id_splits-0-category'), data.categories[0]);
        await selectChoice(page.locator('#id_splits-1-category'), data.categories[1]);
        await page.locator('#id_splits-0-amount').fill('50.001');
        await page.locator('#id_splits-1-amount').fill('50.00');
        await selectChoice(page.locator('#id_payment_channel'), 'ACCOUNT');
        await selectChoice(page.locator('#id_bank_account'), data.account);
        await page.locator('#id_date').fill('17/10/2026');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.locator('#id_splits-0-amount')).toHaveAttribute('type', 'text');
        await expect(page.locator('#id_splits-0-amount')).toHaveValue('50.001');
        await expect(page.locator('#id_splits-0-amount-error-1')).toBeVisible();
        await expect(page.getByRole('checkbox', {name: 'Remove category', exact: true})).toHaveCount(2);
        await expect(page.getByRole('button', {name: 'Remove category', exact: true})).toHaveCount(0);
        await page.locator('#id_splits-0-amount').fill('50.00');
        await page.locator('#id_title').press('Enter');
        await expect(page.getByText('Transaction "Shared purchase" created.', {exact: true})).toBeVisible();
    } finally { await context.close(); }
});
