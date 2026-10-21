// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {openCatalogue} = require('../helpers/catalogue');

for (const theme of ['light', 'dark']) for (const width of [1440, 320]) {
    test(`planning specimen keeps native sections and readable goals (${theme}, ${width})`, async ({page}, info) => {
        await page.setViewportSize({width, height: 900});
        await openCatalogue(page, {hash: '#lab-planning-navigation', theme, waitForFonts: true});
        const sections = page.getByRole('navigation', {name: 'Example planning sections'});
        await expect(sections.locator('a')).toHaveText(['This month', 'Goals', 'Simulations', 'Alerts']);
        await sections.getByRole('link', {name: 'Goals', exact: true}).focus();
        await page.keyboard.press('Enter');
        await expect(page).toHaveURL(/#lab-planning-goals$/);
        await expect.poll(() => page.evaluate(() => document.querySelector('#lab-planning-goals-title').getBoundingClientRect().top
            - document.querySelector('[data-catalogue-header]').getBoundingClientRect().bottom)).toBeGreaterThanOrEqual(0);
        await expect(page.locator('#lab-planning-goals progress')).toHaveAttribute('value', '20');
        await expect(page.locator('#lab-planning-goals')).toContainText('BRL 1,200.00');
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({path: info.outputPath(`planning-catalogue-${theme}-${width}.png`)});
    });
}
