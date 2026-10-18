// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { selectChoice } = require('./helpers/forms');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const result = await page.request.post(path, { form: { csrfmiddlewaretoken: token, ...values },
        headers: { Referer: response.url() }, maxRedirects: 0 });
    expect(result.status(), await result.text()).toBe(302);
    return result.headers().location;
}

async function fixture(page, info) {
    const username = `planning-import-flow-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', { username, email: `${username}@example.test`, password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' });
    await post(page, '/banking/create/', { name: 'Local flow bank' });
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', { bank, name: 'Main cash', currency: 'BRL', opening_balance: '1000', opening_date: '2020-01-01', reserved_amount: '300' });
    await post(page, '/categories/create/', { name: 'Flow expense', transaction_type: 'EXPENSE' });
    await page.goto('/transactions/create/');
    const account = await page.locator('#id_bank_account option').filter({ hasText: 'Main cash' }).getAttribute('value');
    return { bank, account, origin: `/banking/?context=statement#account-row-${account}` };
}

async function upload(page, account, origin, lines, name = 'flow.csv') {
    await page.goto(`/imports/?account=${account}&next=${encodeURIComponent(origin)}`);
    await expect(page.locator('#id_account')).toHaveValue(account);
    await page.locator('#id_file_format').selectOption('CSV');
    await page.locator('#id_encoding').selectOption('utf-8-sig');
    await page.locator('#id_statement').setInputFiles({ name, mimeType: 'text/csv', buffer: Buffer.from(`Date,Text,Amount,Id\n${lines}`) });
    await page.getByRole('button', { name: 'Stage statement', exact: true }).press('Enter');
    await expect(page).toHaveURL(/\/imports\/\d+\/mapping\//);
    await expect(page.locator('main input[name="next"]')).toHaveValue(origin);
}

async function map(page) {
    await page.locator('#id_date_column').selectOption('Date');
    await page.locator('#id_description_column').selectOption('Text');
    await page.locator('#id_amount_mode').selectOption('signed');
    await page.locator('#id_amount_column').selectOption('Amount');
    await page.locator('#id_id_column').selectOption('Id');
    await page.locator('#id_date_format').selectOption('%Y-%m-%d');
    await page.locator('#id_decimal_mark').selectOption('.');
    await page.getByRole('button', { name: 'Review parsed entries', exact: true }).press('Enter');
}

async function category(page, row, js = true) {
    const select = row.locator('select[name$="-category"]');
    const value = await select.locator('option').filter({ hasText: 'Flow expense' }).getAttribute('value');
    if (js) await selectChoice(select, value);
    else await select.selectOption(value);
}

async function confirm(page, origin) {
    await expect(page).toHaveURL(/\/confirm\//);
    await expect(page.getByRole('checkbox')).not.toBeChecked();
    await page.getByRole('checkbox').press('Space');
    await page.getByRole('button', { name: 'Confirm import', exact: true }).press('Enter');
    await expect(page).toHaveURL(new RegExp(origin.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$'));
}

for (const theme of ['light', 'dark']) {
    test(`planning overview and one-step goal reserve keep keyboard and context (${theme})`, async ({ page }, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const { bank, account } = await fixture(page, info);
        await page.goto('/planning/');
        await expect(page.getByRole('heading', { name: 'Category budgets', exact: true })).toBeVisible();
        await page.locator('nav[aria-label="Planning sections"]').getByRole('link', { name: 'Goals', exact: true }).press('Enter');
        await expect(page.getByRole('link', { name: 'Tools', exact: true })).toBeVisible();
        await page.getByRole('link', { name: 'New goal', exact: true }).press('Enter');
        await page.locator('#id_name').fill('Flow goal');
        await page.locator('#id_target_amount').fill('2000');
        await expect(page.locator('#id_reserve_now')).not.toBeChecked();
        await expect(page.locator('#goal-source-search')).toBeHidden();
        await page.locator('#id_reserve_now').focus();
        await page.keyboard.press('Space');
        await page.keyboard.press('Tab');
        await expect(page.locator('#goal-source-search')).toBeFocused();
        await expect(page.locator('#id_reserved_amount')).toBeHidden();
        await selectChoice(page.locator('#id_source'), `account:${account}`);
        await page.locator('#id_reserved_amount').fill('1500');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(page.getByRole('alert').filter({ hasText: 'reservation exceeds' })).toBeVisible();
        await expect(page.locator('#goal-source-search')).toHaveValue(/Main cash/);
        await expect(page.locator('#id_reserved_amount')).toHaveValue('1500');
        await page.locator('#id_reserve_now').press('Space');
        await expect(page.locator('#id_source')).toHaveValue('');
        await expect(page.locator('#id_reserved_amount')).toHaveValue('');
        await expect(page.locator('#id_reserved_amount')).toBeHidden();
        await page.locator('#id_reserve_now').press('Space');
        await selectChoice(page.locator('#id_source'), `account:${account}`);
        await page.locator('#id_reserved_amount').fill('250');
        await page.screenshot({ path: info.outputPath(`goal-create-${theme}-desktop.png`), fullPage: true });
        await page.setViewportSize({ width: 390, height: 740 });
        const help = page.getByRole('button', { name: 'Explain Reserved amount', exact: true });
        await help.focus();
        const tooltip = page.locator('#id_reserved_amount-help');
        await expect(tooltip).toBeVisible();
        const bounds = await tooltip.boundingBox();
        expect(bounds.x).toBeGreaterThanOrEqual(11);
        expect(bounds.x + bounds.width).toBeLessThanOrEqual(379);
        await page.keyboard.press('Escape');
        await expect(tooltip).toBeHidden();
        await page.keyboard.press('Tab');
        await expect(page.locator('#id_reserved_amount')).toBeFocused();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: info.outputPath(`goal-create-${theme}-mobile.png`), fullPage: true });
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(page).toHaveURL(/\/planning\/goals\/$/);
        const goal = page.locator('article').filter({ has: page.getByRole('heading', { name: 'Flow goal', exact: true }) });
        await expect(goal).toContainText('250,00');
        await page.goto('/banking/');
        // The overview owns bank links; account rows belong to bank details.
        // This fixture leaves its account outside planning, under Reserves.
        await page.locator(`#bank-${bank}`).press('Enter');
        await expect(page).toHaveURL(new RegExp(`/banking/${bank}/$`));
        await page.locator(`#bank-reserves-${bank} > summary`).press('Enter');
        await expect(page.locator(`#account-row-${account}`)).toBeVisible();
        await expect(page.locator(`#account-row-${account} [data-account-balance]`)).toContainText('1.000,00');
    });

    test.skip(`compact paginated import, strong-ID bulk skip and mapping reuse (${theme})`, async ({ page }, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const { account, origin } = await fixture(page, info);
        await upload(page, account, origin, '2026-09-01,Coffee,-25,confirmed\n');
        await map(page);
        let entry = page.locator('[data-import-entry]').first();
        await entry.locator('select[name$="-action"]').selectOption('CREATE');
        await category(page, entry);
        await page.getByRole('button', { name: 'Save review and inspect confirmation', exact: true }).press('Enter');
        await confirm(page, origin);
        const lines = '2026-09-01,Coffee,-25,confirmed\n2026-09-01,Coffee,-25,\n'
            + Array.from({ length: 24 }, (_, index) => `2026-09-02,Entry ${index + 3},-5,new-${index + 3}\n`).join('');
        await upload(page, account, origin, lines, 'more.csv');
        await page.getByRole('link', { name: 'Reuse last confirmed column mapping', exact: true }).press('Enter');
        await expect(page.locator('#id_date_column')).toHaveValue('Date');
        await expect(page.getByText('Previous column choices are filled in.', { exact: false })).toBeVisible();
        await page.getByRole('button', { name: 'Review parsed entries', exact: true }).press('Enter');
        await expect(page.locator('[data-import-entry]')).toHaveCount(25);
        await expect(page.locator('[data-import-entry][open]')).toHaveCount(1);
        await expect(page.locator('[data-import-entry]').first().locator('summary').first()).toContainText('Confirmed identifier');
        await page.getByRole('button', { name: 'Skip confirmed identifiers on this page', exact: true }).press('Enter');
        await expect(page.locator('[data-import-entry]').first().locator('select[name$="-action"]')).toHaveValue('SKIP');
        await expect(page.locator('[data-import-entry]').nth(1).locator('select[name$="-action"]')).toHaveValue('');
        await expect(page.locator('[data-import-entry]').nth(1).locator('summary').first()).toContainText('Possible match');
        await page.screenshot({ path: info.outputPath(`import-review-${theme}-desktop.png`), fullPage: true });
        // Prepare the remaining first-page decisions through its native POST;
        // the browser checks the pagination result and the final row's editor.
        const fields = await page.locator('select[name$="-action"]').evaluateAll(selects => Object.fromEntries(selects.map(select => [select.name, 'SKIP'])));
        const target = new URL(page.url());
        const nextPage = await post(page, target.pathname, { ...fields, page: '1', next: origin });
        await page.goto(nextPage);
        await expect(page.getByText('Page 2 of 2', { exact: true })).toBeVisible();
        await expect(page.locator('[data-import-entry]')).toHaveCount(1);
        entry = page.locator('[data-import-entry]');
        const action = entry.locator('select[name$="-action"]');
        await action.focus();
        await page.keyboard.press('Home');
        await page.keyboard.press('ArrowDown');
        await page.keyboard.press('ArrowDown');
        await expect(action).toHaveValue('CREATE');
        await page.getByRole('button', { name: 'Save page decisions', exact: true }).press('Enter');
        await expect(entry.getByRole('alert').filter({ hasText: 'Choose an owned category' })).toBeVisible();
        await category(page, entry);
        await page.setViewportSize({ width: 390, height: 740 });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: info.outputPath(`import-review-${theme}-mobile.png`), fullPage: true });
        await page.getByRole('button', { name: 'Save page decisions', exact: true }).press('Enter');
        await confirm(page, origin);
        await expect(page.locator(`#account-row-${account}`)).toContainText('970,00');
    });
}

test.describe('native planning flow', () => {
    test.use({ javaScriptEnabled: false });
    test('optional reserve keeps goal details without JavaScript', async ({ page }, info) => {
        const { account, origin } = await fixture(page, info);
        await page.goto('/planning/goals/create/');
        await page.locator('#id_name').fill('Native connected target');
        await page.locator('#id_target_amount').fill('1000');
        await page.locator('#id_reserve_now').press('Space');
        await page.locator('#id_source').selectOption(`account:${account}`);
        await page.locator('#id_reserved_amount').fill('200');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(page.getByRole('heading', { name: 'Native connected target', exact: true })).toBeVisible();
        await expect(page.locator('main')).toContainText('200,00');

    });
});
