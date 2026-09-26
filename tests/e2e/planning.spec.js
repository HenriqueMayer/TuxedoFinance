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

test('commitments use explicit review, preserve edits and save without losing location', async ({ page }, testInfo) => {
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
    await page.goto('/sandbox/');
    await page.getByLabel('Gross monthly salary', { exact: true }).fill('5000');
    await page.getByLabel('Planning month', { exact: true }).fill('2026-10');
    await page.getByLabel('Expense basis', { exact: true }).selectOption('recorded');
    await expect(page.getByLabel('Fixed costs target', { exact: true })).toBeHidden();
    await page.getByRole('button', { name: 'Capture commitments', exact: true }).focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('region', { name: 'Review commitment refresh' })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Review commitment refresh' })).toContainText('Future rent');
    await page.getByRole('button', { name: 'Apply snapshot', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Review commitment refresh' })).toHaveCount(0);
    const amount = page.getByLabel('Scenario amount for Future rent', { exact: true });
    await amount.fill('450');
    await page.getByRole('button', { name: 'Review refresh', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Review commitment refresh' })).toContainText('Manual amount retained');
    await page.getByRole('button', { name: 'Apply snapshot', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Review commitment refresh' })).toHaveCount(0);
    await expect(amount).toHaveValue('450');
    await page.locator('#id_draft_name').fill('October commitments');
    await page.getByRole('button', { name: 'Save draft', exact: true }).click();
    await expect(page).toHaveURL(/\/sandbox\/drafts\/\d+\/$/);
    await expect(amount).toHaveValue('450.00');
    await page.setViewportSize({ width: 390, height: 700 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('planning-commitments-mobile.png'), fullPage: true });
});

test.describe('planning without JavaScript', () => {
    test.use({ javaScriptEnabled: false });
    test('yield rows, invalid values and optional saving work through native forms', async ({ page }, info) => {
        await signup(page, info);
        await page.goto('/sandbox/simulation/');
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
        await page.locator('#id_draft_name').fill('My incomplete plan');
        await page.getByLabel('Planning month', { exact: true }).fill('2026-');
        await page.locator('[data-add-variable]').click();
        await page.getByLabel('Expense description', { exact: true }).fill('Rent');
        await page.getByLabel('Expense value', { exact: true }).fill('invalid');
        await page.getByRole('button', { name: 'Save draft', exact: true }).click();
        await expect(page).toHaveURL(/\/sandbox\/drafts\/\d+\/$/);
        await expect(page.getByLabel('Planning month', { exact: true })).toHaveValue('2026-');
        await expect(page.getByLabel('Expense value', { exact: true })).toHaveValue('invalid');
        await expect(page.getByRole('heading', { name: 'Manual calculation', exact: true })).toHaveCount(0);
        await page.getByLabel('Planning month', { exact: true }).fill('2026-10');
        await page.getByLabel('Gross monthly salary', { exact: true }).fill('5000');
        await page.getByLabel('Expense value', { exact: true }).fill('1000');
        await page.getByRole('button', { name: 'Calculate', exact: true }).click();
        await expect(page.getByRole('heading', { name: 'Manual calculation', exact: true })).toBeVisible();
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
