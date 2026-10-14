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
async function prepare(page, info) {
    const username = `live-filter-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {
        username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!',
    });
    for (const name of ['House heating', 'House cooling', 'Paycheck']) {
        await post(page, '/categories/create/', {name, transaction_type: 'EXPENSE'});
    }
    await page.goto('/categories/');
}
async function idle(page, id = 'category-results') {
    await expect(page.locator(`#${id}`)).not.toHaveAttribute('aria-busy', 'true');
}

for (const theme of ['light', 'dark']) {
    test(`typing, deletion and history keep stable controls and useful entries (${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({width: 390, height: 740});
        await prepare(page, info);
        const search = page.locator('#filter-search');
        await expect(page.locator('[data-live-submit]')).toBeHidden();
        await expect(page.locator('#category-clear-filters')).toHaveCount(0);
        await search.focus();
        const initial = await page.evaluate(() => {
            window.liveSearchControl = document.getElementById('filter-search');
            window.liveDocumentMarker = true;
            return history.length;
        });
        await page.keyboard.type('House', {delay: 20});
        await expect(page).toHaveURL(/q=House$/);
        await expect(page.locator('#category-results-status')).toHaveText('2 categories');
        await expect(search).toBeFocused();
        expect(await page.evaluate(() => history.length)).toBe(initial + 1);
        await search.press('ArrowLeft');
        await search.press('ArrowLeft');
        await page.keyboard.type('s');
        await expect(page).toHaveURL(/q=Housse$/);
        expect(await page.evaluate(() => document.activeElement.selectionStart)).toBe(4);
        await page.keyboard.press('Backspace');
        await expect(page).toHaveURL(/q=House$/);
        expect(await page.evaluate(() => document.activeElement.selectionStart)).toBe(3);
        await search.press('End');
        await page.keyboard.type(' heating', {delay: 20});
        await expect(page).toHaveURL(/q=House\+heating$/);
        await expect(page.locator('#category-results-status')).toHaveText('1 category');
        await expect(page.getByRole('link', {name: 'New Category', exact: true})).toHaveAttribute('href', /next=%2Fcategories%2F%3Fq%3DHouse%2Bheating/);
        expect(await page.locator('input[type="hidden"][name="next"]').first().inputValue()).toBe('/categories/?q=House+heating');
        expect(await page.evaluate(() => history.length)).toBe(initial + 1);
        expect(await page.evaluate(() => document.activeElement.selectionStart)).toBe('House heating'.length);
        expect(await page.evaluate(() => window.liveSearchControl === document.getElementById('filter-search'))).toBe(true);
        await page.goBack();
        await expect(page).toHaveURL(/\/categories\/$/);
        await expect(search).toHaveValue('');
        await expect(page.locator('#category-results-status')).toHaveText('12 categories');
        await page.goForward();
        await expect(search).toHaveValue('House heating');
        await expect(page.locator('#category-results-status')).toHaveText('1 category');
        await search.press('ControlOrMeta+A');
        await page.keyboard.press('Backspace');
        await expect(page).toHaveURL(/\/categories\/$/);
        await expect(page.locator('#category-results-status')).toHaveText('12 categories');
        await expect(page.locator('#category-clear-filters')).toHaveCount(0);
        await expect(search).toBeFocused();
        expect(await page.evaluate(() => window.liveDocumentMarker)).toBe(true);
        // Enter commits immediately and native choice changes apply on selection.
        await page.keyboard.type('House');
        await search.press('Enter');
        await expect(page.locator('#category-results-status')).toHaveText('2 categories');
        await page.locator('#category-filters .filter-disclosure > summary').press('Enter');
        await page.locator('#filter-level').selectOption('sub');
        await expect(page).toHaveURL(/level=sub/);
        await expect(page.getByText('No matching categories', {exact: true})).toBeVisible();
        await expect(page.locator('#category-clear-filters')).toHaveCount(1);
        await page.locator('#category-clear-filters').click();
        await expect(search).toHaveValue('');
        await expect(page.locator('#filter-level')).toHaveValue('');
        await expect(search).toBeFocused();
        await idle(page);
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({path: info.outputPath(`live-filters-${theme}.png`), fullPage: true});
        await search.fill('House');
        await search.press('Enter');
        await expect(page).toHaveURL(/q=House$/);
        await page.getByRole('link', {name: 'New Category', exact: true}).click();
        await expect(page).toHaveURL(url => url.pathname === '/categories/create/' && url.searchParams.get('next') === '/categories/?q=House');
        await page.getByRole('link', {name: 'Cancel', exact: true}).click();
        await expect(search).toHaveValue('House');
        await expect(page.locator('#category-results-status')).toHaveText('2 categories');
    });

    test(`preferred date errors recover without replacing the input (${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await prepare(page, info);
        await page.goto('/transactions/');
        await page.locator('#transaction-extra-filters > summary').focus();
        await page.keyboard.press('Enter');
        const date = page.locator('#filter-date');
        await page.evaluate(() => { window.liveDateControl = document.getElementById('filter-date'); });
        await date.fill('32/01/2026');
        await date.press('Tab');
        await expect(page.locator('#filter-date-error-1')).toBeVisible();
        await expect(date).toHaveValue('32/01/2026');
        await date.fill('15/01/2026');
        await date.press('Tab');
        await expect(page).toHaveURL(/date=2026-01-15/);
        await expect(page.locator('#filter-date-error-1')).toHaveCount(0);
        await expect(date).not.toHaveAttribute('aria-invalid', 'true');
        await expect(date).not.toHaveAttribute('aria-describedby', /filter-date-error/);
        expect(await page.evaluate(() => window.liveDateControl === document.getElementById('filter-date'))).toBe(true);
        await date.fill('');
        await date.press('Tab');
        await expect(page).toHaveURL(/\/transactions\/$/);
        await expect(page.locator('#transaction-clear-filters')).toHaveCount(0);
    });
}

test('an older delayed filter response cannot replace newer results', async ({page}, info) => {
    await prepare(page, info);
    let releaseOld;
    const oldStarted = new Promise(resolve => { releaseOld = resolve; });
    await page.route('**/categories/?**', async route => {
        const url = new URL(route.request().url());
        if (route.request().resourceType() !== 'fetch' || url.searchParams.get('q') !== 'heating') return route.continue();
        const response = await route.fetch();
        releaseOld();
        await new Promise(resolve => setTimeout(resolve, 900));
        await route.fulfill({response}).catch(() => {}); // The obsolete request may already be aborted.
    });
    await page.locator('#filter-search').fill('heating');
    await oldStarted;
    await page.locator('#filter-search').fill('cooling');
    await expect(page).toHaveURL(/q=cooling/);
    await expect(page.locator('#category-results')).toContainText('House cooling');
    await page.waitForTimeout(1000);
    await expect(page.locator('#category-results')).not.toContainText('House heating');
    await expect(page.locator('#filter-search')).toHaveValue('cooling');
    await idle(page);
});

test('failed live GET reveals a complete native submit recovery', async ({page}, info) => {
    await prepare(page, info);
    await page.route('**/categories/?**', route => route.request().resourceType() === 'fetch'
        ? route.abort('failed') : route.continue());
    await page.locator('#filter-search').fill('heating');
    const submit = page.locator('#category-filters [data-live-submit]');
    await expect(submit).toBeVisible();
    await submit.press('Enter');
    await expect(page).toHaveURL(/q=heating/);
    await expect(page.locator('#category-results-status')).toHaveText('1 category');
    await expect(page.locator('#category-results')).toContainText('House heating');
    await expect(page.locator('#category-filters [data-live-submit]')).toBeHidden();
});

for (const theme of ['light', 'dark']) {
    test(`GET filters and changed action-only POST rows do not warn on departure (${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await prepare(page, info);
        await post(page, '/banking/create/', {name: 'Live institution'});
        await post(page, '/banking/create/', {name: 'Other institution'});
        const form = await page.request.get('/banking/accounts/create/');
        const bank = (await form.text()).match(/<option value="(\d+)"[^>]*>Live institution<\/option>/)[1];
        await post(page, '/banking/accounts/create/', {
            bank, name: 'Live account', currency: 'BRL', opening_balance: '100', opening_date: '2026-01-01',
        });
        await page.goto('/banking/');
        const dialogs = [];
        page.on('dialog', async dialog => { dialogs.push(dialog.message()); await dialog.dismiss(); });
        const disclosure = page.locator(`#bank-${bank}`);
        await disclosure.locator(':scope > summary').press('Enter');
        await expect(disclosure).toHaveAttribute('open', '');
        await expect(page.locator('#bank-results form[method="post"]')).toHaveCount(1);
        const query = page.locator('#bank-filter-form input[name="q"]');
        await query.fill('Live');
        await query.press('Enter');
        await expect(page).toHaveURL(/q=Live/);
        await expect(disclosure).toHaveAttribute('open', '');
        await query.fill('Other');
        await query.press('Enter');
        await expect(page.locator('#bank-results form[method="post"]')).toHaveCount(0);
        await page.locator('#app-desktop-transactions-link').click();
        await expect(page).toHaveURL(/\/transactions\/$/);
        await page.goBack();
        await expect(page).toHaveURL(/\/banking\/\?q=Other$/);
        await expect(query).toHaveValue('Other');
        await page.locator('#bank-filter-form a[data-live-reset]').click();
        await expect(page.locator('#bank-results form[method="post"]')).toHaveCount(1);
        await page.locator('#app-desktop-transactions-link').click();
        await expect(page).toHaveURL(/\/transactions\/$/);
        expect(dialogs).toEqual([]);
    });
}

