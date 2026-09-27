// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function post(page, path, fields) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, { form: { csrfmiddlewaretoken: csrf, ...fields },
        headers: { Referer: response.url() }, maxRedirects: 0 });
    expect(saved.status(), await saved.text()).toBe(302);
}
async function signup(page, testInfo) {
    const name = `planning-${testInfo.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', { username: name, email: `${name}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' });
}

for (const theme of ['light', 'dark']) {
    test(`yield month adjustments follow duration and retain edits (${theme})`, async ({ page }, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await signup(page, info);
        await page.goto('/sandbox/simulation/');
        await expect(page.locator('#id_draft_name')).toBeHidden();
        await page.locator('#id_initial_balance').fill('100');
        await page.locator('#id_rate').fill('1');
        await page.locator('#id_months').fill('2');
        await page.locator('#yield-month-overrides > summary').press('Enter');
        await expect(page.getByRole('button', { name: 'Update month rows' })).toBeHidden();
        await expect(page.locator('[data-yield-rows] > tr:visible')).toHaveCount(2);
        await page.locator('[name="contribution_1"]').fill('200');
        await expect(page.locator('#simulation-result')).toContainText('302,01');
        await page.locator('#id_months').fill('1');
        await expect(page.locator('[name="contribution_1"]')).toBeHidden();
        await expect(page.locator('[name="contribution_1"]')).toBeDisabled();
        await expect(page.locator('#simulation-result')).toContainText('101,00');
        await page.locator('#id_months').fill('2');
        await expect(page.locator('[name="contribution_1"]')).toHaveValue('200');
        await expect(page.locator('#simulation-result')).toContainText('302,01');
        await expect(page.locator('#yield-monthly-results table')).toBeHidden();
        await page.locator('#yield-monthly-results > summary').press('Space');
        await page.locator('#id_rate').fill('0');
        await expect(page.locator('#simulation-result')).toContainText('300,00');
        await expect(page.locator('#yield-monthly-results table')).toBeVisible();
        await page.locator('[name="contribution_1"]').fill('invalid');
        await expect(page.locator('#simulation-result [role="alert"]')).toContainText('Month 2');
        await expect(page.locator('[name="contribution_1"]')).toBeFocused();
        await page.locator('[name="contribution_1"]').fill('200');
        await expect(page.locator('#simulation-result')).toContainText('300,00');
        await page.setViewportSize({ width: 390, height: 740 });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: info.outputPath(`simulation-mobile-${theme}.png`), fullPage: true });
    });
    test(`yield simulation recalculates without moving keyboard focus in ${theme}`, async ({ page }, testInfo) => {
        await signup(page, testInfo);
        await page.goto('/sandbox/simulation/');
        await page.evaluate(theme => {
            localStorage.setItem('theme', theme);
            document.documentElement.classList.toggle('dark', theme === 'dark');
        }, theme);
        await page.locator('#id_months').fill('2');
        await page.locator('#id_initial_balance').fill('100');
        await page.locator('#id_rate').fill('1');
        const contribution = page.locator('#id_contribution');
        await contribution.focus();
        await page.keyboard.press('ControlOrMeta+A');
        await page.keyboard.type('100');
        const scroll = await page.evaluate(() => window.scrollY);
        await expect(page.locator('#simulation-result')).toContainText('303,01');
        await expect(contribution).toBeFocused();
        expect(await page.evaluate(() => window.scrollY)).toBeCloseTo(scroll, 0);
        await page.keyboard.press('Tab');
        await expect(page.locator('#id_withdrawal')).toBeFocused();
        await page.keyboard.type('10000');
        await expect(page.locator('#simulation-result')).toContainText('withdrawal exceeds');
        await expect(page.locator('#id_withdrawal')).toBeFocused();
        await page.locator('#id_withdrawal').fill('0');
        await expect(page.locator('#simulation-result')).toContainText('303,01');
        await page.getByText('Save this scenario', { exact: true }).press('Enter');
        await page.locator('#id_draft_name').fill(`Yield ${theme}`);
        await page.getByRole('button', { name: 'Save draft', exact: true }).click();
        await expect(page).toHaveURL(/\/sandbox\/drafts\/\d+\/$/);
        await expect(page.locator('#id_initial_balance')).toHaveValue('100.00');
        await expect(page.locator('#simulation-result')).toContainText('303,01');
        await page.screenshot({ path: testInfo.outputPath(`planning-yield-${theme}.png`), fullPage: true });
    });
}

