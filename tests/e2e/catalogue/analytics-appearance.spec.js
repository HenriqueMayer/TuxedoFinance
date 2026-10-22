// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {openCatalogue} = require('../helpers/catalogue');

for (const theme of ['light', 'dark']) {
    for (const width of [1440, 320]) {
        test(`catalogue Analytics and native position identity (${theme}, ${width})`, async ({page}, info) => {
            await page.setViewportSize({width, height: 900});
            await openCatalogue(page, {hash: '#navigation', theme, waitForFonts: true});
            const home = page.locator('#lab-view-home');
            await expect(home.locator('svg.lab-sparkline')).toHaveCount(0);
            await home.getByRole('link', {name: 'View analyses for this month ↗'}).focus();
            await page.keyboard.press('Enter');
            await expect(page.locator('#lab-view-analytics')).toBeVisible();
            await expect(page.locator('[data-lab-destination="analytics"]')).toHaveAttribute('aria-current', 'page');
            await expect(page.locator('#lab-view-analytics .lab-local-tabs a')).toHaveText(['Finances', 'Investments']);
            await page.locator('[data-lab-destination="investments"]').press('Enter');
            const position = page.locator('#lab-view-investments');
            await expect(position.locator('.lab-local-tabs a')).toHaveText(['My investments', 'History', 'Prices', 'Setup']);
            const details = position.locator('#lab-position-personalization');
            await details.locator('summary').press('Enter');
            const icons = details.locator('input[type="radio"]');
            await expect(icons).toHaveCount(12);
            const reserve = details.locator('input[value="reserve"]');
            await reserve.focus();
            await page.keyboard.press('Space');
            await expect(reserve).toBeChecked();
            await details.getByRole('button', {name: 'Save icon'}).press('Enter');
            await expect(position.locator('[data-lab-position-icon]')).toHaveText('🛟');
            await expect(details.getByRole('status')).toContainText('No balance or financial record changed');
            for (const label of await details.locator('.lab-position-icons label').all()) {
                const bounds = await label.boundingBox();
                expect(bounds.height).toBeGreaterThanOrEqual(44);
                expect(bounds.x).toBeGreaterThanOrEqual(0);
                expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
            }
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            await page.screenshot({path: info.outputPath(`position-identity-${width}-${theme}.png`)});
        });
    }
}

test('catalogue position identity retains native selection without JavaScript', async ({browser}) => {
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 390, height: 900}});
    try {
        const page = await context.newPage();
        await openCatalogue(page, {hash: '#lab-view-investments'});
        const details = page.locator('#lab-position-personalization');
        await details.locator('summary').press('Enter');
        const home = details.locator('input[value="home"]');
        await home.focus();
        await page.keyboard.press('Space');
        await expect(home).toBeChecked();
        // Text selectors intentionally skip <noscript>; inspect its native fallback directly.
        const fallback = details.locator('noscript .subtle-copy');
        await expect(fallback).toHaveText('These are native choices. This static example does not persist settings.');
        await expect(fallback).toBeVisible();
    } finally {
        await context.close();
    }
});
