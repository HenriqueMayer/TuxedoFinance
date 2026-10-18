// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function paintedPoint(art, name = 'left') {
    return art.evaluate((owner, layer) => {
        const node = owner.querySelector(`[data-bowtie-layer="${layer}"]`);
        const point = new DOMPoint(layer === 'left' ? 142 : 438, 220).matrixTransform(node.getScreenCTM());
        return {x: point.x, y: point.y};
    }, name);
}

for (const theme of ['light', 'dark']) {
    test(`public paper map preserves local hover, keyboard and HTMX cleanup (${theme})`, async ({page}, info) => {
        await page.setViewportSize({width: 1440, height: 1000});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.goto('/');
        const art = page.locator('[data-paper-bowtie]');
        const control = art.getByRole('button', {name: 'Explore workspaces', exact: true});
        const map = art.locator('[data-bowtie-map]');
        await expect(art).toHaveAttribute('data-paper-enhanced', 'true');
        await expect(art.locator('[data-bowtie-layer]')).toHaveCount(5);
        await expect(art.locator('[data-bowtie-fragment]')).toHaveCount(0);
        await expect(map).toBeHidden();
        await expect(control).toHaveAttribute('aria-expanded', 'false');
        // Hovering the actual painted paper opens its index; empty scene
        // margins and unrelated page content are not activation targets.
        const point = await paintedPoint(art);
        await page.mouse.move(point.x, point.y);
        await expect(map).toBeVisible();
        await expect(control).toHaveAttribute('aria-pressed', 'false');
        await page.mouse.move(8, 8);
        await expect(map).toBeHidden();
        await control.focus();
        await control.press('Space');
        await expect(control).toHaveAttribute('aria-pressed', 'true');
        await expect(map).toBeVisible();
        await control.press('Tab');
        await expect(map.getByRole('link', {name: 'Home', exact: true})).toBeFocused();
        await page.keyboard.press('Tab');
        await expect(map.getByRole('link', {name: 'Transactions', exact: true})).toBeFocused();
        await expect(art).toHaveAttribute('data-bowtie-highlight', 'ledger');
        await page.screenshot({path: info.outputPath(`public-home-${theme}.png`), fullPage: true});
        await page.keyboard.press('Escape');
        await expect(control).toBeFocused();
        await expect(map).toBeHidden();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        // Keep a reference only in this disposable test so the detached
        // document proves that HTMX cleanup released its private observers.
        await page.evaluate(() => { window.__previousPaperOwner = document.querySelector('[data-paper-bowtie]'); });
        await page.locator('.public-navbar').getByRole('link', {name: 'Log in', exact: true}).click();
        await expect(page).toHaveURL(/\/accounts\/login\/$/);
        expect(await page.evaluate(() => ({connected: window.__previousPaperOwner.isConnected,
            enhanced: window.__previousPaperOwner.dataset.paperEnhanced,
            layers: window.__previousPaperOwner.querySelectorAll('[data-bowtie-layers]').length})))
            .toEqual({connected: false, enhanced: undefined, layers: 0});
        await page.locator('.public-navbar').getByRole('link', {name: 'Tuxedo Finance', exact: true}).click();
        await expect(page.locator('[data-paper-bowtie]')).toHaveAttribute('data-paper-enhanced', 'true');
        await expect(page.locator('[data-bowtie-layer]')).toHaveCount(5);
        expect(errors).toEqual([]);
    });

    test(`public paper map supports touch and reduced motion at 390px (${theme})`, async ({browser}, info) => {
        const context = await browser.newContext({baseURL: info.project.use.baseURL,
            viewport: {width: 390, height: 844}, hasTouch: true, isMobile: true, reducedMotion: 'reduce'});
        try {
            const page = await context.newPage();
            await page.addInitScript(value => localStorage.setItem('theme', value), theme);
            await page.goto('/');
            const art = page.locator('[data-paper-bowtie]');
            const control = art.getByRole('button', {name: 'Explore workspaces', exact: true});
            const map = art.locator('[data-bowtie-map]');
            await expect(art).toHaveAttribute('data-bowtie-motion', 'reduced');
            await control.scrollIntoViewIfNeeded();
            const point = await paintedPoint(art);
            await page.touchscreen.tap(point.x, point.y);
            await expect(map).toBeVisible();
            await expect(control).toHaveAttribute('aria-pressed', 'true');
            const links = map.locator('[data-bowtie-map-link]');
            await expect(links).toHaveCount(5);
            for (const link of await links.all()) {
                const box = await link.boundingBox();
                expect(box.height).toBeGreaterThanOrEqual(44);
                expect(box.x).toBeGreaterThanOrEqual(0);
                expect(box.x + box.width).toBeLessThanOrEqual(390);
            }
            await art.scrollIntoViewIfNeeded();
            await expect(control).toHaveAttribute('aria-pressed', 'true');
            // Full-page mobile capture temporarily resizes Chromium's viewport,
            // which deliberately resets this illustration's responsive pose.
            await page.screenshot({path: info.outputPath(`public-home-touch-${theme}.png`)});
            await control.scrollIntoViewIfNeeded();
            const close = await paintedPoint(art);
            await page.touchscreen.tap(close.x, close.y);
            await expect(map).toBeHidden();
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        } finally { await context.close(); }
    });

    test(`public paper links and authentication stay native without JavaScript (${theme})`, async ({browser}, info) => {
        const context = await browser.newContext({baseURL: info.project.use.baseURL,
            viewport: {width: theme === 'light' ? 320 : 390, height: 844}, javaScriptEnabled: false, colorScheme: theme});
        try {
            const page = await context.newPage();
            await page.goto('/');
            const art = page.locator('[data-paper-bowtie]');
            await expect(art.getByRole('img', {name: 'A ledger-paper bow tie that reveals the workspace map.'})).toBeVisible();
            await expect(art.locator('[data-bowtie-map]')).toBeVisible();
            await expect(art.locator('[data-bowtie-map-link]')).toHaveCount(5);
            await expect(art.locator('[data-bowtie-layers]')).toHaveCount(0);
            const accounts = art.getByRole('link', {name: 'Accounts', exact: true});
            await accounts.focus();
            await accounts.press('Enter');
            await expect(page).toHaveURL(/#feature-accounts$/);
            await expect(page.locator('#feature-accounts')).toBeInViewport();
            await expect(page.locator('main dl > div')).toHaveCount(7);
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            await page.locator('main').getByRole('link', {name: 'Log in', exact: true}).click();
            await expect(page).toHaveURL(/\/accounts\/login\/$/);
            await expect(page.getByRole('textbox', {name: /^Username/})).toBeVisible();
        } finally { await context.close(); }
    });
}
