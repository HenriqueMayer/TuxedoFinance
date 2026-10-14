// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { resolve } = require('node:path');

// Serve only the checked-in catalogue and public assets through the isolated
// executor's origin; the catalogue keeps its own documentation navigation.
async function openCatalogue(page) {
    const root = resolve(__dirname, '../..');
    await page.route('**/catalogue/**', async route => {
        const name = new URL(route.request().url()).pathname.slice('/catalogue/'.length);
        if (name !== 'docs/design-system.html' && !name.startsWith('static/')) return route.abort();
        if (name.split('/').includes('..')) return route.abort();
        const types = { html: 'text/html', css: 'text/css', js: 'application/javascript', woff2: 'font/woff2', png: 'image/png', ico: 'image/x-icon' };
        await route.fulfill({ path: resolve(root, name), contentType: types[name.split('.').pop()] });
    });
    await page.goto('/catalogue/docs/design-system.html');
}

for (const theme of ['light', 'dark']) {
    test(`catalogue records direct workspaces and deliberate account options (${theme})`, async ({ page }, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({ width: 1440, height: 900 });
        await openCatalogue(page);
        const sample = page.locator('#catalogue-workspace-shell');
        const desktop = page.getByRole('navigation', { name: 'Example desktop workspaces' });
        await expect(desktop.getByRole('link')).toHaveText(['Home', 'Transactions', 'Accounts', 'Investments', 'Plan']);
        await expect(sample.locator('[data-nav-menu]')).toHaveCount(0);
        await expect(page.getByRole('navigation', { name: 'Example Home sections' }).getByRole('link')).toHaveText(['Dashboard', 'Reports', 'Net worth']);
        await desktop.getByRole('link', { name: 'Home', exact: true }).focus();
        await page.keyboard.press('Tab');
        await expect(desktop.getByRole('link', { name: 'Transactions', exact: true })).toBeFocused();
        const options = sample.locator('header details.secondary-actions');
        await options.locator('summary').hover();
        await expect(options).not.toHaveAttribute('open', '');
        await options.locator('summary').press('Space');
        await expect(options).toHaveAttribute('open', '');
        await page.keyboard.press('Escape');
        await expect(options).not.toHaveAttribute('open', '');
        await expect(options.locator('summary')).toBeFocused();
        for (const width of [1440, 390]) {
            await page.setViewportSize({ width, height: 900 });
            const navigation = page.getByRole('navigation', { name: width >= 1024 ? 'Example desktop workspaces' : 'Example mobile workspaces' });
            await expect(navigation.getByRole('link')).toHaveCount(5);
            await sample.scrollIntoViewIfNeeded();
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            await page.screenshot({ path: info.outputPath(`catalogue-navigation-${width}-${theme}.png`) });
        }
        await page.locator('#menu-btn').click();
        const dialog = page.locator('#mobile-menu');
        await expect(dialog).toHaveAttribute('aria-hidden', 'false');
        await expect(dialog.locator('[data-nav-item]')).toHaveCount(0);
        await page.keyboard.press('Escape');
        await expect(dialog).toHaveAttribute('aria-hidden', 'true');
        await expect(page.locator('#menu-btn')).toBeFocused();
        await expect(page.locator('body > header').getByRole('link', { name: 'Nav', exact: true })).toHaveAttribute('href', '#navigation');
    });
}
