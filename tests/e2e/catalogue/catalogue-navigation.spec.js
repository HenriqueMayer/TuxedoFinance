// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const {openCatalogue} = require('../helpers/catalogue');

async function navigationGeometry(link) {
    return link.evaluate(async node => {
        getComputedStyle(node).color;
        await Promise.all(node.getAnimations({subtree: true}).map(animation => animation.finished.catch(() => {})));
        const bounds = node.getBoundingClientRect();
        const relative = element => {
            const box = element.getBoundingClientRect();
            return [box.left - bounds.left, box.top - bounds.top, box.width, box.height];
        };
        return {target: [node.offsetLeft, node.offsetTop, node.offsetWidth, node.offsetHeight],
            text: relative(node.querySelector('span')), icon: relative(node.querySelector('svg'))};
    });
}

function expectSubtleNavigation(actual, original) {
    expect(actual.target, 'Navigation keeps its hit area').toEqual(original.target);
    actual.text.forEach((value, index) => expect(value, 'Navigation text does not reflow').toBeCloseTo(original.text[index], 1));
    actual.icon.forEach((value, index) => expect(Math.abs(value - original.icon[index]),
        'Navigation icon feedback stays within 2px').toBeLessThanOrEqual(index < 2 ? 2 : .1));
}

for (const theme of ['light', 'dark']) {
    test(`catalogue has one responsive workspace shell and deliberate account options (${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({width: 1440, height: 900});
        await openCatalogue(page, {hash: '#navigation'});
        const sample = page.locator('#lab-workspace-example');
        await expect(sample.locator('.lab-rail-brand')).toHaveAttribute('href', '#public-homepage');
        const navigation = sample.getByRole('navigation', {name: 'Workspace navigation', exact: true});
        const names = ['Home', 'Transactions', 'Accounts', 'Investments', 'Plan', 'Analytics'];
        await expect(navigation.getByRole('link')).toHaveCount(6);
        await expect(page.locator('[data-lab-navigation]')).toHaveCount(1);
        await expect(page.locator('section#shell, section#dashboard')).toHaveCount(0);
        await expect(page.locator('#navigation > #shell, #navigation > #dashboard')).toHaveCount(2);
        await expect(sample.locator('[data-nav-menu]')).toHaveCount(0);
        await expect(sample.getByRole('link', {name: /Net worth|Imports/})).toHaveCount(0);
        await navigation.getByRole('link', {name: 'Home', exact: true}).focus();
        await page.keyboard.press('Tab');
        await expect(navigation.getByRole('link', {name: 'Transactions', exact: true})).toBeFocused();
        const options = sample.locator('details.secondary-actions');
        const summary = options.locator('summary');
        await summary.hover();
        await expect(options).not.toHaveAttribute('open');
        await summary.focus();
        await expect(options).not.toHaveAttribute('open');
        await summary.press('Space');
        await expect(options).toHaveAttribute('open', '');
        await page.keyboard.press('Escape');
        await expect(options).not.toHaveAttribute('open');
        await expect(summary).toBeFocused();
        for (const width of [1440, 390, 320]) {
            await page.setViewportSize({width, height: 900});
            await expect(navigation).toBeVisible();
            await expect(navigation.getByRole('link')).toHaveCount(6);
            for (const [index, name] of names.entries()) {
                const link = navigation.getByRole('link', {name, exact: true});
                const compact = {Transactions: 'Entries', Investments: 'Invest'};
                await expect(link.locator('span:visible')).toHaveText([width <= 760 ? (compact[name] || name) : name]);
                await expect(link).toHaveAttribute('href', '#lab-view-' + ['home', 'transactions', 'accounts', 'investments', 'plan', 'analytics'][index]);
                const target = await link.boundingBox();
                expect(target.width).toBeGreaterThanOrEqual(44);
                expect(target.height).toBeGreaterThanOrEqual(44);
                await page.mouse.move(0, 0);
                await link.scrollIntoViewIfNeeded();
                const original = await navigationGeometry(link);
                await link.hover();
                expectSubtleNavigation(await navigationGeometry(link), original);
                await page.mouse.move(0, 0);
                await link.focus();
                await link.press('Tab');
                await page.keyboard.press('Shift+Tab');
                await expect(link).toBeFocused();
                expectSubtleNavigation(await navigationGeometry(link), original);
            }
            await sample.scrollIntoViewIfNeeded();
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            // The sticky documentation header must paint above the contained
            // workspace preview, including its current-item decoration.
            await navigation.evaluate(node => window.scrollTo({
                top: scrollY + node.getBoundingClientRect().top + 16, behavior: 'instant',
            }));
            const stacking = await navigation.evaluate(node => {
                const header = document.querySelector('[data-catalogue-header]');
                const heading = header.getBoundingClientRect();
                const preview = node.getBoundingClientRect();
                const left = Math.max(heading.left, preview.left);
                const right = Math.min(heading.right, preview.right);
                const top = Math.max(heading.top, preview.top);
                const bottom = Math.min(heading.bottom, preview.bottom);
                const hit = document.elementFromPoint(left + Math.min(20, (right - left) / 2), (top + bottom) / 2);
                return {width: right - left, height: bottom - top, headerOwnsPoint: header.contains(hit)};
            });
            expect(stacking.width).toBeGreaterThan(0);
            expect(stacking.height).toBeGreaterThan(0);
            expect(stacking.headerOwnsPoint, JSON.stringify(stacking)).toBe(true);
            await page.screenshot({path: info.outputPath(`catalogue-navigation-${width}-${theme}.png`)});
        }
        await expect(page.locator('[data-catalogue-header]').getByRole('link', {name: 'Workspace', exact: true}))
            .toHaveAttribute('href', '#navigation');
        await expect(page.locator('[data-catalogue-header]').getByRole('link', {name: 'Patterns', exact: true}))
            .toHaveAttribute('href', '#workspaces');
        for (const hash of ['shell', 'dashboard']) {
            await page.locator('[data-lab-destination="plan"]').press('Enter');
            await expect(page.locator('[data-lab-view="plan"]')).toBeVisible();
            await page.goto('/catalogue/docs/design-system.html#' + hash);
            await expect(page.locator('#lab-nav-title')).toBeInViewport();
            await expect(page.locator('[data-lab-navigation]')).toHaveCount(1);
            await expect(page.locator('[data-lab-view="home"]')).toBeVisible();
            await expect(page.locator('[data-lab-destination="home"]')).toHaveAttribute('aria-current', 'page');
        }
    });
}

test('catalogue Accounts identifies banks and keeps cash disclosures separate from invoice debt in both themes', async ({browser}, info) => {
    for (const theme of ['light', 'dark']) {
        const context = await browser.newContext({viewport: {width: 390, height: 900}});
        try {
            const page = await context.newPage();
            await page.addInitScript(value => localStorage.setItem('theme', value), theme);
            await openCatalogue(page, {hash: '#navigation'});
            await page.locator('[data-lab-destination="accounts"]').press('Enter');
            const view = page.locator('#lab-view-accounts');
            await expect(view).toBeVisible();
            const banks = view.locator('details.bank-overview-card');
            await expect(banks).toHaveCount(2);
            const colors = [];
            for (const bank of await banks.all()) {
                const marker = bank.locator('.bank-marker');
                await expect(marker).toBeVisible();
                colors.push(await marker.evaluate(node => getComputedStyle(node).backgroundColor));
            }
            expect(new Set(colors).size, 'Each bank retains its own visible identifying color').toBe(2);
            const invoice = view.locator('.lab-bank-invoice');
            await expect(invoice.locator('.bank-bookmark')).toBeVisible();
            await expect(view.getByText('Card debt', {exact: true})).toBeVisible();
            await expect(invoice).toContainText('Unpaid');
            expect(await invoice.evaluate(node => !node.closest('details.bank-overview-card'))).toBe(true);
            for (const width of [390, 320]) {
                await page.setViewportSize({width, height: 900});
                for (const bank of await banks.all()) {
                    const summary = bank.locator(':scope > summary');
                    await summary.hover();
                    await expect(bank).not.toHaveAttribute('open');
                    await summary.focus();
                    await summary.press('Space');
                    await expect(bank).toHaveAttribute('open', '');
                    await expect(summary).toBeFocused();
                    expect(await summary.evaluate(node => node.matches(':focus-visible'))).toBe(true);
                    const money = await bank.evaluate(node => {
                        const cents = text => Math.round(Number(text.replace(/[^\d.-]/g, '')) * 100);
                        return {cash: cents(node.querySelector('summary .lab-bank-balance strong').textContent),
                            accounts: [...node.querySelectorAll('.lab-bank-accounts p > strong')]
                                .reduce((sum, amount) => sum + cents(amount.textContent), 0)};
                    });
                    expect(money.cash, 'Displayed bank cash reconciles only with the listed accounts').toBe(money.accounts);
                    await expect(summary).toContainText('Bank cash · BRL');
                    await expect(bank.getByText('Card debt', {exact: true})).toHaveCount(0);
                    const bounds = await bank.boundingBox();
                    expect(bounds.x).toBeGreaterThanOrEqual(0);
                    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
                    await summary.press('Enter');
                    await expect(bank).not.toHaveAttribute('open');
                }
                expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
                await view.screenshot({path: info.outputPath(`accounts-cash-debt-${width}-${theme}.png`)});
            }
        } finally { await context.close(); }
    }
});
