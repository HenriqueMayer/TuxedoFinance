// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect, chromium} = require('@playwright/test');

// Full Chromium can freeze documents; the headless shell disables BFCache at
// its delegate. Record privacy cases without tracing/screencasting so the
// persisted-page regression cannot silently become an ordinary GET.
test.use({
    launchOptions: {executablePath: chromium.executablePath(), ignoreDefaultArgs: ['--disable-back-forward-cache']},
    trace: 'off', video: 'off',
});

const password = 'Q7!vN4#xR9@tL2$k';

async function post(page, path, fields) {
    const response = await page.request.get(path);
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {
        form: {csrfmiddlewaretoken: token, ...fields},
        headers: {Referer: response.url()}, maxRedirects: 0,
    });
    expect(saved.status(), await saved.text()).toBe(302);
}

async function seed(page, info) {
    const suffix = `${info.workerIndex}-${Date.now()}`;
    const users = {};
    // Leave Alice signed in. Bob already has a separate owned bank for the
    // later real login, without adding setup pages to browser history.
    for (const name of ['bob', 'alice']) {
        const username = `${name}-history-${suffix}`;
        const bank = `${name}-private-bank-${suffix}`;
        await post(page, '/accounts/signup/', {
            username, email: `${username}@example.test`, password1: password, password2: password,
        });
        await post(page, '/banking/create/', {name: bank});
        users[name] = {username, bank};
    }
    return users;
}

async function logout(page) {
    const options = page.locator('header details').filter({has: page.locator('form[action="/accounts/logout/"]')}).first();
    await options.locator('summary').press('Enter');
    await options.getByRole('button', {name: 'Log out', exact: true}).press('Enter');
    await expect(page).toHaveURL(url => url.pathname === '/');
    await expect(page.locator('main[data-workspace-user]')).toHaveCount(0);
}

async function login(page, username) {
    await page.goto('/accounts/login/');
    await page.locator('#id_username').fill(username);
    await page.locator('#id_password').fill(password);
    await page.locator('#id_password').press('Enter');
    await expect(page).toHaveURL(/\/dashboard\/$/);
    await expect(page.locator('main[data-workspace-user]')).toBeVisible();
}

async function leaveBanks(page, bank) {
    await page.goto('/banking/');
    await expect(page.locator('main')).toContainText(bank);
    await page.getByRole('navigation', {name: 'Main navigation', exact: true})
        .getByRole('link', {name: 'Transactions', exact: true}).press('Enter');
    await expect(page).toHaveURL(/\/transactions\/$/);
}

async function sameTabDraftPrivacy(page, info) {
    await page.setViewportSize({width: 1440, height: 900});
    const users = await seed(page, info);
    await page.goto('/transactions/create/');
    const formUrl = page.url();
    const formHistoryLength = await page.evaluate(() => history.length);
    await page.locator('#id_title').fill('Alice private same-tab draft');
    page.once('dialog', dialog => dialog.accept());
    await page.goto('/transactions/');
    await logout(page);
    await login(page, users.bob.username);
    const bob = await page.locator('main').getAttribute('data-workspace-user');
    const freshGet = page.waitForResponse(response => response.request().isNavigationRequest()
        && response.request().method() === 'GET' && response.url() === formUrl);
    const distance = await page.evaluate(length => length - history.length, formHistoryLength);
    expect(distance).toBeLessThan(0);
    // Go directly to the earlier native entry. Traversing intermediary login
    // pages can legitimately redirect/replace and abort goBack's load wait.
    await page.evaluate(step => history.go(step), distance);
    const response = await freshGet;
    expect(response.status()).toBe(200);
    expect(await response.text()).not.toContain('Alice private same-tab draft');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('main')).toHaveAttribute('data-workspace-user', bob);
    await expect(page.locator('#id_title')).toHaveValue('');
}

for (const theme of ['light', 'dark']) {
    test(`Back reauthorizes private pages after logout and another user's login (${theme})`, async ({page}, info) => {
        await page.setViewportSize({width: 1440, height: 900});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const users = await seed(page, info);
        await leaveBanks(page, users.alice.bank);
        await logout(page);
        expect(await page.evaluate(() => sessionStorage.getItem('htmx-history-cache'))).toBeNull();
        await login(page, users.bob.username);
        const bob = await page.locator('main').getAttribute('data-workspace-user');
        const requests = [];
        page.on('request', request => {
            if (request.resourceType() === 'document' || request.resourceType() === 'xhr') {
                requests.push(`${request.method()} ${new URL(request.url()).pathname}`);
            }
        });
        let restoredBank = false;
        for (let step = 0; step < 5; step++) {
            await page.goBack();
            await page.waitForLoadState('networkidle');
            await expect(page.locator('body')).not.toContainText(users.alice.bank);
            if (new URL(page.url()).pathname !== '/banking/') continue;
            await expect(page.locator('main')).toHaveAttribute('data-workspace-user', bob);
            await expect(page.locator('main')).toContainText(users.bob.bank);
            expect(requests).toContain('GET /banking/');
            restoredBank = true;
            break;
        }
        expect(restoredBank).toBe(true);
        expect(requests.every(request => request.startsWith('GET '))).toBe(true);
    });
}

