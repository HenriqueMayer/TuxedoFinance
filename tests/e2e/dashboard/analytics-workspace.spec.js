// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function signup(page, info) {
    const username = `analytics-${info.workerIndex}-${Date.now()}`;
    const form = await page.request.get('/accounts/signup/');
    const token = (await form.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post('/accounts/signup/', {
        form: {csrfmiddlewaretoken: token, username, email: `${username}@example.test`,
            password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'},
        headers: {Referer: form.url()}, maxRedirects: 0,
    });
    expect(saved.status()).toBe(302);
}

for (const theme of ['light', 'dark']) for (const [width, language] of [[1440, 'en'], [320, 'en'], [390, 'pt-br']]) {
    test(`Analytics navigation, tabs and month shortcut (${theme}, ${width}, ${language})`, async ({page}, info) => {
        await signup(page, info);
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.context().addCookies([{name: 'django_language', value: language, url: info.project.use.baseURL}]);
        await page.setViewportSize({width, height: width < 640 ? 740 : 900});
        const month = new Date();
        month.setUTCDate(1);
        month.setUTCMonth(month.getUTCMonth() - 1);
        const selected = month.toISOString().slice(0, 7);
        await page.goto(`/dashboard/?month=${selected}`);
        await expect(page.locator('#category-heading, #outlook-heading')).toHaveCount(0);
        const shortcut = page.locator('main').getByRole('link', {name: language === 'pt-br' ? 'Análises' : 'Analytics', exact: true});
        await shortcut.press('Enter');
        await expect(page).toHaveURL(url => url.pathname === '/analytics/' && url.searchParams.get('month') === selected);
        await expect(page.locator('#category-heading, #outlook-heading')).toHaveCount(2);
        const navigation = page.locator(`[data-app-navigation="${width >= 1024 ? 'desktop' : 'mobile'}"]`);
        await expect(navigation.getByRole('link')).toHaveCount(6);
        await expect(navigation.locator('[data-nav-item="analytics"]')).toHaveAttribute('aria-current', 'page');
        if (width < 1024) {
            for (const link of await navigation.getByRole('link').all()) {
                const box = await link.boundingBox();
                expect(box.width).toBeGreaterThanOrEqual(44);
                expect(box.height).toBeGreaterThanOrEqual(44);
                expect(parseFloat(await link.evaluate(element => getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(10);
                const label = link.locator('.app-navigation-label');
                expect(await label.evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
            }
        }
        const sections = page.locator('main .section-nav');
        await expect(sections.getByRole('link')).toHaveCount(2);
        const investments = sections.getByRole('link', {name: language === 'pt-br' ? 'Investimentos' : 'Investments', exact: true});
        await investments.press('Enter');
        await expect(page).toHaveURL(url => url.pathname === '/analytics/investments/');
        await expect(investments).toHaveAttribute('aria-current', 'page');
        await expect(navigation.locator('[data-nav-item="analytics"]')).toHaveAttribute('aria-current', 'page');
        await expect(page.locator('#investment-evolution')).toBeVisible();
        await expect(page.locator('#departure-confirm')).toBeHidden();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({path: info.outputPath(`analytics-investments-${theme}-${width}.png`), fullPage: true});
        await page.goBack();
        await expect(page).toHaveURL(url => url.pathname === '/analytics/' && url.searchParams.get('month') === selected);
        await expect(page.locator('#category-heading')).toBeVisible();
    });
}

test('legacy analytical URLs retain query and chart anchors in native and stale HTMX navigation', async ({page}, info) => {
    await signup(page, info);
    await page.goto('/dashboard/reports/?charts_offset=-1&instrument_month=ALL#monthly-cashflow');
    await expect(page).toHaveURL(url => url.pathname === '/analytics/' && url.searchParams.get('charts_offset') === '-1'
        && url.searchParams.get('instrument_month') === 'ALL' && url.hash === '#monthly-cashflow');
    await page.goto('/investments/charts/?scope=cash&total_offset=-1&flow_offset=-2#investment-cashflow');
    await expect(page).toHaveURL(url => url.pathname === '/analytics/investments/' && url.searchParams.get('scope') === 'cash'
        && url.searchParams.get('flow_offset') === '-2' && url.hash === '#investment-cashflow');
    const legacy = '/investments/charts/?scope=cash&total_offset=-2&flow_offset=-1';
    const redirected = page.waitForResponse(response => new URL(response.url()).pathname === '/investments/charts/'
        && new URL(response.url()).searchParams.get('total_offset') === '-2');
    await page.evaluate(path => {
        // Model a tab opened before the route moved: its document is stale,
        // but the ordinary chart-island refresh must reach the canonical
        // workspace. Its source owns hx-request=noHeaders:false; using body
        // instead would deliberately suppress the identifying HTMX headers.
        history.replaceState({}, '', path + '#investment-cashflow');
        window.htmx.ajax('GET', path, {source: '#investments-charts', target: '#investments-charts', swap: 'outerHTML'});
    }, legacy);
    const response = await redirected;
    expect(response.request().headers()['hx-request']).toBe('true');
    expect(response.headers()['hx-redirect']).toBe('/analytics/investments/?scope=cash&total_offset=-2&flow_offset=-1#investment-cashflow');
    await expect(page).toHaveURL(url => url.pathname === '/analytics/investments/' && url.searchParams.get('total_offset') === '-2'
        && url.searchParams.get('flow_offset') === '-1' && url.hash === '#investment-cashflow');
    await expect(page.locator('main h1')).toHaveCount(1);
    await expect(page.locator('.app-sidebar')).toHaveCount(1);
    await expect(page.locator('#investments-charts')).toHaveCount(1);
});

test('Analytics native navigation and monthly filters work without JavaScript', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 320, height: 740}});
    try {
        const page = await context.newPage();
        await signup(page, info);
        await page.goto('/dashboard/?month=2026-08');
        await page.locator('main').getByRole('link', {name: 'Analytics', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname === '/analytics/' && url.searchParams.get('month') === '2026-08');
        const monthly = page.locator('#finance-monthly-analysis');
        await monthly.getByRole('link', {name: 'Previous month', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.searchParams.get('month') === '2026-07');
        await page.locator('main .section-nav').getByRole('link', {name: 'Investments', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname === '/analytics/investments/');
        const form = page.locator('#investments-charts form');
        await form.locator('[name="scope"]').selectOption('cash');
        await form.getByRole('button', {name: 'Filter', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.searchParams.get('scope') === 'cash');
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    } finally {
        await context.close();
    }
});
