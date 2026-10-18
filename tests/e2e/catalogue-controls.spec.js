// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { resolve } = require('node:path');

async function openCatalogue(page, theme) {
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    const root = resolve(__dirname, '../..');
    await page.route('**/catalogue/**', async route => {
        const name = new URL(route.request().url()).pathname.slice('/catalogue/'.length);
        const documents = ['docs/design-system.html', 'docs/design-system.css',
            'docs/design-system.js', 'docs/design-system-layers.js', 'docs/design-system-calendar.js'];
        if ((!documents.includes(name) && !name.startsWith('static/')) || name.split('/').includes('..')) return route.abort();
        const types = {html: 'text/html', css: 'text/css', js: 'application/javascript',
            woff2: 'font/woff2', png: 'image/png', jpg: 'image/jpeg', ico: 'image/x-icon'};
        await route.fulfill({path: resolve(root, name), contentType: types[name.split('.').pop()]});
    });
    await page.goto('/catalogue/docs/design-system.html#workspaces');
    await page.evaluate(() => document.fonts.ready);
}

test('catalogue compact monthly, login and daily controls adapt to fine and coarse pointers in both themes', async ({browser}, info) => {
    for (const theme of ['light', 'dark']) {
        for (const coarse of [false, true]) {
            const context = await browser.newContext({viewport: {width: coarse ? 390 : 1440, height: 900},
                hasTouch: coarse, isMobile: coarse});
            try {
                const page = await context.newPage();
                await openCatalogue(page, theme);
                expect(await page.evaluate(() => matchMedia('(pointer: coarse)').matches)).toBe(coarse);
                const monthly = page.getByRole('region', {name: 'Example monthly overrides', exact: true});
                const inputs = monthly.getByRole('textbox');
                await expect(inputs).toHaveCount(4);
                const controls = [
                    ...await inputs.all(),
                    page.locator('#lab-login').getByLabel('Username', {exact: true}),
                    page.locator('#lab-login').getByLabel('Password', {exact: true}),
                    page.locator('#daily-flow').getByRole('searchbox', {name: 'Search', exact: true}),
                ];
                for (const control of controls) {
                    await expect(control).toHaveAccessibleName(/\S/);
                    const box = await control.boundingBox();
                    expect(box.height, theme + ' ' + (coarse ? 'coarse' : 'fine') + ' control height')
                        .toBeCloseTo(coarse ? 44 : 40, 1);
                }
                for (const control of await inputs.all()) {
                    expect((await control.boundingBox()).width, 'Monthly overrides stay at most 160px wide').toBeLessThanOrEqual(160);
                }
                const contribution = monthly.getByRole('textbox', {name: 'Month 1 contribution in BRL', exact: true});
                await contribution.fill('750.25');
                await contribution.press('Tab');
                await page.keyboard.press('Shift+Tab');
                await expect(contribution).toBeFocused();
                await expect(contribution).toHaveValue('750.25');
                expect(await contribution.evaluate(node => {
                    const style = getComputedStyle(node);
                    return node.matches(':focus-visible') && parseFloat(style.outlineWidth) > 0 && style.outlineStyle !== 'none';
                })).toBe(true);
                await expect(page.locator('#lab-login-user')).toHaveAttribute('readonly', '');
                await expect(page.locator('#lab-login-password')).toHaveAttribute('readonly', '');
                expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
                await page.locator('#planning-sheet-example').screenshot({path: info.outputPath(`monthly-${coarse ? 'coarse' : 'fine'}-${theme}.png`)});
            } finally { await context.close(); }
        }
    }
});

test('catalogue print keeps every column of Semantic, Outlook and Monthly tables on the printable page', async ({browser}, info) => {
    for (const theme of ['light', 'dark']) {
        // A4 minus two 12mm margins gives a 703 CSS-pixel reading area.
        // Exercise the print cascade at that width before retaining the PDF.
        const context = await browser.newContext({viewport: {width: 703, height: 1000}});
        try {
            const page = await context.newPage();
            await openCatalogue(page, theme);
            await page.emulateMedia({media: 'print', reducedMotion: 'reduce'});
            const regions = [
                page.locator('#lab-semantic-scroll'), page.locator('#lab-outlook-scroll'),
                page.getByRole('region', {name: 'Example monthly overrides', exact: true}),
            ];
            for (const region of regions) {
                const table = region.getByRole('table');
                await expect(table).toBeVisible();
                const layout = await table.evaluate(node => {
                    const bounds = node.getBoundingClientRect();
                    const region = node.parentElement;
                    const owner = region.getBoundingClientRect();
                    const rows = [...node.rows];
                    const lastColumn = rows.map(row => {
                        const cell = row.cells[row.cells.length - 1];
                        const box = cell.getBoundingClientRect();
                        const range = document.createRange();
                        range.selectNodeContents(cell);
                        const contents = range.getBoundingClientRect();
                        const input = cell.querySelector('input')?.getBoundingClientRect();
                        return {cellLeft: box.left, cellRight: box.right,
                            contentLeft: input?.left ?? contents.left, contentRight: input?.right ?? contents.right};
                    });
                    return {left: bounds.left, right: bounds.right, regionLeft: owner.left, regionRight: owner.right,
                        overflow: region.scrollWidth - region.clientWidth, viewport: innerWidth, lastColumn};
                });
                expect(layout.overflow, 'Print removes horizontal table clipping').toBeLessThanOrEqual(1);
                expect(layout.left).toBeGreaterThanOrEqual(layout.regionLeft - 1);
                expect(layout.right).toBeLessThanOrEqual(layout.regionRight + 1);
                expect(layout.left).toBeGreaterThanOrEqual(0);
                expect(layout.right).toBeLessThanOrEqual(layout.viewport);
                expect(layout.lastColumn.length).toBeGreaterThan(1);
                for (const cell of layout.lastColumn) {
                    expect(cell.cellRight).toBeLessThanOrEqual(layout.regionRight + 1);
                    expect(cell.contentLeft).toBeGreaterThanOrEqual(cell.cellLeft - 1);
                    expect(cell.contentRight, 'The last column content remains inside its printed cell').toBeLessThanOrEqual(cell.cellRight + 1);
                }
            }
            await page.pdf({path: info.outputPath(`catalogue-print-${theme}.pdf`), format: 'A4',
                margin: {top: '12mm', bottom: '12mm', left: '12mm', right: '12mm'}, printBackground: true});
        } finally { await context.close(); }
    }
});