test('Back after logout reaches a working login instead of cached financial HTML', async ({page}, info) => {
    await page.setViewportSize({width: 1440, height: 900});
    const users = await seed(page, info);
    await leaveBanks(page, users.alice.bank);
    await logout(page);
    await page.goBack();
    await expect(page).toHaveURL(/\/accounts\/login\/\?next=/);
    await expect(page.locator('main[data-workspace-user]')).toHaveCount(0);
    await expect(page.locator('body')).not.toContainText(users.alice.bank);
    await page.locator('#id_username').fill(users.bob.username);
    await page.locator('#id_password').fill(password);
    const loginResponse = page.waitForResponse(response =>
        response.request().method() === 'POST' && new URL(response.url()).pathname === '/accounts/login/');
    await page.locator('#id_password').press('Enter');
    expect((await loginResponse).status()).toBe(302);
    await expect(page).toHaveURL(/\/transactions\/$/);
    await expect(page.locator('main[data-workspace-user]')).toBeVisible();
});

test('an open tab reauthorizes history and drops another user\'s unsent fields', async ({page, context}, info) => {
    await page.setViewportSize({width: 1440, height: 900});
    const users = await seed(page, info);
    await page.goto('/transactions/');
    await page.getByRole('link', {name: 'New transaction', exact: true}).first().press('Enter');
    await expect(page).toHaveURL(url => url.pathname === '/transactions/create/');
    const formUrl = page.url();
    await page.locator('#id_title').fill('Alice private unsent title');
    await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
    await page.getByRole('button', {name: 'Leave page', exact: true}).press('Enter');
    await expect(page).toHaveURL(/\/transactions\/$/);
    const other = await context.newPage();
    try {
        await other.goto('/dashboard/');
        await logout(other);
        await login(other, users.bob.username);
        const bob = await other.locator('main').getAttribute('data-workspace-user');
        const response = page.waitForResponse(item =>
            item.request().method() === 'GET' && item.url() === formUrl);
        await page.goBack();
        const authorized = await response;
        expect(authorized.status()).toBe(200);
        expect(await authorized.text()).not.toContain('Alice private unsent title');
        await expect(page).toHaveURL(formUrl);
        await expect(page.locator('main')).toHaveAttribute('data-workspace-user', bob);
        await expect(page.locator('#id_title')).toHaveValue('');
        expect(await page.evaluate(() => sessionStorage.getItem('tuxedo.history-workspace.v2') || ''))
            .not.toContain('Alice private unsent title');
    } finally {
        await other.close();
    }
});

test('native form history drops a draft after logout and login in the same tab', async ({page}, info) => {
    await sameTabDraftPrivacy(page, info);
});

test('legacy DOM cache is discarded at startup and before a history traversal', async ({page}, info) => {
    await seed(page, info);
    await page.addInitScript(() => sessionStorage.setItem('htmx-history-cache', JSON.stringify([
        {url: '/banking', content: '<main>Legacy private DOM</main>', title: 'Old private page', scroll: 0},
    ])));
    await page.goto('/banking/');
    expect(await page.evaluate(() => sessionStorage.getItem('htmx-history-cache'))).toBeNull();
    await page.getByRole('navigation', {name: 'Main navigation', exact: true})
        .getByRole('link', {name: 'Transactions', exact: true}).press('Enter');
    await expect(page).toHaveURL(/\/transactions\/$/);
    // Model data left by an old document after the current bootstrap ran.
    await page.evaluate(() => sessionStorage.setItem('htmx-history-cache', JSON.stringify([
        {url: '/banking', content: '<main>Legacy private DOM</main>', title: 'Old private page', scroll: 0},
    ])));
    const response = page.waitForResponse(item =>
        item.request().method() === 'GET' && new URL(item.url()).pathname === '/banking/');
    await page.goBack();
    expect((await response).status()).toBe(200);
    await expect(page.locator('main[data-workspace-user]')).toBeVisible();
    await expect(page.locator('body')).not.toContainText('Legacy private DOM');
    expect(await page.evaluate(() => sessionStorage.getItem('htmx-history-cache'))).toBeNull();
});