test('salary plan uses the selected month forecast and saves only when requested', async ({ page }, testInfo) => {
    await signup(page, testInfo);
    await post(page, '/banking/create/', { name: 'Planning bank' });
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', { bank, name: 'Checking', currency: 'BRL', opening_balance: '1000', pix_enabled: 'on' });
    await page.goto('/transactions/create/');
    const account = await page.locator('#id_bank_account option').last().getAttribute('value');
    const category = await page.locator('#id_category option').last().getAttribute('value');
    await post(page, '/transactions/create/', { title: 'Future rent', amount: '600', transaction_type: 'EXPENSE',
        category, payment_channel: 'ACCOUNT', bank_account: account, date: '2026-10-15', installments: '1' });
    await post(page, '/banking/credit-cards/create/', {
        account, name: 'Planning card', card_type: 'PHYSICAL', closing_day: '24', due_day: '1',
    });
    await page.goto('/transactions/create/');
    const card = await page.locator('#id_credit_card option').last().getAttribute('value');
    await post(page, '/transactions/create/', { title: 'September card expense', amount: '100',
        transaction_type: 'EXPENSE', category, payment_channel: 'CREDIT_CARD', credit_card: card,
        date: '2026-09-05', installments: '1' });
    await page.goto('/sandbox/');
    await expect(page.locator('#id_draft_name')).toBeHidden();
    await page.getByLabel('Gross monthly salary', { exact: true }).fill('5000');
    await page.getByLabel('Planning month', { exact: true }).fill('2026-10');
    await expect(page.getByRole('button', { name: 'Show month forecast', exact: true })).toBeHidden();
    const forecast = page.getByRole('article').filter({ hasText: 'Existing expense forecast' });
    await expect(forecast).toContainText('600,00');
    await page.locator('#budget-previous-month').press('Enter');
    await expect(forecast).toContainText('100,00');
    await expect(page.locator('#id_planning_month')).toHaveValue('2026-09');
    await page.locator('#budget-next-month').press('Space');
    await expect(forecast).toContainText('600,00');
    await expect(page.locator('#id_planning_month')).toHaveValue('2026-10');
    const firstExpense = page.locator('[data-variable-row]').first();
    await firstExpense.getByLabel('Fixed expense description').fill('Utilities');
    await firstExpense.getByLabel('Fixed expense monthly amount').fill('150');
    await page.getByRole('button', { name: 'Add fixed expense' }).click();
    const expenses = page.locator('[data-variable-row]');
    await expect(expenses).toHaveCount(2);
    await expenses.nth(1).getByLabel('Fixed expense description').fill('Transport');
    await expenses.nth(1).getByLabel('Fixed expense monthly amount').fill('50');
    await page.getByRole('button', { name: 'Calculate month', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'October 2026', level: 2 })).toBeVisible();
    await expect(page.getByText('R$ 4.200,00', { exact: true })).toBeVisible();
    await page.getByText('Save this plan (optional)', { exact: true }).click();
    await page.locator('#id_draft_name').fill('October commitments');
    await page.getByRole('button', { name: 'Save draft', exact: true }).click();
    await expect(page).toHaveURL(/\/sandbox\/drafts\/\d+\/$/);
    await expect(page.getByLabel('Fixed expense monthly amount').first()).toHaveValue('150.00');
    await expect(page.getByText('R$ 4.200,00', { exact: true })).toBeVisible();
    await page.setViewportSize({ width: 390, height: 700 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('planning-commitments-mobile.png'), fullPage: true });
});

