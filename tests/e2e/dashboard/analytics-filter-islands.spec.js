// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function post(page, path, fields) {
    const form = await page.request.get(path);
    const csrf = (await form.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const response = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...fields},
        headers: {Referer: form.url()}, maxRedirects: 0});
    expect(response.status(), await response.text()).toBe(302);
}

function month(offset = 0) {
    const date = new Date();
    date.setUTCDate(1);
    date.setUTCMonth(date.getUTCMonth() + offset);
    return date.toISOString().slice(0, 7);
}

function monthLabel(value) {
    return new Intl.DateTimeFormat('en', {month: 'long', year: 'numeric', timeZone: 'UTC'})
        .format(new Date(`${value}-01T12:00:00Z`));
}

async function settledIsland(page, selector = '#finance-monthly-analysis') {
    const island = page.locator(selector);
    await expect(island).not.toHaveClass(/htmx-settling/);
    // URL push and inserted HTML precede HTMX initialization and shared view
    // restoration. Begin the next keyboard interaction after both have run.
    await island.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}

async function setup(page, info, withExpense = false) {
    const username = `analytics-islands-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    if (withExpense) {
        await post(page, '/banking/create/', {name: 'Analytics bank', color: '#315D50'});
        await page.goto('/banking/accounts/create/');
        const bank = await page.locator('#id_bank option').last().getAttribute('value');
        await post(page, '/banking/accounts/create/', {bank, name: 'Analytics account', currency: 'BRL',
            opening_balance: '1000', opening_date: '2020-01-01'});
        await post(page, '/categories/create/', {name: 'Analytics category', transaction_type: 'EXPENSE'});
        await page.goto('/transactions/create/');
        const account = await page.locator('#id_bank_account option').last().getAttribute('value');
        const category = await page.locator('#id_category option').filter({hasText: /^Analytics category$/}).getAttribute('value');
        await post(page, '/transactions/create/', {title: 'Analytics source', amount: '42.50',
            transaction_type: 'EXPENSE', payment_channel: 'ACCOUNT', bank_account: account, category,
            date: `${month()}-01`});
    }
    await page.goto(`/analytics/?month=${month()}&charts_offset=0&instrument_month=${month()}&installment_month=${month()}`);
}

async function assertState(page, values, enhanced = true) {
    await expect(page).toHaveURL(url => Object.entries(values).every(([key, value]) => url.searchParams.get(key) === value));
    // Native document navigation has no HTMX initialization or animation-frame
    // callbacks when JavaScript is disabled; inspect the complete GET directly.
    if (enhanced) {
        await settledIsland(page);
        await settledIsland(page, '#reports-charts');
    }
    await expect(page.locator('#selected-period-heading')).toHaveText(monthLabel(values.month));
    await expect(page.locator('#instrument-window')).toHaveText(monthLabel(values.instrument_month));
    await expect(page.locator('#installment-window')).toHaveText(monthLabel(values.installment_month));
    const nextWindow = new URL(await page.locator('#report-balance-next').getAttribute('href'), page.url());
    expect(nextWindow.searchParams.get('charts_offset')).toBe(String(Number(values.charts_offset) + 1));
    await expect(page.locator('main h1')).toHaveCount(1);
    await expect(page.locator('#finance-monthly-analysis, #reports-charts')).toHaveCount(2);
}

for (const theme of ['light', 'dark']) {
    test(`Finance islands retain each cursor across interleaving and history (${theme})`, async ({page}, info) => {
        await page.setViewportSize({width: 320, height: 740});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await setup(page, info, true);
        await page.screenshot({path: info.outputPath(`analytics-finances-${theme}-320.png`)});
        const state = {month: month(), charts_offset: '0', instrument_month: month(), installment_month: month()};
        await page.locator('#analytics-month-previous').press('Enter');
        state.month = month(-1);
        await assertState(page, state);
        await expect(page.locator('#analytics-month-previous')).toBeFocused();
        await page.locator('#report-balance-previous').press('Enter');
        state.charts_offset = '-1';
        await assertState(page, state);
        await page.locator('#instrument-previous').press('Enter');
        state.instrument_month = month(-1);
        await assertState(page, state);
        await page.locator('#installment-previous').press('Enter');
        state.installment_month = month(-1);
        await assertState(page, state);
        await page.locator('#analytics-month-previous').press('Enter');
        state.month = month(-2);
        await assertState(page, state);
        await page.goBack();
        await assertState(page, {...state, month: month(-1)});
        await page.goForward();
        await assertState(page, state);
        // Reverse the order: a reports refresh must be retained by the next
        // monthly response too, without relying on a complete page replacement.
        await page.locator('#report-balance-previous').press('Enter');
        state.charts_offset = '-2';
        await assertState(page, state);
        await page.locator('#analytics-month-next').press('Enter');
        state.month = month(-1);
        await assertState(page, state);
    });
}

for (const first of ['reports', 'monthly']) {
    test(`Rapid independent Finance choices survive a pending ${first} response`, async ({page}, info) => {
        await setup(page, info);
        let release;
        const held = new Promise(resolve => { release = resolve; });
        let intercepted;
        const started = new Promise(resolve => { intercepted = resolve; });
        const requests = [];
        await page.route('**/analytics/?*', async route => {
            if (route.request().headers()['hx-request'] !== 'true') return route.continue();
            requests.push(new URL(route.request().url()));
            if (requests.length === 1) {
                intercepted();
                await held;
            }
            await route.continue();
        });
        try {
            const order = first === 'reports'
                ? ['#report-balance-previous', '#analytics-month-previous', '#instrument-previous', '#installment-previous']
                : ['#analytics-month-previous', '#report-balance-previous', '#instrument-previous', '#installment-previous'];
            await page.locator(order[0]).click();
            await started;
            for (const selector of order.slice(1)) await page.locator(selector).click();
            expect(requests).toHaveLength(1);
            release();
            const expected = {month: month(-1), charts_offset: '-1', instrument_month: month(-1), installment_month: month(-1)};
            await assertState(page, expected);
            expect(requests).toHaveLength(4);
            for (const [key, value] of Object.entries(expected)) expect(requests.at(-1).searchParams.get(key)).toBe(value);
        } finally {
            release();
            await page.unroute('**/analytics/?*');
        }
    });
}

test('Finance monthly horizon retains keyboard focus on the unavailable next control', async ({page}, info) => {
    await setup(page, info);
    await page.goto(`/analytics/?month=${month(5)}&charts_offset=-1`);
    const next = page.locator('#analytics-month-next');
    await next.press('Enter');
    await expect(page).toHaveURL(url => url.searchParams.get('month') === month(6)
        && url.searchParams.get('charts_offset') === '-1');
    await expect(next).toHaveAttribute('aria-disabled', 'true');
    await expect(next).toHaveAttribute('tabindex', '-1');
    await expect(next).toBeFocused();
    await expect(page.locator('#selected-period-heading')).toHaveText(monthLabel(month(6)));
    await page.keyboard.press('Shift+Tab');
    await expect(page.locator('#analytics-month-previous')).toBeFocused();
});

test('Finance keyboard month reset focuses its caption without disturbing background help', async ({page}, info) => {
    await setup(page, info);
    await page.goto(`/analytics/?month=${month(-1)}&charts_offset=-1`);
    await page.locator('#analytics-month-current').press('Enter');
    await expect(page).toHaveURL(url => !url.searchParams.has('month') && url.searchParams.get('charts_offset') === '-1');
    await expect(page.locator('#analytics-month-current')).toHaveCount(0);
    const caption = page.locator('#selected-period-heading');
    await expect(caption).toBeFocused();
    await expect(caption).toHaveAttribute('tabindex', '-1');
    await page.keyboard.press('Shift+Tab');
    await expect(page.locator('#analytics-month-previous')).toBeFocused();
    await expect(caption).not.toHaveAttribute('tabindex');
    await page.locator('#analytics-month-previous').press('Enter');
    await expect(page).toHaveURL(url => url.searchParams.get('month') === month(-1));
    await settledIsland(page);
    const help = page.locator('[aria-controls="report-balance-help"]');
    await help.focus();
    await expect(page.locator('#report-balance-help')).toBeVisible();
    await page.locator('#analytics-month-current').evaluate(element => {
        window.htmx.ajax('GET', element.href, {source: element, target: '#finance-monthly-analysis', swap: 'outerHTML'});
    });
    await expect(page).toHaveURL(url => !url.searchParams.has('month'));
    await settledIsland(page);
    await expect(help).toBeFocused();
    await expect(page.locator('#report-balance-help')).toBeVisible();
});

test('Leaving Finance aborts a held response and discards queued filter intentions', async ({page}, info) => {
    await setup(page, info);
    let release;
    const held = new Promise(resolve => { release = resolve; });
    let intercepted;
    const started = new Promise(resolve => { intercepted = resolve; });
    let completed;
    const finished = new Promise(resolve => { completed = resolve; });
    const requests = [];
    await page.route('**/analytics/?*', async route => {
        if (route.request().headers()['hx-request'] !== 'true') return route.continue();
        requests.push(route.request());
        intercepted();
        await held;
        try { await route.continue(); }
        finally { completed(); }
    });
    try {
        await page.locator('#report-balance-previous').click();
        await started;
        await page.locator('#analytics-month-previous').click();
        await page.locator('[data-app-navigation="desktop"] a[href="/planning/"]').click();
        await expect(page).toHaveURL(url => url.pathname === '/planning/');
        await expect(page.locator('#finance-analytics')).toHaveCount(0);
        release();
        await finished;
        await page.waitForLoadState('networkidle');
        await expect(page).toHaveURL(url => url.pathname === '/planning/');
        await expect(page.locator('#finance-analytics')).toHaveCount(0);
        await expect(page.locator('main h1')).toHaveCount(1);
        expect(requests).toHaveLength(1);
    } finally {
        release();
        await page.unroute('**/analytics/?*');
    }
});

test('Finance background refresh preserves help and composition in the other island', async ({page}, info) => {
    await setup(page, info, true);
    const help = page.locator('[aria-controls="report-balance-help"]');
    await help.focus();
    await help.evaluate(element => { element.dataset.continuity = 'original-help'; });
    await expect(page.locator('#report-balance-help')).toBeVisible();
    await page.locator('#analytics-month-previous').evaluate(element => {
        window.htmx.ajax('GET', element.href, {source: element, target: '#finance-monthly-analysis', swap: 'outerHTML'});
    });
    await expect(page).toHaveURL(url => url.searchParams.get('month') === month(-1));
    await settledIsland(page);
    await expect(help).toBeFocused();
    await expect(help).toHaveAttribute('data-continuity', 'original-help');
    await expect(page.locator('#report-balance-help')).toBeVisible();
    await page.locator('#analytics-month-next').press('Enter');
    await expect(page).toHaveURL(url => url.searchParams.get('month') === month());
    await settledIsland(page);
    const mark = page.locator('[aria-labelledby="category-heading"] [data-point]').first();
    await expect(mark).toHaveAttribute('aria-controls', /chart-composition-/);
    await mark.focus();
    await page.keyboard.press('Control');
    const composition = page.locator(`#${await mark.getAttribute('aria-controls')}`);
    await expect(composition).toBeVisible();
    await expect(composition).toContainText('Analytics category');
    await composition.evaluate(element => { element.dataset.continuity = 'original-composition'; });
    await page.locator('#report-balance-previous').evaluate(element => {
        window.htmx.ajax('GET', element.href, {source: element, target: '#reports-charts', swap: 'outerHTML'});
    });
    await expect(page).toHaveURL(url => url.searchParams.get('charts_offset') === '-1');
    await settledIsland(page, '#reports-charts');
    await expect(composition).toBeVisible();
    await expect(composition).toHaveAttribute('data-continuity', 'original-composition');
});