for (const theme of ['light', 'dark']) {
    test(`typing immediately after a delayed Clear uses reset controls (${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await prepare(page, info);
        await post(page, '/banking/create/', {name: 'Clear institution'});
        await page.goto('/banking/accounts/create/');
        const bank = await page.locator('#id_bank option').last().getAttribute('value');
        await post(page, '/banking/accounts/create/', {
            bank, name: 'Clear cash', currency: 'BRL', opening_balance: '1000', opening_date: '2026-01-01',
        });
        await page.goto('/transactions/create/');
        const account = await page.locator('#id_bank_account option').last().getAttribute('value');
        const category = name => page.locator('#id_category option').filter({hasText: new RegExp(`^${name}$`)}).getAttribute('value');
        const heating = await category('House heating');
        const cooling = await category('House cooling');
        const common = {amount: '25', transaction_type: 'EXPENSE', payment_channel: 'ACCOUNT', bank_account: account, installments: '1'};
        await post(page, '/transactions/create/', {...common, title: 'Heating record', category: heating, date: '15/01/2026'});
        await post(page, '/transactions/create/', {...common, title: 'Cooling record', category: cooling, date: '15/02/2026'});
        const old = new URLSearchParams({q: 'heating', type: 'EXPENSE', recurrence: 'oneoff', sort: 'oldest',
            month: '2026-01', date: '2026-01-15', category: heating});
        await page.goto(`/transactions/?${old}`);
        await expect(page.locator('#transaction-results-status')).toHaveText('1 transaction');

        let releaseClear, markStarted, markCompleted;
        const hold = new Promise(resolve => { releaseClear = resolve; });
        const started = new Promise(resolve => { markStarted = resolve; });
        const completed = new Promise(resolve => { markCompleted = resolve; });
        await page.route('**/transactions/**', async route => {
            const url = new URL(route.request().url());
            if (route.request().resourceType() !== 'fetch' || url.pathname !== '/transactions/' || url.search) return route.continue();
            const response = await route.fetch();
            markStarted();
            await hold;
            await route.fulfill({response}).catch(() => {}); // Superseded Clear is expected to be aborted.
            markCompleted();
        });
        const clear = page.locator('#transaction-clear-filters');
        await clear.press('Enter');
        await started;
        await expect(clear).toBeFocused();
        for (const name of ['q', 'type', 'recurrence', 'month', 'date', 'category']) {
            await expect(page.locator(`#transaction-filters [name="${name}"]`)).toHaveValue('');
        }
        await expect(page.locator('#filter-sort')).toHaveValue('newest');
        await expect(page.locator('#filter-category-search')).toHaveValue('');
        await expect(page.locator('#transaction-filters [data-native-date-picker]')).toHaveValue('');
        const search = page.locator('#filter-search');
        await search.click();
        await page.keyboard.type('cooling');
        await expect(page).toHaveURL(url => url.pathname === '/transactions/' &&
            url.searchParams.get('q') === 'cooling' && Array.from(url.searchParams.keys()).every(name => name === 'q'));
        await expect(page.locator('#transaction-results-status')).toHaveText('1 transaction');
        await expect(page.locator('#transaction-results')).toContainText('Cooling record');
        await expect(page.locator('#transaction-results')).not.toContainText('Heating record');
        releaseClear();
        await completed;
        await expect(search).toHaveValue('cooling');
        await expect(search).toBeFocused();
        expect(await search.evaluate(input => input.selectionStart)).toBe(7);
        await idle(page, 'transaction-results');
    });
}

