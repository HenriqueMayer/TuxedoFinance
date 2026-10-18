// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const result = await page.request.post(path, { form: { csrfmiddlewaretoken: token, ...values }, headers: { Referer: response.url() }, maxRedirects: 0 });
    expect(result.status(), await result.text()).toBe(302);
    return result.headers().location;
}
async function seed(page, info) {
    const username = `simple-month-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', { username, email: `${username}@example.test`, password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' });
    await post(page, '/banking/create/', { name: 'Monthly bank' });
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', { bank, name: 'Monthly cash', currency: 'BRL', opening_balance: '1000', opening_date: '2020-01-01', reserved_amount: '200', planning_enabled: 'on' });
    await post(page, '/categories/create/', { name: 'Monthly groceries', transaction_type: 'EXPENSE' });
    await page.goto('/planning/budgets/create/');
    const category = await page.locator('#id_category option').filter({ hasText: 'Monthly groceries' }).getAttribute('value');
    const month = await page.locator('#id_month').inputValue();
    await post(page, '/planning/budgets/create/', { category, month, amount: '250', currency: 'BRL' });
    await post(page, '/planning/goals/create/', { name: 'Emergency reserve', target_amount: '2000', currency: 'BRL' });
    await post(page, '/planning/goals/create/', { name: 'Travel fund', target_amount: '500', currency: 'BRL' });
    return { month };
}
for (const theme of ['light', 'dark']) for (const language of ['en', 'pt-br']) for (const width of [1366, 390]) {
    test(`simple monthly workspace, live goals and paused areas (${theme}, ${language}, ${width})`, async ({ page }, info) => {
        const { month } = await seed(page, info);
        const errors = [], dialogs = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('dialog', async dialog => { dialogs.push(dialog.message()); await dialog.dismiss(); });
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.context().addCookies([{ name: 'django_language', value: language, url: info.project.use.baseURL }]);
        await page.setViewportSize({ width, height: 844 });
        await page.goto('/planning/');
        await expect(page.locator('html')).toHaveAttribute('lang', language);
        const sections = page.locator('nav[aria-label="' + (language === 'en' ? 'Planning sections' : 'Seções de planejamento') + '"]');
        await expect(sections.getByRole('link')).toHaveCount(3);
        await expect(page.getByRole('heading', { name: language === 'en' ? 'Plan this month' : 'Planejar este mês', exact: true })).toBeVisible();
        await expect(page.locator('#monthly-results')).toContainText('800,00');
        await expect(page.locator('#budgets')).toContainText('250,00');
        await expect(page.locator('[data-live-submit]')).toBeHidden();
        await page.screenshot({ path: info.outputPath(`month-${theme}-${language}-${width}.png`), fullPage: true });
        const previous = new Date(Number(month.slice(0, 4)), Number(month.slice(5)) - 2, 1);
        const earlier = `${previous.getFullYear()}-${String(previous.getMonth() + 1).padStart(2, '0')}`;
        const monthTrigger = page.locator('#id_month-trigger');
        const monthSearch = page.locator('#id_month-choice-search');
        const monthPanel = page.locator('#id_month-panel');
        const year = page.locator('#id_month-year');
        await expect(page.locator('#id_month')).toBeHidden();
        await monthTrigger.press('Enter');
        await expect(monthSearch).toBeFocused();
        // The native ISO field is only the no-JavaScript fallback. Exercise
        // the shared month choice, including January's previous-year boundary.
        await page.keyboard.press('Shift+Tab');
        await expect(year).toBeFocused();
        await page.keyboard.press('ControlOrMeta+A');
        await page.keyboard.type(String(previous.getFullYear()));
        await year.press('Enter');
        await expect(monthSearch).toBeFocused();
        await monthSearch.press('ControlOrMeta+A');
        await monthSearch.pressSequentially(new Intl.DateTimeFormat(language, { month: 'long' }).format(previous));
        await expect(monthPanel.getByRole('option')).toHaveCount(1);
        await monthSearch.press('Enter');
        await expect(page).toHaveURL(url => url.searchParams.get('month') === earlier);
        await expect(page.locator('#id_month')).toHaveValue(earlier);
        await expect(monthPanel).toBeHidden();
        await expect(monthTrigger).toBeFocused();
        await expect(page.locator('#budgets')).not.toContainText('Monthly groceries');
        await page.goBack();
        await expect(page.locator('#id_month')).toHaveValue(month);
        await expect(page.locator('#budgets')).toContainText('Monthly groceries');
        await page.goForward();
        await expect(page.locator('#id_month')).toHaveValue(earlier);
        await page.goto('/planning/goals/');
        const search = page.locator('#goal-query');
        await search.focus();
        await search.pressSequentially('Emergency', { delay: 20 });
        await expect(page.locator('#goal-results')).toContainText('Emergency reserve');
        await expect(page.locator('#goal-results')).not.toContainText('Travel fund');
        await expect(search).toBeFocused();
        await search.press('ControlOrMeta+A'); await search.press('Backspace');
        await expect(page.locator('#goal-results')).toContainText('Travel fund');
        await page.locator('#goal-extra-filters > summary').press('Enter');
        await expect(page.locator('#goal-extra-filters')).toHaveAttribute('open', '');
        await page.keyboard.press('Tab');
        await expect(page.locator('input[name="archived"]')).toBeFocused();
        await page.locator('input[name="archived"]').press('Space');
        await expect(page).toHaveURL(/archived=1/);
        await page.locator('#goal-filter-clear a').press('Enter');
        await expect(page.locator('input[name="archived"]')).not.toBeChecked();
        await page.goto('/planning/tools/');
        for (const href of ['/planning/signals/', '/sandbox/', '/sandbox/simulation/', '/sandbox/drafts/']) await expect(page.locator(`main a[href="${href}"]`)).toBeVisible();
        await page.goto('/imports/');
        await expect(page).toHaveURL(/\/transactions\/$/);
        await page.goto('/dashboard/wealth/');
        await expect(page).toHaveURL(/\/dashboard\/$/);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        expect(dialogs).toEqual([]); expect(errors).toEqual([]);
    });
}

test.describe('native monthly consultation', () => {
    test.use({ javaScriptEnabled: false });
    test('month and goal filters still submit without JavaScript', async ({ page }, info) => {
        const { month } = await seed(page, info);
        await page.goto('/planning/');
        await expect(page.getByRole('button', { name: 'Show month', exact: true })).toBeVisible();
        await page.locator('#id_month').fill(month);
        await page.getByRole('button', { name: 'Show month', exact: true }).press('Enter');
        await expect(page.locator('#budgets')).toContainText('Monthly groceries');
        await page.goto('/planning/goals/');
        await page.locator('#goal-query').fill('Travel');
        await page.getByRole('button', { name: 'Apply filters', exact: true }).press('Enter');
        await expect(page.locator('#goal-results')).toContainText('Travel fund');
        await expect(page.locator('#goal-results')).not.toContainText('Emergency reserve');
        await page.goto('/imports/'); await expect(page).toHaveURL(/\/transactions\/$/);
    });
});
