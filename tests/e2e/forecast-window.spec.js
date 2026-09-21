// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function signUp(page, testInfo) {
    const username = `forecast-${testInfo.workerIndex}-${Date.now()}`;
    await page.goto('/accounts/signup/');
    await page.locator('#id_username').fill(username);
    await page.locator('#id_email').fill(`${username}@example.test`);
    await page.locator('#id_password1').fill('Tuxedo-E2E-2026!');
    await page.locator('#id_password2').fill('Tuxedo-E2E-2026!');
    await page.getByRole('button', { name: 'Sign up' }).click();
    await expect(page).toHaveURL(/\/dashboard\/$/);
}

for (const dark of [false, true]) {
    test(`report forecast boundary retains keyboard focus (${dark ? 'dark' : 'light'})`, async ({ page }, testInfo) => {
        await signUp(page, testInfo);
        await page.goto('/dashboard/reports/?charts_offset=4');
        await page.evaluate(value => {
            document.documentElement.classList.toggle('dark', value);
            localStorage.setItem('theme', value ? 'dark' : 'light');
        }, dark);
        const next = page.locator('#report-cashflow-next');
        await next.focus();
        const top = await page.evaluate(() => window.scrollY);
        expect(top).toBeGreaterThan(0);
        await next.press('Enter');
        await expect(page).toHaveURL(/charts_offset=5/);
        await expect(next).toHaveText('Forecast limit');
        await expect(next).toBeFocused();
        await expect(page.getByRole('link', { name: 'Next window', exact: true })).toHaveCount(0);
        expect(Math.abs(await page.evaluate(() => window.scrollY) - top)).toBeLessThan(4);
        await page.locator('#report-cashflow-previous').focus();
        await page.keyboard.press('Enter');
        await expect(page).toHaveURL(/charts_offset=4/);
        await expect(page.locator('#report-cashflow-previous')).toBeFocused();
        await expect(next).toHaveAttribute('href', /charts_offset=5/);
    });
}

test('report forecast limit works without JavaScript', async ({ browser }, testInfo) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    try {
        await signUp(page, testInfo);
        await page.goto('/dashboard/reports/?charts_offset=4');
        await page.locator('#report-balance-next').press('Enter');
        await expect(page).toHaveURL(/charts_offset=5/);
        await expect(page.locator('#report-balance-next')).toHaveText('Forecast limit');
        await expect(page.getByRole('link', { name: 'Next window', exact: true })).toHaveCount(0);
        await page.locator('#report-balance-previous').press('Enter');
        await expect(page).toHaveURL(/charts_offset=4/);
    } finally {
        await context.close();
    }
});