test('Modified Finance links open a native tab with the latest unrelated filters', async ({page}, info) => {
    await setup(page, info);
    await page.locator('#analytics-month-previous').press('Enter');
    await expect(page).toHaveURL(url => url.searchParams.get('month') === month(-1));
    const original = page.url();
    const popup = page.context().waitForEvent('page');
    await page.locator('#report-balance-previous').click({modifiers: ['ControlOrMeta']});
    const tab = await popup;
    try {
        await expect(tab).toHaveURL(url => url.pathname === '/analytics/' && url.searchParams.get('month') === month(-1)
            && url.searchParams.get('charts_offset') === '-1');
        await expect(page).toHaveURL(original);
    } finally { await tab.close(); }
});

test('Finance interleaved cursor links remain complete native GETs without JavaScript', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 320, height: 740}});
    try {
        const page = await context.newPage();
        await setup(page, info);
        const state = {month: month(-1), charts_offset: '0', instrument_month: month(), installment_month: month()};
        await page.locator('#analytics-month-previous').press('Enter');
        await assertState(page, state, false);
        await page.locator('#report-balance-previous').press('Enter');
        state.charts_offset = '-1';
        await assertState(page, state, false);
        await page.locator('#instrument-previous').press('Enter');
        state.instrument_month = month(-1);
        await assertState(page, state, false);
        await page.locator('#installment-previous').press('Enter');
        state.installment_month = month(-1);
        await assertState(page, state, false);
        await page.locator('#analytics-month-previous').press('Enter');
        state.month = month(-2);
        await assertState(page, state, false);
    } finally { await context.close(); }
});
