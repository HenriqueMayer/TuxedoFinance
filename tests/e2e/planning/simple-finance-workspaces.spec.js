// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, { form: { csrfmiddlewaretoken: token, ...values },
        headers: { Referer: response.url() }, maxRedirects: 0 });
    expect(saved.status(), await saved.text()).toBe(302);
    return saved.headers().location;
}

async function seed(page, info) {
    const username = `simple-finance-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', { username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' });
    await post(page, '/banking/create/', { name: 'Local bank' });
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', { bank, name: 'Daily account', currency: 'BRL',
        opening_balance: '1000', opening_date: '2025-01-01', reserved_amount: '200', planning_enabled: 'on', pix_enabled: 'on' });
    await post(page, '/investments/add/', { institution: bank, name: 'Travel reserve', currency: 'BRL',
        valuation_mode: 'MONETARY', purpose: 'MONTHLY_CASH', opening_balance: '100', opening_date: '2025-01-01' });
    await post(page, '/investments/add/', { institution: bank, name: 'Global fund', currency: 'BRL',
        valuation_mode: 'UNITS', opening_quantity: '2', opening_unit_price: '50', opening_date: '2025-01-01' });
    await post(page, '/categories/create/', { name: 'Daily food', transaction_type: 'EXPENSE' });
    await post(page, '/categories/create/', { name: 'Transport', transaction_type: 'EXPENSE' });
    await page.goto('/transactions/create/');
    const category = await page.locator('#id_category option').filter({ hasText: 'Daily food' }).getAttribute('value');
    const transport = await page.locator('#id_category option').filter({ hasText: /^\s*Transport\s*$/ }).getAttribute('value');
    const account = await page.locator('#id_bank_account option').filter({ hasText: 'Daily account' }).getAttribute('value');
    await page.goto('/planning/');
    const month = await page.locator('#id_month').inputValue();
    await post(page, '/transactions/create/', { title: 'Groceries', transaction_type: 'EXPENSE',
        amount: '50', category, payment_channel: 'ACCOUNT', bank_account: account, date: `${month}-01`, installments: '1' });
    await post(page, '/planning/budgets/create/', { category, month, currency: 'BRL', amount: '250' });
    await post(page, '/planning/budgets/create/', { category: transport, month, currency: 'BRL', amount: '120' });
    const goal = await post(page, '/planning/goals/create/', { name: 'Travel target', target_amount: '2000', currency: 'BRL',
        reserve_now: 'on', source: `account:${account}`, reserved_amount: '100' });
    return { month, goal };
}

async function noOverflow(page) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

for (const width of [390, 1440]) {
for (const theme of ['light', 'dark']) {
test(`simple finance workspaces keep data, keyboard, filters and context (${width}, ${theme})`, async ({ browser }, info) => {
    const portuguese = width === 390;
    const context = await browser.newContext({ viewport: { width, height: 820 }, hasTouch: width === 390, locale: portuguese ? 'pt-BR' : 'en-US' });
    const page = await context.newPage();
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    const dialogs = [];
    page.on('dialog', async dialog => { dialogs.push(dialog.message()); await dialog.dismiss(); });
    try {
        const { month } = await seed(page, info);
        await page.goto('/investments/');
        const positions = page.locator('#investment-position-list article:visible');
        await expect(positions).toHaveCount(2);
        await expect(page.locator('#investment-total')).toContainText(/BRL 200[,.]00/);
        await expect(page.locator('#investment-price-warning')).toBeVisible();
        const filter = page.locator('#position-extra-filters > summary');
        // Touch activation first scrolls its target into view using the control's
        // viewport margins. Establish the rail baseline after that preparation,
        // then verify opening the disclosure itself changes neither rail nor scroll.
        await filter.scrollIntoViewIfNeeded();
        const before = await filter.boundingBox();
        const filterScroll = await page.evaluate(() => window.scrollY);
        if (width === 390) await filter.tap();
        else await filter.press('Enter');
        await expect(page.locator('#position-scope')).toBeVisible();
        const after = await filter.boundingBox();
        expect(Math.abs(before.x - after.x)).toBeLessThan(1);
        expect(Math.abs(before.y - after.y)).toBeLessThan(1);
        expect(await page.evaluate(() => window.scrollY)).toBeCloseTo(filterScroll, 0);
        await page.locator('#position-scope').focus();
        await page.keyboard.press('End');
        await page.keyboard.press('Tab');
        await expect(page).toHaveURL(url => url.searchParams.get('scope') === 'cash');
        await expect(positions).toHaveCount(1);
        await expect(positions).toContainText('Travel reserve');
        await expect(page.locator('#investment-total')).toContainText(/BRL 100[,.]00/);
        await page.locator('#position-search').pressSequentially('missing');
        await expect(page).toHaveURL(url => url.searchParams.get('q') === 'missing');
        await expect(positions).toHaveCount(0);
        await expect(page.locator('#position-search')).toBeFocused();
        await expect(page.locator('#investment-total')).toContainText(/BRL 100[,.]00/);
        await page.locator('#position-value-details > summary').press('Enter');
        await page.locator('#position-search').fill('');
        await expect(positions).toHaveCount(1);
        await expect(page.locator('#position-value-details')).toHaveAttribute('open', '');
        await page.locator('#position-filter-clear a').press('Enter');
        await expect(positions).toHaveCount(2);
        const row = positions.filter({ hasText: 'Travel reserve' });
        await row.getByRole('link', { name: portuguese ? 'Atualizar' : 'Update', exact: true }).press('Enter');
        await expect(page.locator('.position-update-choice')).toHaveCount(3);
        await noOverflow(page);
        await page.getByRole('link', { name: portuguese ? 'Cancelar' : 'Cancel', exact: true }).press('Enter');
        await expect(page).toHaveURL(/#position-\d+-\d+(?:-mobile)?$/);
        await expect(row).toBeInViewport();
        await row.getByRole('link', { name: portuguese ? 'Atualizar' : 'Update', exact: true }).press('Enter');
        await page.locator('a[href*="kind=YIELD"]').press('Enter');
        await page.getByRole('link', { name: portuguese ? 'Cancelar' : 'Cancel', exact: true }).press('Enter');
        await expect(row).toBeInViewport();
        await page.screenshot({ path: info.outputPath(`investments-${width}-${theme}.png`), fullPage: true });

        await page.goto('/planning/');
        await expect(page.locator('[data-monthly-available]')).toContainText(/BRL 750[,.]00/);
        await expect(page.locator('.monthly-outlook .status-badge')).toHaveText(portuguese ? 'Projeção' : 'Projection');
        // The excluded 100 cash pot joins the account's 200 reserve; its real
        // balance stays recorded while available cash remains 750.
        await expect(page.locator('.monthly-outlook-metrics')).toContainText(/BRL 300[,.]00/);
        await expect(page.locator('.budget-row')).toHaveCount(2);
        await expect(page.locator('.budget-row').filter({ hasText: 'Daily food' }).locator('progress')).toHaveAttribute('value', '20');
        await expect(page.locator('.budget-row').filter({ hasText: 'Daily food' }).locator('progress')).toHaveCSS('accent-color', 'rgb(184, 138, 89)');
        const calculation = page.locator('#monthly-calculation');
        await calculation.locator('summary').press('Enter');
        await expect(calculation).toHaveAttribute('open', '');
        const trigger = page.locator('#id_month-trigger');
        await trigger.press('Enter');
        const search = page.locator('#id_month-choice-search');
        await expect(search).toBeFocused();
        await page.locator('#id_month-year').fill('');
        await page.locator('#id_month-year').press('Enter');
        await expect(page.locator('#id_month-year')).toHaveAttribute('aria-invalid', 'true');
        await expect(page.locator('#id_month')).toHaveValue(month);
        await page.keyboard.press('Escape');
        await expect(trigger).toBeFocused();
        await trigger.press('Enter');
        await search.pressSequentially(portuguese ? 'sete' : 'sep');
        await search.press('Enter');
        await expect(page).toHaveURL(url => url.searchParams.get('month') === `${month.slice(0, 4)}-09`);
        await expect(trigger).toBeFocused();
        await expect(calculation).toHaveAttribute('open', '');
        await trigger.press('Enter');
        await page.locator('#id_month-panel').getByRole('button', { name: portuguese ? 'Este mês' : 'This month', exact: true }).press('Enter');
        await expect(page).toHaveURL(url => url.searchParams.get('month') === month);
        await expect(page.locator('.budget-row')).toHaveCount(2);
        await page.goBack();
        await expect(page.locator('#id_month')).toHaveValue(`${month.slice(0, 4)}-09`);
        await page.goForward();
        await expect(page.locator('#id_month')).toHaveValue(month);
        await expect(page.locator('.budget-row')).toHaveCount(2);
        await noOverflow(page);
        await page.screenshot({ path: info.outputPath(`planning-${width}-${theme}.png`), fullPage: true });
        await page.locator('nav[aria-label]').getByRole('link', { name: portuguese ? 'Metas' : 'Goals', exact: true }).press('Enter');
        await expect(page.locator('.goal-card')).toHaveCount(1);
        await expect(page.locator('.goal-card progress')).toHaveAttribute('value', '5');
        const goalFilter = page.locator('#goal-extra-filters > summary');
        const goalBefore = await goalFilter.boundingBox();
        await goalFilter.press('Enter');
        const goalAfter = await goalFilter.boundingBox();
        expect(Math.abs(goalBefore.y - goalAfter.y)).toBeLessThan(1);
        await page.locator('#goal-filters input[name="archived"]').press('Space');
        await expect(page).toHaveURL(url => url.searchParams.get('archived') === '1');
        await page.locator('#goal-query').pressSequentially('Travel');
        await expect(page).toHaveURL(url => url.searchParams.get('q') === 'Travel');
        await expect(page.locator('#goal-query')).toBeFocused();
        await noOverflow(page);
        await page.screenshot({ path: info.outputPath(`goals-${width}-${theme}.png`), fullPage: true });
        await page.locator('.goal-card .investment-name').press('Enter');
        await page.getByRole('link', { name: portuguese ? 'Editar meta' : 'Edit goal', exact: true }).press('Enter');
        await expect(page.locator('label[for="id_target_amount"]')).toContainText(portuguese ? 'Valor da meta' : 'Goal amount');
        await page.getByRole('textbox', { name: portuguese ? 'Valor da meta *' : 'Goal amount *', exact: true }).focus();
        await expect(page.locator('#id_target_amount')).toBeFocused();
        await page.goto('/planning/tools/');
        await expect(page).toHaveURL(/\/sandbox\/$/);
        await expect(page.locator('[data-planning-navigation] > a')).toHaveCount(4);
        const simulationLinks = page.locator('[data-simulation-navigation] > a');
        await expect(simulationLinks).toHaveCount(3);
        await simulationLinks.first().focus();
        await page.keyboard.press('Tab');
        await expect(simulationLinks.nth(1)).toBeFocused();
        await noOverflow(page);
        await page.screenshot({ path: info.outputPath(`planning-tools-${width}-${theme}.png`), fullPage: true });
        expect(dialogs).toEqual([]);
    } finally { await context.close(); }
});
}
}

test('simple finance workspaces retain native filters, monthly errors and budget actions', async ({ browser }, info) => {
    const context = await browser.newContext({ javaScriptEnabled: false, locale: 'en-US', viewport: { width: 390, height: 820 } });
    const page = await context.newPage();
    try {
        const { month } = await seed(page, info);
        await page.goto('/investments/');
        await page.locator('#position-extra-filters > summary').press('Enter');
        await page.locator('#position-scope').selectOption('cash');
        await page.getByRole('button', { name: 'Search', exact: true }).press('Enter');
        await expect(page.locator('#investment-position-list article:visible')).toHaveCount(1);
        await page.goto('/planning/?month=invalid');
        await expect(page.locator('#id_month')).toHaveAttribute('aria-invalid', 'true');
        await expect(page.locator('#id_month')).toHaveValue('invalid');
        await page.locator('#id_month').fill(month);
        await page.getByRole('button', { name: 'Show month', exact: true }).press('Enter');
        await expect(page.locator('.budget-row')).toHaveCount(2);
        const budget = page.locator('.budget-row').filter({ hasText: 'Daily food' });
        await budget.locator('details > summary').press('Enter');
        await expect(budget).toContainText(/BRL 50[,.]00/);
        await budget.getByRole('button', { name: 'Remove limit', exact: true }).press('Enter');
        await expect(page.locator('.budget-row')).toHaveCount(1);
        await page.goto('/planning/goals/');
        await page.locator('#goal-extra-filters > summary').press('Enter');
        await page.locator('#goal-filters input[name="archived"]').press('Space');
        await page.getByRole('button', { name: 'Apply filters', exact: true }).press('Enter');
        await expect(page).toHaveURL(url => url.searchParams.get('archived') === '1');
        await expect(page.locator('.goal-card')).toHaveCount(1);
        await noOverflow(page);
    } finally { await context.close(); }
});