test.describe('browser BFCache privacy', () => {
    test('a persisted native document reauthorizes with GET before restoring its own draft', async ({page, context}, info) => {
        await seed(page, info);
        await context.addInitScript(() => window.addEventListener('pageshow', event => {
            const records = JSON.parse(sessionStorage.getItem('privacy-bfcache-proof') || '[]');
            records.push({path: location.pathname, persisted: event.persisted});
            sessionStorage.setItem('privacy-bfcache-proof', JSON.stringify(records));
        }));
        // Admit this one real app document with the previous cache policy.
        // Current Chromium may reject no-store outright; the controller must
        // also protect browsers/legacy documents which do keep frozen HTML.
        await page.route(url => url.pathname === '/transactions/create/', async route => {
            const response = await route.fetch();
            await route.fulfill({response, headers: {...response.headers(), 'cache-control': 'private, no-cache'}});
        }, {times: 1});
        await page.goto('/transactions/create/?next=%2Ftransactions%2F');
        await page.unrouteAll({behavior: 'wait'});
        const formUrl = page.url();
        await page.locator('#id_title').fill('Same user private draft');
        await page.locator('#id_title').focus();
        await page.evaluate(() => window.scrollTo(0, 180));
        const top = await page.evaluate(() => scrollY);
        page.once('dialog', dialog => dialog.accept());
        await page.goto('/transactions/');
        const posts = [];
        page.on('request', request => { if (request.method() === 'POST') posts.push(request.url()); });
        const freshGet = page.waitForResponse(response => response.request().isNavigationRequest()
            && response.request().method() === 'GET' && response.url() === formUrl);
        // BFCache restoration emits no load event, so do not use goBack's
        // default load wait or accept a test that never froze the document.
        await page.evaluate(() => { setTimeout(() => history.back(), 0); });
        const response = await freshGet;
        expect(response.status()).toBe(200);
        expect(response.headers()['cache-control']).toContain('private');
        expect(response.headers()['cache-control']).toContain('no-store');
        await expect(page.locator('html')).not.toHaveAttribute('hidden');
        await expect(page.locator('#id_title')).toHaveValue('Same user private draft');
        await expect(page.locator('#id_title')).toBeFocused();
        await expect.poll(() => page.evaluate(expected => Math.abs(scrollY - expected), top)).toBeLessThan(4);
        expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem('privacy-bfcache-proof') || '[]')
            .some(record => record.path === '/transactions/create/' && record.persisted))).toBe(true);
        expect(posts).toEqual([]);
    });

    test('native history reauthorizes after another tab changes the account', async ({page, context}, info) => {
        await page.setViewportSize({width: 1440, height: 900});
        const users = await seed(page, info);
        await page.goto('/banking/');
        await expect(page.locator('main')).toContainText(users.alice.bank);
        // Native full-document navigation, so HTMX is not the cache owner.
        await page.goto('/transactions/');
        const other = await context.newPage();
        try {
            await other.goto('/dashboard/');
            await logout(other);
            await login(other, users.bob.username);
            const bob = await other.locator('main').getAttribute('data-workspace-user');
            const freshGet = page.waitForResponse(response => response.request().isNavigationRequest()
                && response.request().method() === 'GET' && new URL(response.url()).pathname === '/banking/');
            await page.evaluate(() => { setTimeout(() => history.back(), 0); });
            expect((await freshGet).status()).toBe(200);
            await expect(page.locator('main')).toHaveAttribute('data-workspace-user', bob);
            await expect(page.locator('main')).toContainText(users.bob.bank);
            await expect(page.locator('body')).not.toContainText(users.alice.bank);
        } finally {
            await other.close();
        }
    });
});

test.describe('native history privacy', () => {
    test.use({javaScriptEnabled: false});
    test('native form history drops a draft after a same-tab account change without JavaScript', async ({page}, info) => {
        await sameTabDraftPrivacy(page, info);
    });
    test('native financial forms retain bound errors and explicit saves without browser autocomplete', async ({page}, info) => {
        const users = await seed(page, info);
        await page.goto('/banking/create/');
        await expect(page.locator('main form')).toHaveAttribute('autocomplete', 'off');
        const name = page.locator('#id_name');
        await name.fill(users.alice.bank);
        const invalid = page.waitForResponse(response => response.request().method() === 'POST'
            && new URL(response.url()).pathname === '/banking/create/');
        await name.press('Enter');
        expect((await invalid).status()).toBe(200);
        await expect(name).toHaveValue(users.alice.bank);
        await expect(name).toHaveAttribute('aria-invalid', 'true');
        const savedName = `${users.alice.bank}-saved`;
        await name.fill(savedName);
        const saved = page.waitForResponse(response => response.request().method() === 'POST'
            && new URL(response.url()).pathname === '/banking/create/');
        await name.press('Enter');
        expect((await saved).status()).toBe(302);
        await expect(page).toHaveURL(/\/banking\/$/);
        await expect(page.locator('main')).toContainText(savedName);
    });
    test('Back after logout keeps the native login and ownership checks', async ({page}, info) => {
        await page.setViewportSize({width: 1440, height: 900});
        const users = await seed(page, info);
        await leaveBanks(page, users.alice.bank);
        await logout(page);
        await page.goBack();
        await expect(page).toHaveURL(/\/accounts\/login\/\?next=/);
        await expect(page.locator('main[data-workspace-user]')).toHaveCount(0);
        await expect(page.locator('body')).not.toContainText(users.alice.bank);
        await page.locator('#id_username').fill(users.bob.username);
        await page.locator('#id_password').fill(password);
        await page.locator('#id_password').press('Enter');
        await expect(page).toHaveURL(/\/transactions\/$/);
    });
});