test.describe('planning without JavaScript', () => {
    test.use({ javaScriptEnabled: false });
    test('yield rows, invalid values and optional saving work through native forms', async ({ page }, info) => {
        await signup(page, info);
        await page.goto('/sandbox/simulation/');
        await expect(page.getByRole('button', { name: '2 years', exact: true })).toBeHidden();
        await page.locator('#id_initial_balance').fill('100');
        await page.locator('#id_rate').fill('0');
        await page.locator('#id_months').fill('2');
        await page.locator('#yield-month-overrides > summary').press('Enter');
        await page.getByRole('button', { name: 'Update month rows' }).press('Enter');
        await expect(page.locator('[data-yield-rows] > tr:visible')).toHaveCount(2);
        await page.locator('[name="contribution_1"]').fill('invalid');
        await page.getByRole('button', { name: 'Calculate', exact: true }).press('Enter');
        await expect(page.locator('[name="contribution_1"]')).toBeVisible();
        await expect(page.locator('[name="contribution_1"]')).toHaveValue('invalid');
        await page.locator('[name="contribution_1"]').fill('50');
        await page.getByRole('button', { name: 'Calculate', exact: true }).press('Enter');
        await expect(page.locator('#simulation-result')).toContainText('150,00');
        await page.getByText('Save this scenario', { exact: true }).press('Enter');
        await page.getByRole('button', { name: 'Save draft', exact: true }).press('Enter');
        await expect(page.locator('#id_draft_name')).toBeVisible();
        await page.locator('#id_draft_name').fill('Native yield scenario');
        await page.getByRole('button', { name: 'Save draft', exact: true }).press('Enter');
        await expect(page).toHaveURL(/\/sandbox\/drafts\/\d+\/$/);
        await expect(page.locator('[name="contribution_1"]')).toHaveValue('50.00');
    });
    test('incomplete drafts and repeated rows support full native submission', async ({ page }, testInfo) => {
        await signup(page, testInfo);
        await page.goto('/sandbox/');
        await page.getByText('Save this plan (optional)', { exact: true }).press('Enter');
        await page.locator('#id_draft_name').fill('My incomplete plan');
        await page.getByLabel('Planning month', { exact: true }).fill('2026-10');
        await page.getByLabel('Fixed expense description', { exact: true }).fill('Rent');
        await page.getByLabel('Fixed expense monthly amount', { exact: true }).fill('invalid');
        await page.getByRole('button', { name: 'Save draft', exact: true }).click();
        await expect(page).toHaveURL(/\/sandbox\/drafts\/\d+\/$/);
        await expect(page.getByLabel('Planning month', { exact: true })).toHaveValue('2026-10');
        await expect(page.getByLabel('Fixed expense monthly amount', { exact: true })).toHaveValue('invalid');
        await expect(page.locator('#scenario-result-title')).toHaveCount(0);
        await page.getByLabel('Gross monthly salary', { exact: true }).fill('5000');
        await page.getByLabel('Fixed expense monthly amount', { exact: true }).fill('1000');
        await page.getByRole('button', { name: 'Calculate month', exact: true }).click();
        await expect(page.locator('#scenario-result-title')).toBeVisible();
        await page.getByRole('button', { name: 'Save draft', exact: true }).click();
        await page.getByRole('link', { name: 'Saved drafts', exact: true }).click();
        await page.getByRole('button', { name: 'Duplicate', exact: true }).click();
        await expect(page.locator('#id_draft_name')).toHaveValue('Copy of My incomplete plan');
        await page.getByRole('link', { name: 'Saved drafts', exact: true }).click();
        for (const checkbox of await page.getByRole('checkbox').all()) await checkbox.check();
        await page.getByRole('button', { name: 'Compare selected drafts' }).click();
        await expect(page.getByRole('heading', { name: 'Compare drafts', exact: true })).toBeVisible();
    });
});

