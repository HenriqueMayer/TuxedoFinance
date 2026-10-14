// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { selectChoice } = require('./helpers/forms');

async function post(page, path, fields) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, { form: { csrfmiddlewaretoken: csrf, ...fields },
        headers: { Referer: response.url() }, maxRedirects: 0 });
    expect(saved.status(), await saved.text()).toBe(302);
}
async function fixture(page, testInfo) {
    const username = `imports-${testInfo.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', { username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' });
    await post(page, '/banking/create/', { name: 'Import keyboard bank' });
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', { bank, name: 'Statement account', currency: 'BRL', opening_balance: '1000', opening_date: '2025-01-01' });
    await post(page, '/banking/accounts/create/', { bank, name: 'Other owned account', currency: 'BRL', opening_balance: '0' });
    await post(page, '/categories/create/', { name: 'Imported coffee', transaction_type: 'EXPENSE' });
}
async function stage(page, usePicker = true) {
    await page.goto('/imports/');
    if (usePicker) {
        const trigger = page.getByRole('button', { name: 'Explain Local statement file', exact: true });
        const tooltip = page.locator('#id_statement-help');
        await trigger.hover();
        await expect(tooltip).toBeVisible();
        const bounds = await tooltip.boundingBox();
        expect(bounds.x).toBeGreaterThanOrEqual(11);
        expect(bounds.x + bounds.width).toBeLessThanOrEqual(page.viewportSize().width - 11);
        await trigger.click();
        await page.mouse.move(2, 2);
        await expect(tooltip).toBeHidden();
        await page.locator('#id_statement').focus();
        await page.keyboard.press('Shift+Tab');
        await expect(trigger).toBeFocused();
        await expect(tooltip).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(tooltip).toBeHidden();
        await page.keyboard.press('Space');
        await expect(tooltip).toBeVisible();
        await page.keyboard.press('Tab');
        await expect(tooltip).toBeHidden();
    } else {
        const fallback = page.locator('summary[aria-label="Explain Local statement file"]');
        await fallback.click();
        await expect(fallback.locator('..').locator('.help-fallback-content')).toBeVisible();
        await fallback.click();
    }
    const account = page.locator('#id_account');
    if (usePicker) await selectChoice(account, { label: 'Import keyboard bank - Statement account (BRL)' });
    else {
        const option = await account.locator('option').evaluateAll(options => options.find(option => option.textContent.includes('Statement account')).value);
        await account.selectOption(option);
    }
    await page.locator('#id_file_format').selectOption('CSV');
    await page.locator('#id_encoding').selectOption('utf-8-sig');
    await page.locator('#id_statement').setInputFiles({ name: 'keyboard.csv', mimeType: 'text/csv',
        buffer: Buffer.from('Date,Text,Amount,Id\n2026-09-01,Imported coffee,-25.00,keyboard-1\n') });
    await page.getByLabel('Statement closing balance', { exact: true }).fill('975');
    await page.locator('#id_closing_date').fill('01/09/2026');
    await page.getByRole('button', { name: 'Stage statement', exact: true }).click();
    await expect(page).toHaveURL(/\/imports\/\d+\/mapping\//);
    await page.locator('#id_date_column').selectOption('Date');
    await page.locator('#id_description_column').selectOption('Text');
    await page.locator('#id_amount_mode').selectOption('signed');
    await page.locator('#id_amount_column').selectOption('Amount');
    await page.locator('#id_id_column').selectOption('Id');
    await page.locator('#id_date_format').selectOption('%Y-%m-%d');
    await page.locator('#id_decimal_mark').selectOption('.');
    await page.getByRole('button', { name: 'Review parsed entries' }).click();
    await expect(page).toHaveURL(/\/imports\/\d+\/review\//);
}

for (const dark of [false, true]) {
    test(`statement review keyboard transitions, validation and undo: ${dark ? 'dark' : 'light'}`, async ({ page }, testInfo) => {
        await fixture(page, testInfo);
        await page.evaluate(value => localStorage.setItem('theme', value ? 'dark' : 'light'), dark);
        await stage(page);
        await page.evaluate(value => document.documentElement.classList.toggle('dark', value), dark);
        const entry = page.locator('[data-import-entry]');
        await expect(entry).toHaveCount(1);
        await expect(entry).toHaveAttribute('open', '');
        const action = entry.locator('select[name$="-action"]');
        const category = entry.locator('select[name$="-category"]');
        const categoryId = await category.getAttribute('id');
        const search = page.locator(`[id="${categoryId}-search"]`);
        await expect(action).toHaveValue('');
        await expect(search).toBeHidden();
        await action.focus();
        await page.keyboard.press('Home');
        await page.keyboard.press('ArrowDown');
        await page.keyboard.press('ArrowDown');
        await expect(action).toHaveValue('CREATE');
        await page.keyboard.press('Tab');
        await expect(search).toBeFocused();
        await search.fill('Imported coffee');
        await search.press('ArrowDown');
        await search.press('Enter');
        await expect(category).not.toHaveValue('');
        await action.focus();
        await action.press('End');
        await expect(action).toHaveValue('TRANSFER');
        await expect(category).toHaveValue('');
        const other = entry.locator('select[name$="-counterparty_account"]');
        const otherId = await other.getAttribute('id');
        const otherSearch = page.locator(`[id="${otherId}-search"]`);
        const otherAmount = page.getByLabel('Actual amount in the other account');
        await expect(otherAmount).toBeHidden();
        await selectChoice(otherSearch, { label: 'Import keyboard bank - Other owned account (BRL)' });
        await expect(otherAmount).toBeVisible();
        await otherAmount.fill('25');
        await action.focus();
        await action.press('Home');
        await action.press('ArrowDown');
        await expect(action).toHaveValue('SKIP');
        await expect(other).toHaveValue('');
        await expect(otherAmount).toHaveValue('');
        await expect(otherSearch).toBeHidden();
        await action.press('ArrowDown');
        await expect(action).toHaveValue('CREATE');
        await page.getByRole('button', { name: 'Save review and inspect confirmation' }).click();
        await expect(page.getByRole('alert').filter({ hasText: 'Choose an owned category' })).toBeVisible();
        await expect(action).toHaveValue('CREATE');
        await expect(search).toBeVisible();
        await selectChoice(search, { label: 'Imported coffee' });
        await page.screenshot({ path: testInfo.outputPath(`statement-review-${dark ? 'dark' : 'light'}.png`), fullPage: true });
        await page.getByRole('button', { name: 'Save review and inspect confirmation' }).click();
        await expect(page).toHaveURL(/\/confirm\//);
        await expect(page.getByRole('checkbox')).not.toBeChecked();
        await page.getByRole('button', { name: 'Confirm import', exact: true }).click();
        await expect(page.getByRole('alert').filter({ hasText: 'This field is required' })).toBeVisible();
        await page.getByRole('checkbox').check();
        await page.getByRole('button', { name: 'Confirm import', exact: true }).click();
        await expect(page.getByRole('heading', { name: 'Closing balance reconciliation' })).toBeVisible();
        await expect(page.getByText('Difference: 0.00', { exact: true })).toBeVisible();
        await page.getByRole('link', { name: 'Review undo' }).click();
        await page.getByRole('button', { name: 'Undo this import' }).click();
        await expect(page.getByText('Only unchanged records created by this import were removed.', { exact: false })).toBeVisible();
    });
}

test('CSV mapping and full review submission work without JavaScript', async ({ browser }, testInfo) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    await fixture(page, testInfo);
    await stage(page, false);
    const entry = page.locator('[data-import-entry]');
    await expect(entry).toHaveAttribute('open', '');
    await entry.locator('select[name$="-action"]').selectOption('CREATE');
    const category = entry.locator('select[name$="-category"]');
    const value = await category.locator('option').evaluateAll(options => options.find(option => option.textContent.includes('Imported coffee')).value);
    await category.selectOption(value);
    await page.getByRole('button', { name: 'Save review and inspect confirmation' }).click();
    await page.getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Confirm import', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Local provenance' })).toBeVisible();
    await expect(page.getByText('Difference: 0.00', { exact: true })).toBeVisible();
    await context.close();
});

test('local statement help fits a touch viewport and dismisses on outside touch', async ({ browser }, testInfo) => {
    const context = await browser.newContext({ viewport: { width: 390, height: 740 }, hasTouch: true, locale: 'en-US' });
    try {
        const page = await context.newPage();
        await fixture(page, testInfo);
        await page.goto('/imports/');
        const trigger = page.getByRole('button', { name: 'Explain Local statement file', exact: true });
        const tooltip = page.locator('#id_statement-help');
        await trigger.tap();
        await expect(tooltip).toBeVisible();
        const bounds = await tooltip.boundingBox();
        expect(bounds.x).toBeGreaterThanOrEqual(11);
        expect(bounds.x + bounds.width).toBeLessThanOrEqual(379);
        expect(bounds.y).toBeGreaterThanOrEqual(11);
        expect(bounds.y + bounds.height).toBeLessThanOrEqual(729);
        await page.touchscreen.tap(2, 2);
        await expect(tooltip).toBeHidden();
        await trigger.tap();
        await expect(tooltip).toBeVisible();
        await trigger.tap();
        await expect(tooltip).toBeHidden();
    } finally {
        await context.close();
    }
});
