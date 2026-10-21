// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {openCatalogue} = require('../helpers/catalogue');

async function post(page, path, fields) {
    const form = await page.request.get(path);
    const csrf = (await form.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {
        form: {csrfmiddlewaretoken: csrf, ...fields},
        headers: {Referer: form.url()}, maxRedirects: 0,
    });
    expect(saved.status(), await saved.text()).toBe(302);
}

async function seed(page, info) {
    const username = `workspace-density-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {
        username, email: `${username}@example.test`,
        password1: 'Density-E2E-2026!', password2: 'Density-E2E-2026!',
    });
    await post(page, '/banking/create/', {name: 'Everyday institution', color: '#24594A'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {
        bank, name: 'Available cash with a complete account name', currency: 'BRL',
        opening_date: '2020-01-01', opening_balance: '1000.25',
        reserved_amount: '100', planning_enabled: 'on',
    });
    await post(page, '/investments/products/create/', {
        bank, name: 'Monthly cash pot', purpose: 'MONTHLY_CASH',
    });
    await page.goto('/investments/assets/create/');
    const product = await page.locator('#id_opening_product option')
        .filter({hasText: 'Monthly cash pot'}).getAttribute('value');
    await post(page, '/investments/assets/create/', {
        name: 'Synthetic dated cash', code: 'DENSITY_CASH', asset_class: 'LIQUIDITY',
        currency: 'BRL', valuation_mode: 'MONETARY', opening_balance: '300.25',
        opening_quantity: '0', opening_unit_price: '0', opening_product: product,
        opening_date: '2020-01-01',
    });
}

async function expectFits(page) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        'Headings, controls and complete financial values fit the viewport').toBe(true);
}

async function expectCompactOverview(page) {
    const main = page.locator('main.workspace-density');
    await expect(main).toBeVisible();
    const heading = main.locator('h1.page-title');
    await expect(heading).toHaveCount(1);
    await expect(heading).toHaveCSS('font-size', '24px');
    await expect(heading).toHaveCSS('line-height', '30px');
    for (const summary of await main.locator('.workspace-summary').all()) {
        await expect(summary).toHaveCSS('padding-top', '16px');
        await expect(summary).toHaveCSS('padding-right', '16px');
        await expect(summary).toHaveCSS('padding-bottom', '16px');
        await expect(summary).toHaveCSS('padding-left', '16px');
        for (const value of await summary.locator('.workspace-summary-value').all()) {
            await expect(value).toHaveCSS('font-size', '24px');
            await expect(value).toHaveCSS('line-height', '30px');
            await expect(value.locator('.workspace-summary-currency')).toHaveCSS('font-size', '14px');
        }
        for (const label of await summary.locator('.workspace-summary-label').all()) {
            await expect(label).toHaveCSS('font-size', '14px');
        }
        for (const caption of await summary.locator('.workspace-summary-caption').all()) {
            await expect(caption).toHaveCSS('font-size', '12px');
        }
    }
    const header = main.locator('.workspace-header').first();
    for (const action of await header.locator(
        'a.action-primary:visible, a.action-link:visible, a.quiet-action:visible, [data-export-menu] > summary:visible',
    ).all()) {
        const bounds = await action.boundingBox();
        expect(bounds.height).toBeGreaterThanOrEqual(44);
        expect(bounds.width).toBeGreaterThanOrEqual(44);
    }
    await expectFits(page);
}

async function expectDisclosureGrowth(summary, container) {
    await expect(summary).toBeVisible();
    const closed = await container.boundingBox();
    await summary.press('Space');
    await expect(summary.locator('..')).toHaveAttribute('open', '');
    await expect(summary).toBeFocused();
    expect((await container.boundingBox()).height).toBeGreaterThan(closed.height);
    await summary.press('Space');
    await expect(summary.locator('..')).not.toHaveAttribute('open', '');
}

const destinations = [
    ['home', '/dashboard/'], ['transactions', '/transactions/'], ['accounts', '/banking/'],
    ['investments', '/investments/'], ['planning', '/planning/', 'plan'], ['analytics', '/analytics/'],
];

for (const language of ['en', 'pt-br']) for (const theme of ['light', 'dark']) {
    test(`compact workspace headers preserve summaries and actions (${language}, ${theme})`, async ({page}, info) => {
        test.setTimeout(60000);
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await seed(page, info);
        await page.context().addCookies([{name: 'django_language', value: language, url: info.project.use.baseURL}]);
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        for (const width of [1440, 320]) {
            await page.setViewportSize({width, height: 900});
            await page.goto('/dashboard/');
            let homeAmount;
            for (const [area, path, navItem = area] of destinations) {
                if (area !== 'home') {
                    const navigation = page.locator(`[data-app-navigation="${width >= 1024 ? 'desktop' : 'mobile'}"]`);
                    const link = navigation.locator(`[data-nav-item="${navItem}"]`);
                    await link.press('Enter');
                    await expect(page).toHaveURL(url => url.pathname === path);
                }
                await page.evaluate(() => document.fonts.ready);
                await expectCompactOverview(page);
                if (area === 'home' || area === 'accounts') {
                    const amount = page.locator('#planning-availability .workspace-summary-value');
                    await expect(amount).toContainText(/1[.,\s]200[,.]50/);
                    if (area === 'home') homeAmount = await amount.innerText();
                    else expect(await amount.innerText()).toBe(homeAmount);
                }
                if (area === 'investments') {
                    await expect(page.locator('#investment-total')).toContainText(/BRL 300[,.]25/);
                    await expectDisclosureGrowth(page.locator('#position-value-details > summary'),
                        page.locator('#position-value-summary'));
                }
                if (area === 'planning') {
                    await expect(page.locator('[data-monthly-available]')).toContainText(/BRL 1[.,\s]200[,.]50/);
                    await expect(page.locator('.monthly-outlook-metrics')).toContainText(/BRL 100[,.]00/);
                    await expectDisclosureGrowth(page.locator('#monthly-calculation > summary'),
                        page.locator('.monthly-planning-summary'));
                }
                await page.evaluate(() => window.scrollTo(0, 0));
                await page.screenshot({path: info.outputPath(`compact-${area}-${language}-${theme}-${width}.png`)});
            }
            // Analytics keeps two real destinations rather than a second summary
            // implementation. Its multi-value result panel has no primary total.
            const investmentTab = page.locator('main .section-nav').getByRole('link', {
                name: language === 'pt-br' ? 'Investimentos' : 'Investments', exact: true,
            });
            await investmentTab.press('Enter');
            await expect(page).toHaveURL(url => url.pathname === '/analytics/investments/');
            await expectCompactOverview(page);
            await expect(page.locator('#investment-performance')).toContainText(/BRL 300[,.]25/);
            await expect(page.locator('#departure-confirm')).toBeHidden();
            await page.screenshot({path: info.outputPath(`compact-analytics-investments-${language}-${theme}-${width}.png`)});
            await page.goBack();
            await expect(page).toHaveURL(url => url.pathname === '/analytics/');
            await expectCompactOverview(page);
        }
        expect(errors).toEqual([]);
    });
}

test('compact summaries keep complete native phone navigation and disclosures', async ({browser}, info) => {
    test.setTimeout(60000);
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 320, height: 900}});
    try {
        const page = await context.newPage();
        await seed(page, info);
        await page.context().addCookies([{name: 'django_language', value: 'en', url: info.project.use.baseURL}]);
        await page.goto('/dashboard/');
        for (const [area, path, navItem = area] of destinations) {
            if (area !== 'home') {
                await page.locator(`[data-app-navigation="mobile"] [data-nav-item="${navItem}"]`).press('Enter');
                await expect(page).toHaveURL(url => url.pathname === path);
            }
            await expectCompactOverview(page);
            if (area === 'investments') {
                await expect(page.locator('#investment-total')).toContainText(/BRL 300[,.]25/);
                await expectDisclosureGrowth(page.locator('#position-value-details > summary'),
                    page.locator('#position-value-summary'));
            }
            if (area === 'planning') {
                await expect(page.locator('[data-monthly-available]')).toContainText(/BRL 1[.,\s]200[,.]50/);
                await expectDisclosureGrowth(page.locator('#monthly-calculation > summary'),
                    page.locator('.monthly-planning-summary'));
            }
        }
        await page.locator('main .section-nav').getByRole('link', {name: 'Investments', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname === '/analytics/investments/');
        await expectCompactOverview(page);
    } finally {
        await context.close();
    }
});

for (const theme of ['light', 'dark']) for (const width of [1440, 320]) {
    test(`compact workspace catalogue keeps native summary expansion (${theme}, ${width})`, async ({page}, info) => {
        await page.setViewportSize({width, height: 900});
        await openCatalogue(page, {hash: '#lab-workspace-density', theme, waitForFonts: true});
        const specimen = page.locator('#lab-workspace-density');
        await expect(specimen).toBeVisible();
        await expect(specimen.locator('.page-title')).toHaveCSS('font-size', '24px');
        await expect(specimen.locator('.page-title')).toHaveCSS('line-height', '30px');
        const summary = specimen.locator('.workspace-summary').first();
        await expect(summary).toHaveCSS('padding-top', '16px');
        await expect(summary.locator('.workspace-summary-value')).toHaveCSS('font-size', '24px');
        await expectDisclosureGrowth(summary.locator('details > summary'), summary);
        await expectFits(page);
        await page.screenshot({path: info.outputPath(`compact-catalogue-${theme}-${width}.png`)});
    });
}