for (const theme of ['light', 'dark']) {
    test(`month arrows, percent expenses and simulation parameter controls (${theme})`, async ({ page }, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await signup(page, info);
        await page.goto('/sandbox/');
        await page.locator('#id_gross_salary').fill('5000');
        await page.locator('#id_planning_month').fill('2026-12');
        await expect(page.locator('[data-planning-month]')).toHaveText('December 2026');
        await page.getByLabel('Fixed expense description', { exact: true }).fill('Reserve');
        const unit = page.getByLabel('Fixed expense unit', { exact: true });
        await unit.focus();
        await page.keyboard.press('End');
        await page.keyboard.press('Tab');
        await expect(page.getByLabel('Fixed expense monthly amount')).toBeFocused();
        await page.keyboard.type('10');
        await page.locator('#budget-next-month').press('Enter');
        await expect(page.locator('#id_planning_month')).toHaveValue('2027-01');
        await expect(page.locator('#budget-next-month')).toBeFocused();
        await expect(page.getByLabel('Fixed expense unit')).toHaveValue('percent');
        await page.locator('#budget-previous-month').press('Space');
        await expect(page.locator('#id_planning_month')).toHaveValue('2026-12');
        await page.locator('#budget-calculate').press('Enter');
        await expect(page.getByText('R$ 4.500,00', { exact: true })).toBeVisible();
        await page.getByLabel('Fixed expense monthly amount').fill('101');
        await page.locator('#budget-calculate').press('Enter');
        await expect(page.locator('[role="alert"]').first()).toContainText('0–100');
        await expect(page.getByLabel('Fixed expense unit')).toHaveValue('percent');
        await expect(page.getByLabel('Fixed expense monthly amount')).toHaveValue('101');
        await page.getByLabel('Fixed expense monthly amount').fill('10');
        await page.locator('#budget-calculate').press('Enter');
        await page.setViewportSize({ width: 390, height: 740 });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: info.outputPath(`monthly-controls-${theme}.png`), fullPage: true });
        page.on('dialog', dialog => dialog.accept());
        await page.goto('/sandbox/simulation/');
        await page.locator('#id_initial_balance').fill('100');
        await page.locator('#id_rate').fill('12');
        await page.locator('#id_rate_period').focus();
        await page.keyboard.press('End');
        await page.keyboard.press('Tab');
        await expect(page.getByRole('button', { name: 'Explain Effective annual rate (%)', exact: true })).toBeFocused();
        await expect(page.locator('#id_rate-help')).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(page.locator('#id_rate-help')).toBeHidden();
        await page.getByRole('button', { name: '2 years', exact: true }).press('Enter');
        await expect(page.locator('#id_months')).toHaveValue('24');
        await expect(page.locator('#simulation-result')).toContainText('125,42');
        await expect(page.getByRole('button', { name: '2 years', exact: true })).toBeFocused();
        await page.locator('#id_currency').focus();
        await page.keyboard.press('ArrowDown');
        await page.keyboard.press('Tab');
        await expect(page.locator('[data-currency-field] label').first()).toContainText('USD');
        await expect(page.locator('#id_start_month')).toHaveAttribute('type', 'month');
        await page.screenshot({ path: info.outputPath(`simulation-controls-${theme}.png`), fullPage: true });
    });
}

test.describe('new planning controls without JavaScript', () => {
    test.use({ javaScriptEnabled: false });
    test('month arrows and percent expenses use native posts', async ({ page }, info) => {
        await signup(page, info);
        await page.goto('/sandbox/');
        await page.locator('#id_gross_salary').fill('1000');
        await page.locator('#id_planning_month').fill('2026-12');
        await page.getByLabel('Fixed expense description').fill('Reserve');
        await page.getByLabel('Fixed expense unit').selectOption('percent');
        await page.getByLabel('Fixed expense monthly amount').fill('10');
        await page.locator('#budget-next-month').press('Enter');
        await expect(page.locator('#id_planning_month')).toHaveValue('2027-01');
        await expect(page.locator('#budget-forecast')).toBeVisible();
        await page.locator('#budget-calculate').press('Enter');
        await expect(page.getByText('R$ 900,00', { exact: true })).toBeVisible();
        await expect(page.getByLabel('Fixed expense unit')).toHaveValue('percent');
    });
});