for (const theme of ['light', 'dark']) {
    test(`Back restores the applied query after leaving a pending search (${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await prepare(page, info);
        const search = page.locator('#filter-search');
        await search.click();
        await page.keyboard.type('heating');
        await search.press('Enter');
        await expect(page).toHaveURL(/\/categories\/\?q=heating$/);
        await expect(page.locator('#category-results-status')).toHaveText('1 category');
        await expect(page.locator('#category-results')).toContainText('House heating');

        let releasePending;
        const pending = new Promise(resolve => { releasePending = resolve; });
        await page.route('**/categories/?**', async route => {
            if (route.request().resourceType() !== 'fetch' || new URL(route.request().url()).searchParams.get('q') !== 'cooling') return route.continue();
            // Hold only the newer query; navigating away does not commit it.
            await pending;
            await route.abort('aborted').catch(() => {});
        });
        try {
            await search.press('ControlOrMeta+A');
            await page.keyboard.type('cooling');
            await page.getByRole('link', {name: 'New Category', exact: true}).press('Enter');
            await expect(page).toHaveURL(url => url.pathname === '/categories/create/' && url.searchParams.get('next') === '/categories/?q=heating');
            // Live forms opt out of the HTMX DOM cache. Back must retrieve the
            // applied URL, then restore presentation without replaying the draft.
            const fresh = page.waitForResponse(response => response.request().method() === 'GET' &&
                new URL(response.url()).pathname === '/categories/' &&
                new URL(response.url()).searchParams.get('q') === 'heating' &&
                response.request().headers()['hx-history-restore-request'] === 'true');
            await page.goBack();
            await fresh;
            await expect(page.locator('[data-workspace-restored]')).toBeVisible();
            await expect(page).toHaveURL(/\/categories\/\?q=heating$/);
            await expect(search).toHaveValue('heating');
            await expect(search).toBeFocused();
            await expect(page.locator('#category-results-status')).toHaveText('1 category');
            await expect(page.locator('#category-results')).toContainText('House heating');
            await expect(page.locator('#category-results')).not.toContainText('House cooling');
        } finally { releasePending(); }
    });
}
