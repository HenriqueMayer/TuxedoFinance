// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function signup(page, testInfo) {
    const response = await page.request.get('/accounts/signup/');
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const username = `assets-${testInfo.workerIndex}-${Date.now()}`;
    const saved = await page.request.post('/accounts/signup/', {
        form: { csrfmiddlewaretoken: csrf, username, email: `${username}@example.test`,
            password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' },
        headers: { Referer: response.url() }, maxRedirects: 0,
    });
    expect(saved.status(), await saved.text()).toBe(302);
}

async function openOldDocument(page, path, { legacy = false } = {}) {
    // Model an already-open tab from an earlier release without changing files
    // shared by other tests. Its head and loaded CSS predate the current server.
    await page.route('**/static/css/app.css?v=previous-release', async route => {
        const response = await route.fetch();
        await route.fulfill({ response, body: `${await response.text()}\nhtml{--asset-refresh-probe:old}` });
    });
    await page.route(url => url.pathname === path, async route => {
        if (!route.request().isNavigationRequest()) return route.continue();
        const response = await route.fetch();
        let html = await response.text();
        expect(html).toMatch(/<meta name="tuxedo-assets" content="[a-f0-9]+">/);
        html = html.replace(/(<meta name="tuxedo-assets" content=")[^"]+/, '$1previous-release')
            .replace(/(\/static\/css\/app\.css\?v=)[a-f0-9]+/, '$1previous-release');
        if (legacy) html = html.replace(/<script[^>]+src="[^"]*\/runtime-assets\.js[^>]*><\/script>/, '');
        await route.fulfill({ response, body: html });
    }, { times: 1 });
    await page.goto(path);
    await expect.poll(() => page.evaluate(() => getComputedStyle(document.documentElement)
        .getPropertyValue('--asset-refresh-probe').trim())).toBe('old');
    await page.evaluate(() => { window.assetDocumentMarker = 'old document'; });
}

for (const legacy of [false, true]) {
    test(`an old ${legacy ? 'legacy' : 'versioned'} tab refreshes assets once at the requested GET destination`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width: 1440, height: 900 });
        await signup(page, testInfo);
        await openOldDocument(page, '/banking/', { legacy });
        const destination = '/transactions/?asset-regression=1';
        const documents = [];
        page.on('request', request => {
            if (request.isNavigationRequest()) documents.push(new URL(request.url()).pathname);
        });
        const link = page.locator('header [data-nav-item="activity"] > a').first();
        await link.evaluate((element, href) => {
            element.href = href;
            window.htmx.process(element);
        }, destination);
        const staleResponse = page.waitForResponse(response => response.request().resourceType() === 'xhr'
            && new URL(response.url()).pathname === '/transactions/');
        await link.click();
        const stale = await staleResponse;
        expect(stale.request().headers()['hx-request']).toBeUndefined();
        expect(stale.request().headers()['x-tuxedo-assets']).toBe(legacy ? undefined : 'previous-release');
        expect(stale.headers()['hx-redirect']).toBe(destination);
        await expect(page).toHaveURL(new RegExp('/transactions/\\?asset-regression=1$'));
        await expect(page.locator('main h1')).toBeVisible();
        await expect.poll(() => page.evaluate(() => window.assetDocumentMarker)).toBeUndefined();
        await expect.poll(() => page.evaluate(() => getComputedStyle(document.documentElement)
            .getPropertyValue('--asset-refresh-probe').trim())).toBe('');
        expect(documents).toEqual(['/transactions/']);
        const revision = await page.locator('meta[name="tuxedo-assets"]').getAttribute('content');
        expect(revision).toMatch(/^[a-f0-9]{20}$/);
        await page.evaluate(() => { window.assetDocumentMarker = 'current document'; });
        const currentResponse = page.waitForResponse(response => response.request().resourceType() === 'xhr'
            && new URL(response.url()).pathname === '/banking/');
        await page.locator('header [data-nav-item="banks"] > a').first().click();
        const current = await currentResponse;
        expect(current.request().headers()['x-tuxedo-assets']).toBe(revision);
        expect(current.headers()['hx-redirect']).toBeUndefined();
        await expect(page).toHaveURL(/\/banking\/$/);
        expect(await page.evaluate(() => window.assetDocumentMarker)).toBe('current document');
        expect(documents).toEqual(['/transactions/']);
    });
}

test('a stale tab submits an invalid HTMX form once and retains errors and entered values', async ({ page }, testInfo) => {
    await signup(page, testInfo);
    await openOldDocument(page, '/sandbox/');
    await page.getByLabel('Gross monthly salary', { exact: true }).fill('-10');
    await page.locator('#id_draft_name').fill('Keep this unfinished plan');
    const posts = [];
    const navigations = [];
    page.on('request', request => {
        if (request.method() === 'POST') posts.push(request.url());
        if (request.isNavigationRequest()) navigations.push(request.url());
    });
    const responsePromise = page.waitForResponse(response => response.request().method() === 'POST'
        && new URL(response.url()).pathname === '/sandbox/');
    await page.getByRole('button', { name: 'Calculate', exact: true }).click();
    const response = await responsePromise;
    expect(response.request().headers()['x-tuxedo-assets']).toBe('previous-release');
    expect(response.headers()['hx-redirect']).toBeUndefined();
    await expect(page.locator('#id_gross_salary')).toHaveAttribute('aria-invalid', 'true');
    await expect(page.locator('#id_gross_salary')).toHaveValue('-10');
    await expect(page.locator('#id_draft_name')).toHaveValue('Keep this unfinished plan');
    expect(posts).toHaveLength(1);
    expect(navigations).toEqual([]);
    expect(await page.evaluate(() => window.assetDocumentMarker)).toBe('old document');
});
