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

async function seed(page, testInfo) {
    const username = `personal-plan-${testInfo.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', { username, email: `${username}@example.test`, password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' });
    await post(page, '/banking/create/', { name: 'Planning bank' });
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', { bank, name: 'Planning cash', currency: 'BRL', opening_balance: '1000', opening_date: '2020-01-01', reserved_amount: '300', planning_enabled: 'on', pix_enabled: 'on' });
    await page.goto('/planning/budgets/create/');
    const category = await page.locator('#id_category option').filter({ hasText: 'Groceries' }).getAttribute('value');
    const goalUrl = await post(page, '/planning/goals/create/', { name: 'Study target', target_amount: '2000', currency: 'BRL', target_date: '2030-12-31' });
    return { bank, category, goalUrl };
}

for (const theme of ['light', 'dark']) {
    test(`personal planning keyboard, recovery and source reserves (${theme})`, async ({ page }, testInfo) => {
        const { bank, category, goalUrl } = await seed(page, testInfo);
        await page.addInitScript(theme => localStorage.setItem('theme', theme), theme);
        await page.goto('/planning/budgets/create/');
        await expect(page.locator('nav[aria-label="Planning sections"]')).toHaveCount(1);
        await expect(page.locator('nav[aria-label="Planning sections"]').getByRole('link', { name: 'This month', exact: true })).toHaveAttribute('href', '/planning/');
        const categorySearch = page.locator('#category-search');
        await expect(categorySearch).toHaveValue('');
        await page.locator('#id_month').focus();
        // Chromium's native month control has separate month/year Tab stops.
        for (let stop = 0; stop < 4 && await page.locator('#id_month').evaluate(element => document.activeElement === element); stop++) {
            await page.keyboard.press('Tab');
        }
        // The shared help control remains reachable between the month and category.
        const categoryHelp = page.getByRole('button', { name: 'Explain Category', exact: true });
        await expect(categoryHelp).toBeFocused();
        await expect(page.locator('#id_category-help')).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(page.locator('#id_category-help')).toBeHidden();
        await page.keyboard.press('Tab');
        await expect(categorySearch).toBeFocused();
        await categorySearch.press('ArrowDown');
        const bounds = await categorySearch.boundingBox();
        expect(bounds.y).toBeGreaterThanOrEqual(0);
        expect(bounds.y + bounds.height).toBeLessThan(await page.evaluate(() => innerHeight));
        await categorySearch.press('Escape');
        await selectChoice(page.locator('#id_category'), category);
        await categorySearch.press('Tab');
        const categoryClear = categorySearch.locator('..').getByRole('button');
        await expect(categoryClear).toBeFocused();
        await categoryClear.press('Space');
        await expect(categorySearch).toHaveValue('');
        await selectChoice(page.locator('#id_category'), category);
        await categorySearch.press('Tab');
        await expect(categoryClear).toBeFocused();
        await categoryClear.press('Tab');
        await expect(page.locator('#id_currency')).toBeFocused();
        await page.locator('#id_amount').fill('-1');
        await page.getByRole('button', { name: 'Save', exact: true }).click();
        await expect(page.locator('[role="alert"]').first()).toBeVisible();
        await expect(categorySearch).toHaveValue('Groceries');
        await expect(page.locator('#id_amount')).toHaveValue('-1');
        await page.locator('#id_amount').fill('250');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(page).toHaveURL(/planning\/\?month=/);
        await expect(page.locator('main')).toContainText('250,00');
        await page.locator('#id_month-trigger').press('Enter');
        await expect(page.locator('#id_month-choice-search')).toBeFocused();
        await page.keyboard.press('Escape');
        await expect(page.locator('#id_month-trigger')).toBeFocused();
        await expect(page.locator('main')).toContainText('250,00');

        await page.goto(goalUrl);
        await page.getByRole('link', { name: 'Reserve a balance', exact: true }).press('Enter');
        const sourceSearch = page.locator('#source-search');
        await expect(sourceSearch).toHaveValue('');
        await sourceSearch.focus();
        await sourceSearch.press('ArrowDown');
        await sourceSearch.press('Enter');
        await expect(sourceSearch).toHaveValue(/Planning cash/);
        await sourceSearch.press('Tab');
        const sourceClear = sourceSearch.locator('..').getByRole('button');
        await expect(sourceClear).toBeFocused();
        await sourceClear.press('Tab');
        const amountHelp = page.getByRole('button', { name: 'Explain Reserved amount', exact: true });
        await expect(amountHelp).toBeFocused();
        await page.keyboard.press('Escape');
        await page.keyboard.press('Tab');
        await expect(page.locator('#id_amount')).toBeFocused();
        await page.locator('#id_amount').fill('1500');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(page.locator('[role="alert"]').first()).toContainText('reservation exceeds');
        await expect(sourceSearch).toHaveValue(/Planning cash/);
        await expect(page.locator('#id_amount')).toHaveValue('1500');
        await page.locator('#id_amount').fill('200');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(page).toHaveURL(goalUrl);
        await expect(page.locator('main')).toContainText('200,00');
        await page.goto(`/banking/${bank}/`);
        const accountRow = page.locator('article[id^="account-row-"]').first();
        await expect(accountRow).toContainText('1.000,00');
        await expect(accountRow).toContainText('300,00');
        await expect(accountRow).toContainText('700,00');
        await page.goto(goalUrl);
        await page.screenshot({ path: testInfo.outputPath(`planning-goal-${theme}.png`), fullPage: true });
        await page.setViewportSize({ width: 390, height: 844 });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: testInfo.outputPath(`planning-goal-mobile-${theme}.png`), fullPage: true });
        await page.getByRole('button', { name: 'Archive goal', exact: true }).press('Enter');
        await expect(page.locator('main')).toContainText('Reservations are released');
        await page.getByRole('button', { name: 'Restore goal', exact: true }).press('Enter');
        await expect(page.getByRole('button', { name: 'Archive goal', exact: true })).toBeVisible();
        await page.goto('/planning/signals/');
        await page.getByRole('link', { name: 'Signal settings', exact: true }).press('Enter');
        await page.locator('#id_duplicate_days').fill('99');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(page.locator('[role="alert"]').first()).toBeVisible();
        await expect(page.locator('#id_duplicate_days')).toHaveValue('99');
    });
}

test('personal planning submits native budgets, goals and source choices without JavaScript', async ({ browser }, testInfo) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    try {
        const { category, goalUrl } = await seed(page, testInfo);
        await page.goto('/planning/budgets/create/');
        await page.locator('#id_category').selectOption(category);
        await page.locator('#id_amount').fill('250');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(page.locator('main')).toContainText('250,00');
        await page.goto(`${goalUrl}reserve/`);
        const source = page.locator('#id_source');
        await expect(source).toBeVisible();
        await source.focus();
        await source.press('Home');
        await source.press('ArrowDown');
        await source.press('Tab');
        await page.locator('#id_amount').fill('100');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(page).toHaveURL(goalUrl);
        await expect(page.locator('main')).toContainText('100,00');
        await page.getByRole('button', { name: 'Release reservation', exact: true }).press('Enter');
        await expect(page.locator('main')).toContainText('No balance reserved');
    } finally { await context.close(); }
});
