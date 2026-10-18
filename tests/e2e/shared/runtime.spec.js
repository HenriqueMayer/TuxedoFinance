// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

for (const theme of ['light', 'dark']) {
    test(`runtime serves styled keyboard login and server errors in ${theme} theme`, async ({ page }, testInfo) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const failures = [];
        page.on('pageerror', error => failures.push(error.message));
        page.on('response', response => {
            if (response.url().includes('/static/') && response.status() >= 400) failures.push(response.url());
        });
        await page.goto('/accounts/login/');
        await expect(page.locator('html')).toHaveClass(theme === 'dark' ? /dark/ : /^(?!.*dark)/);
        const username = page.getByLabel(/^\s*Username/);
        await username.focus();
        await page.keyboard.type('nonexistent-runtime-user');
        await page.keyboard.press('Tab');
        await expect(page.getByLabel(/^\s*Password/)).toBeFocused();
        await page.keyboard.type('invalid-password');
        const response = page.waitForResponse(r => r.request().method() === 'POST' && r.url().includes('/accounts/login/'));
        await page.keyboard.press('Enter');
        expect((await response).status()).toBe(200);
        await expect(page.getByText('Please enter a correct username and password.')).toBeVisible();
        await expect(username).toHaveValue('nonexistent-runtime-user');
        await username.focus();
        await expect(username).toBeFocused();
        expect(await username.evaluate(element => getComputedStyle(element).boxShadow)).not.toBe('none');
        expect(await page.locator('form[novalidate]').evaluate(element => getComputedStyle(element).borderRadius)).not.toBe('0px');
        expect(failures).toEqual([]);
        await page.screenshot({ path: testInfo.outputPath(`login-${theme}.png`), fullPage: true });
    });
}
