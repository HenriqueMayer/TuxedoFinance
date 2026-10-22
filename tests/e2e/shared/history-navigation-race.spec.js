// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function post(page, path, fields) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {
        form: {csrfmiddlewaretoken: csrf, ...fields},
        headers: {Referer: response.url()}, maxRedirects: 0,
    });
    expect(saved.status(), await saved.text()).toBe(302);
}

async function enterHistory(page, info, theme) {
    await page.setViewportSize({width: 1440, height: 900});
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    const username = `history-order-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {
        username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!',
    });
    await post(page, '/banking/create/', {name: 'Ordered history bank'});
    await page.goto('/banking/');
    const bank = page.locator('.bank-overview-card').filter({hasText: 'Ordered history bank'});
    const detail = await bank.getAttribute('href');
    await bank.press('Enter');
    await expect(page).toHaveURL(url => url.pathname === detail);
    await expect(page.getByRole('heading', {name: 'Ordered history bank', exact: true})).toBeVisible();
    await mainLink(page, 'Transactions').press('Enter');
    await expect(page).toHaveURL(/\/transactions\/$/);
    await expect(page.getByRole('heading', {name: 'Transactions', exact: true, level: 1})).toBeVisible();
    await page.evaluate(() => {
        window.historyCompletedPaths = [];
        document.addEventListener('htmx:historyCacheMiss', event => {
            event.detail.xhr.addEventListener('loadend', () => window.historyCompletedPaths.push(event.detail.path), {once: true});
        });
    });
    return detail;
}

function mainLink(page, name) {
    return page.getByRole('navigation', {name: 'Main navigation', exact: true})
        .getByRole('link', {name, exact: true});
}

async function holdHistory(page, path) {
    let release, received, finished;
    const gate = new Promise(resolve => { release = resolve; });
    const seen = new Promise(resolve => { received = resolve; });
    const done = new Promise(resolve => { finished = resolve; });
    let request = null, aborted = false;
    const failed = candidate => {
        if (candidate === request) aborted = true;
    };
    page.on('requestfailed', failed);
    const handler = async route => {
        if (request || route.request().headers()['hx-history-restore-request'] !== 'true') {
            await route.continue();
            return;
        }
        request = route.request();
        const response = await route.fetch();
        expect(response.status()).toBe(200);
        received();
        await gate;
        try {
            await route.fulfill({response});
        } catch (error) {
            if (!aborted) throw error;
        } finally { finished(); }
    };
    const matches = url => url.pathname === path;
    await page.route(matches, handler);
    return {
        seen, release,
        async complete() {
            release();
            await done;
            await expect.poll(() => page.evaluate(value =>
                window.historyCompletedPaths.includes(value), path)).toBe(true);
        },
        wasAborted: () => aborted,
        async dispose() {
            release();
            page.off('requestfailed', failed);
            await page.unroute(matches, handler);
        },
    };
}

async function expectFreshHistory(page, requests) {
    expect(await page.evaluate(() => sessionStorage.getItem('htmx-history-cache'))).toBeNull();
    expect(requests.length).toBeGreaterThan(1);
    expect(requests.every(request => request.method() === 'GET')).toBe(true);
    expect(requests.some(request => request.headers()['hx-history-restore-request'] === 'true')).toBe(true);
}

for (const theme of ['light', 'dark']) {
    test(`a delayed first Back cannot overwrite the second Back or later Forward (${theme})`, async ({page}, info) => {
        const detail = await enterHistory(page, info, theme);
        const requests = [];
        page.on('request', request => requests.push(request));
        const held = await holdHistory(page, detail);
        try {
            await page.evaluate(() => history.back());
            await held.seen;
            await page.evaluate(() => history.back());
            await expect(page).toHaveURL(/\/banking\/$/);
            await expect(page.getByRole('heading', {name: 'Your banks', exact: true})).toBeVisible();
            await held.complete();
            await expect(page).toHaveURL(/\/banking\/$/);
            await expect(page.getByRole('heading', {name: 'Your banks', exact: true})).toBeVisible();
            expect(held.wasAborted()).toBe(true);
            const fresh = page.waitForResponse(response => new URL(response.url()).pathname === detail
                && response.request().headers()['hx-history-restore-request'] === 'true');
            await page.goForward();
            expect((await fresh).status()).toBe(200);
            await expect(page).toHaveURL(url => url.pathname === detail);
            await expect(page.getByRole('heading', {name: 'Ordered history bank', exact: true})).toBeVisible();
            await expectFreshHistory(page, requests);
        } finally { await held.dispose(); }
    });

    test(`a keyboard destination supersedes an unfinished Back response (${theme})`, async ({page}, info) => {
        const detail = await enterHistory(page, info, theme);
        const requests = [];
        page.on('request', request => requests.push(request));
        const held = await holdHistory(page, detail);
        try {
            await page.evaluate(() => history.back());
            await held.seen;
            await mainLink(page, 'Home').press('Enter');
            await expect(page).toHaveURL(/\/dashboard\/$/);
            await expect(page.getByRole('heading', {name: 'Dashboard', exact: true, level: 1})).toBeVisible();
            await held.complete();
            await expect(page).toHaveURL(/\/dashboard\/$/);
            await expect(page.getByRole('heading', {name: 'Dashboard', exact: true, level: 1})).toBeVisible();
            expect(held.wasAborted()).toBe(true);
            await expectFreshHistory(page, requests);
        } finally { await held.dispose(); }
    });

    test(`a cancelled body request keeps the authorized Back response (${theme})`, async ({page}, info) => {
        const detail = await enterHistory(page, info, theme);
        const held = await holdHistory(page, detail);
        try {
            await page.evaluate(() => history.back());
            await held.seen;
            // A cancelled request never reaches beforeSend, as with a rejected
            // departure. It must not cancel the still-current history GET.
            await page.evaluate(() => {
                document.addEventListener('htmx:beforeRequest', event => {
                    if (event.detail.requestConfig.path === '/dashboard/') event.preventDefault();
                }, {once: true});
            });
            await mainLink(page, 'Home').press('Enter');
            await held.complete();
            await expect(page).toHaveURL(url => url.pathname === detail);
            await expect(page.getByRole('heading', {name: 'Ordered history bank', exact: true})).toBeVisible();
            expect(held.wasAborted()).toBe(false);
            expect(await page.evaluate(() => sessionStorage.getItem('htmx-history-cache'))).toBeNull();
        } finally { await held.dispose(); }
    });
}
