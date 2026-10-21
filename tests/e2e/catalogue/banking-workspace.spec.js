// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {openCatalogue} = require('../helpers/catalogue');

for (const theme of ['light', 'dark']) for (const width of [1440, 320]) {
    test(`account specimens keep four sections and separate debt from points (${theme}, ${width})`, async ({page}, info) => {
        await page.setViewportSize({width, height: 900});
        await openCatalogue(page, {hash: '#lab-banking-navigation', theme, waitForFonts: true});
        // The technical catalogue is English; the application tests own both
        // translated interfaces and the catalogue retains native anchor links.
        await expect(page.locator('html')).toHaveAttribute('lang', 'en');
        const sections = page.getByRole('navigation', {name: 'Example account sections'});
        await expect(sections.locator('a')).toHaveText(['Accounts', 'Invoices', 'Loyalty', 'Exchange rates']);
        for (const link of await sections.locator('a').all()) {
            const bounds = await link.boundingBox();
            expect(bounds.width).toBeGreaterThanOrEqual(44);
            expect(bounds.height).toBeGreaterThanOrEqual(44);
        }

        await sections.getByRole('link',{name:'Accounts',exact:true}).press('Enter');
        const account = page.locator('#lab-bank-institution');
        const accountArt = account.locator('.institution-miniature');
        await expect(accountArt).toHaveAttribute('aria-hidden','true');
        const accountBounds = await accountArt.boundingBox();
        expect(accountBounds.width).toBe(54);
        expect(accountBounds.height).toBe(36);
        await page.screenshot({path:info.outputPath(`account-icon-catalogue-${theme}-${width}.png`)});

        for (const [label, target] of [['Invoices', 'lab-banking-invoices'], ['Loyalty', 'lab-banking-loyalty'], ['Exchange rates', 'lab-banking-rates']]) {
            await sections.getByRole('link', {name: label, exact: true}).focus();
            await page.keyboard.press('Enter');
            await expect(page).toHaveURL(new RegExp(`#${target}$`));
            await expect.poll(() => page.evaluate(id => document.getElementById(id).getBoundingClientRect().top
                - document.querySelector('[data-catalogue-header]').getBoundingClientRect().bottom, target)).toBeGreaterThanOrEqual(0);
            const bounds = await page.locator(`#${target}`).boundingBox();
            expect(bounds.x).toBeGreaterThanOrEqual(0);
            expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
            if (label === 'Invoices') {
                const history = page.locator(`#${target} .invoice-history`);
                await expect(history).toContainText('BRL 940.00');
                await expect(history).toContainText('Due November 10');
                if (width < 1024) await expect(history.locator('.invoice-history-head')).toBeHidden();
                else await expect(history.locator('.invoice-history-head')).toBeVisible();
                const miniature = await page.locator(`#${target} .card-miniature`).boundingBox();
                expect(miniature.width).toBe(64);
                expect(miniature.height).toBe(40);
                await page.screenshot({path: info.outputPath(`invoice-catalogue-${theme}-${width}.png`)});
            }
            if (label === 'Loyalty') {
                const disclosure = page.locator(`#${target} details`);
                const summary = disclosure.locator(':scope > summary');
                await expect(disclosure).not.toHaveAttribute('open', '');
                await summary.focus();
                await page.keyboard.press('Space');
                await expect(disclosure).toHaveAttribute('open', '');
                await expect(disclosure).toContainText('+240.00 points');
                await expect(summary).toBeFocused();
                await expect(page.locator(`#${target}`)).toContainText('2,400.00');
                await page.screenshot({path: info.outputPath(`loyalty-catalogue-${theme}-${width}.png`)});
                await page.keyboard.press('Enter');
                await expect(disclosure).not.toHaveAttribute('open', '');
            }
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
}
