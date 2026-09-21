// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const result = await page.request.post(path, { form: { csrfmiddlewaretoken: token, ...values },
        headers: { Referer: response.url() }, maxRedirects: 0 });
    expect(result.status(), await result.text()).toBe(302);
}
async function seed(page, testInfo) {
    const username = `reserves-${testInfo.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', { username, email: `${username}@example.test`, password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' });
    await post(page, '/banking/create/', { name: 'Monthly bank' });
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', { bank, name: 'Monthly account', currency: 'BRL', opening_balance: '5000', pix_enabled: 'on', planning_enabled: 'on', reserved_amount: '2000' });
    await page.goto('/banking/');
    return bank;
}
for (const dark of [false, true]) {
    test(`bank reserves and account toggle preserve money, focus and position (${dark ? 'dark' : 'light'})`, async ({ page }, testInfo) => {
        await seed(page, testInfo);
        await page.evaluate(value => { document.documentElement.classList.toggle('dark', value); localStorage.setItem('theme', value ? 'dark' : 'light'); }, dark);
        const row = page.locator('tr[data-preserve-view]').first();
        await expect(row).toContainText('3.000,00');
        const toggle = row.getByRole('button', { name: 'Set aside Monthly account', exact: true });
        await toggle.focus();
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        const top = await page.evaluate(() => window.scrollY);
        await toggle.press('Enter');
        await expect(row.getByRole('button', { name: 'Use Monthly account in planning', exact: true })).toBeFocused();
        await expect(row.locator('td').nth(1)).toContainText('5.000,00');
        await expect(row.locator('td').nth(3)).toContainText('0,00');
        // Focus is restored after swap; viewport restoration also runs after
        // HTMX settles attributes and the browser performs its final reflow.
        await expect.poll(async () => Math.abs(await page.evaluate(() => window.scrollY) - top)).toBeLessThan(4);
        await expect(page.locator('#planning-availability')).toContainText('BRL 0,00');
        await page.keyboard.press('Space');
        await expect(row.getByRole('button', { name: 'Set aside Monthly account', exact: true })).toBeFocused();
        await expect(row.locator('td').nth(3)).toContainText('3.000,00');
        await page.screenshot({ path: testInfo.outputPath(`banks-${dark ? 'dark' : 'light'}.png`), fullPage: true });
        await page.setViewportSize({ width: 390, height: 844 });
        await expect(row).toHaveCSS('display', 'grid');
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        for (const cell of await row.locator('td[data-label]').all()) {
            const bounds = await cell.boundingBox();
            expect(bounds.x).toBeGreaterThanOrEqual(16);
            expect(bounds.x + bounds.width).toBeLessThanOrEqual(374);
        }
        await page.screenshot({ path: testInfo.outputPath(`banks-mobile-${dark ? 'dark' : 'light'}.png`), fullPage: true });
        await row.getByRole('link', { name: 'Edit Monthly account and reserve' }).click();
        await page.getByLabel('Reserved amount', { exact: true }).fill('-1');
        await page.getByRole('button', { name: 'Save', exact: true }).click();
        await expect(page.locator('[role="alert"]').first()).toBeVisible();
        await expect(page.getByLabel('Reserved amount', { exact: true })).toHaveValue('-1');
    });
}

test('bank controls and category options remain usable without JavaScript', async ({ browser }, testInfo) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    try {
        await seed(page, testInfo);
        await page.getByRole('button', { name: 'Set aside Monthly account', exact: true }).click();
        await expect(page.getByRole('button', { name: 'Use Monthly account in planning', exact: true })).toBeVisible();
        await page.goto('/categories/');
        await page.locator('main').getByText('More options', { exact: true }).press('Enter');
        await expect(page.getByRole('link', { name: 'Export CSV for spreadsheets', exact: true })).toBeVisible();
        await page.getByLabel('Type', { exact: true }).selectOption('unclassified');
        await page.getByRole('button', { name: 'Filter', exact: true }).click();
        await expect(page).toHaveURL(/type=unclassified/);
        await page.setViewportSize({ width: 390, height: 740 });
        await expect(page.getByRole('link', { name: 'Planning', exact: true })).toBeVisible();
        await expect(page.getByRole('button', { name: 'Log out', exact: true })).toBeVisible();
        await page.locator('#language-select-mobile-native').selectOption('pt-br');
        await page.locator('#language-select-mobile-native').locator('..').getByRole('button', { name: 'Apply', exact: true }).click();
        await expect(page.locator('html')).toHaveAttribute('lang', 'pt-br');
        await expect(page.getByRole('link', { name: 'Planejamento', exact: true })).toBeVisible();
    } finally { await context.close(); }
});
