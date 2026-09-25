// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function signup(page, info) {
    const response = await page.request.get('/accounts/signup/');
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const username = `export-menu-${info.workerIndex}-${Date.now()}`;
    const saved = await page.request.post('/accounts/signup/', {
        form: {csrfmiddlewaretoken: csrf, username, email: `${username}@example.test`,
            password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'},
        headers: {Referer: response.url()}, maxRedirects: 0,
    });
    expect(saved.status(), await saved.text()).toBe(302);
}

for (const theme of ['light', 'dark']) {
    test(`Export CSV opens only on activation (${theme})`, async ({page}, info) => {
        await signup(page, info);
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.goto('/transactions/');
        const menu = page.locator('[data-export-menu]');
        const trigger = menu.locator(':scope > summary');
        await trigger.hover();
        await expect(menu).not.toHaveAttribute('open', '');
        await trigger.focus();
        await expect(menu).not.toHaveAttribute('open', '');
        await trigger.click();
        await expect(menu).toHaveAttribute('open', '');
        await page.locator('main h1').hover();
        await expect(menu).toHaveAttribute('open', '');
        await menu.getByRole('link', {name: 'Export all transactions'}).hover();
        await expect(menu).toHaveAttribute('open', '');
        await page.screenshot({path: info.outputPath(`export-${theme}.png`)});
        await page.keyboard.press('Escape');
        await expect(menu).not.toHaveAttribute('open', '');
        await expect(trigger).toBeFocused();
        await trigger.press('Space');
        await expect(menu).toHaveAttribute('open', '');
        await page.locator('main h1').click();
        await expect(menu).not.toHaveAttribute('open', '');
    });
}

test('Export CSV native disclosure requires activation without JavaScript', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false});
    const page = await context.newPage();
    try {
        await signup(page, info);
        await page.goto('/transactions/');
        const menu = page.locator('[data-export-menu]');
        await menu.locator(':scope > summary').hover();
        await expect(menu).not.toHaveAttribute('open', '');
        await menu.locator(':scope > summary').press('Enter');
        await expect(menu).toHaveAttribute('open', '');
        await expect(menu.getByRole('link', {name: 'Export all transactions'})).toBeVisible();
    } finally { await context.close(); }
});
