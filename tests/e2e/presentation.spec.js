// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function signUp(page, testInfo) {
    await page.goto('/accounts/signup/');
    const name = `presentation-${testInfo.workerIndex}-${Date.now()}`;
    await page.locator('#id_username').fill(name);
    await page.locator('#id_email').fill(`${name}@example.test`);
    await page.locator('#id_password1').fill('Tuxedo-E2E-2026!');
    await page.locator('#id_password2').fill('Tuxedo-E2E-2026!');
    await page.getByRole('button', { name: 'Sign up', exact: true }).click();
    await expect(page).not.toHaveURL(/signup/);
}

for (const theme of ['light', 'dark']) {
    test(`bank and field explanations stay in contextual help (${theme})`, async ({ page }, testInfo) => {
        await signUp(page, testInfo);
        await page.evaluate(value => localStorage.setItem('theme', value), theme);
        await page.goto('/banking/');
        const card = page.locator('#planning-availability');
        await expect(card).toHaveClass(/surface-panel/);
        const help = card.getByRole('button', { name: 'Explain Available for planning', exact: true });
        const panel = page.locator('#bank-planning-help');
        await expect(panel).toBeHidden();
        await help.hover();
        await expect(panel).toBeVisible();
        await expect(panel).toContainText('Before upcoming bills.');
        await panel.hover();
        await expect(panel).toBeVisible();
        await page.getByRole('heading', { name: 'Banks', exact: true }).hover();
        await expect(panel).toBeHidden();
        await help.focus();
        await page.keyboard.press('Enter');
        await expect(panel).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(panel).toBeHidden();
        await expect(help).toBeFocused();

        await page.goto('/banking/accounts/create/');
        const reserve = page.getByRole('button', { name: 'Explain Reserved amount', exact: true });
        await reserve.press('Enter');
        await expect(page.locator('#id_reserved_amount-help')).toBeVisible();
        await page.keyboard.press('Escape');
        await page.getByLabel('Reserved amount', { exact: true }).fill('-1');
        await page.getByRole('button', { name: 'Save', exact: true }).click();
        await expect(page.getByLabel('Reserved amount', { exact: true })).toHaveValue('-1');
        await expect(page.locator('#id_reserved_amount-error-1')).toBeVisible();
        await page.setViewportSize({ width: 390, height: 740 });
        await page.getByRole('button', { name: 'Explain Reserved amount', exact: true }).press('Enter');
        const box = await page.locator('#id_reserved_amount-help').boundingBox();
        expect(box.x).toBeGreaterThanOrEqual(12);
        expect(box.x + box.width).toBeLessThanOrEqual(378);
        await page.screenshot({ path: testInfo.outputPath(`field-help-${theme}.png`), fullPage: true });
    });
}

test('native field help remains readable on mobile without JavaScript', async ({ browser }, testInfo) => {
    const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 740 } });
    try {
        const page = await context.newPage();
        await signUp(page, testInfo);
        await page.goto('/banking/accounts/create/');
        // Native summary exposes its own accessible name, without the hidden JS button.
        const summary = page.locator('summary[aria-label="Explain Reserved amount"]');
        await summary.press('Enter');
        const content = summary.locator('..').locator('.help-fallback-content');
        await expect(content).toBeVisible();
        const box = await content.boundingBox();
        expect(box.x).toBeGreaterThanOrEqual(12);
        expect(box.x + box.width).toBeLessThanOrEqual(378);
        expect(box.y).toBeGreaterThanOrEqual(0);
        expect(box.y + box.height).toBeLessThanOrEqual(740);
        await summary.press('Enter');
        await expect(content).toBeHidden();
    } finally { await context.close(); }
});
