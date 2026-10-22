// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { selectChoice } = require('../helpers/forms');

const title = 'Historical recurring expense with a deliberately descriptive title for error recovery';
const accountName = 'Cash account for recurring commitments with an intentionally long descriptive name';
const recurrenceError = /^This recurring transaction would generate more than [\d,.\s]+ monthly occurrences\. Review its start and end dates\.$/;

async function postForm(page, path, fields) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {
        form: { csrfmiddlewaretoken: csrf, ...fields },
        headers: { Referer: response.url() }, maxRedirects: 0,
    });
    expect(saved.status(), (await saved.text()).match(/role="alert"[^>]*>[^<]+/g)?.join(' ') || path).toBe(302);
}

async function prepare(page, testInfo) {
    const username = `recurrence-${testInfo.workerIndex}-${Date.now()}`;
    await postForm(page, '/accounts/signup/', {
        username, email: `${username}@example.test`,
        password1: 'M8!qL4@vZ7#rT2', password2: 'M8!qL4@vZ7#rT2',
    });
    await postForm(page, '/banking/create/', { name: 'Recurrence limits bank' });
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    // A zero balance with an unknown opening date accepts genuine old history;
    // the recurrence limit must be the only reason this submission is rejected.
    await postForm(page, '/banking/accounts/create/', {
        bank, name: accountName, currency: 'BRL', opening_balance: '0', opening_date: '',
    });
    await postForm(page, '/categories/create/', {
        name: 'Historical commitments', transaction_type: 'EXPENSE',
    });
    await page.goto('/transactions/create/');
    return {
        bank,
        account: await page.locator('#id_bank_account option').last().getAttribute('value'),
        category: await page.locator('#id_category option').filter({ hasText: /^Historical commitments$/ }).getAttribute('value'),
    };
}

async function enterUnboundedRecurrence(page, data) {
    await selectChoice(page.locator('#id_transaction_type'), 'EXPENSE');
    await page.locator('#id_title').fill(title);
    await page.locator('#id_amount').fill('1.00');
    const date = page.locator('#id_date');
    await expect(date).toHaveAttribute('placeholder', 'DD/MM/YYYY');
    await date.focus();
    await page.keyboard.press('ControlOrMeta+A');
    await page.keyboard.type('01/01/0001');
    await page.keyboard.press('Tab');
    await expect(date).toHaveValue('01/01/0001');
    await selectChoice(page.locator('#id_category'), data.category);
    await selectChoice(page.locator('#id_payment_channel'), 'ACCOUNT');
    await selectChoice(page.locator('#id_bank_account'), data.account);
    await page.locator('.entry-advanced > summary').focus();
    await page.keyboard.press('Enter');
    await page.locator('#id_is_fixed').focus();
    await page.keyboard.press('Space');
    await expect(page.locator('#id_is_fixed')).toBeChecked();
    await expect(page.locator('#id_fixed_until')).toBeVisible();
    await page.locator('#id_notes').fill('Keep the original history and payment choice while correcting the range.');
}

async function expectBoundError(page, data) {
    await expect(page).toHaveURL(/\/transactions\/create\/$/);
    await expect(page.getByRole('alert').filter({ hasText: recurrenceError })).toBeVisible();
    await expect(page.locator('#id_title')).toHaveValue(title);
    await expect(page.locator('#id_amount')).toHaveValue('1.00');
    await expect(page.locator('#id_date')).toHaveValue('01/01/0001');
    await expect(page.locator('#id_transaction_type input[value="EXPENSE"]')).toBeChecked();
    await expect(page.locator('#id_category')).toHaveValue(data.category);
    await expect(page.locator('#id_payment_channel input[value="ACCOUNT"]')).toBeChecked();
    await expect(page.locator('#id_bank_account')).toHaveValue(data.account);
    await expect(page.locator('#id_is_fixed')).toBeChecked();
    await expect(page.locator('#id_fixed_until')).toHaveValue('');
    await expect(page.locator('#id_notes')).toHaveValue('Keep the original history and payment choice while correcting the range.');
    await expect(page.locator('.entry-advanced')).toHaveAttribute('open', '');
}

async function expectNoSavedHistory(page, data) {
    const inspection = await page.context().newPage();
    try {
        await inspection.goto('/transactions/');
        await expect(inspection.locator('#transaction-results-status')).toHaveText('0 transactions');
        await expect(inspection.locator('#transaction-results')).not.toContainText(title);
        await inspection.goto(`/banking/${data.bank}/`);
        await expect(inspection.locator(`#account-row-${data.account} [data-account-balance]`)).toHaveText(/^BRL 0[,.]00$/);
        await expect(inspection.locator('#bank-activity')).toHaveCount(0);
    } finally {
        await inspection.close();
    }
}

async function expectFinalActionsFit(page) {
    const save = page.getByRole('button', { name: 'Save', exact: true });
    const cancel = page.getByRole('link', { name: 'Cancel', exact: true });
    await page.locator('#id_notes').focus();
    await page.keyboard.press('Tab');
    await expect(save).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(cancel).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const navigation = page.locator('[data-app-navigation="mobile"]');
    const viewport = page.viewportSize();
    const bottom = await navigation.isVisible() ? (await navigation.boundingBox()).y : viewport.height;
    for (const action of [save, cancel]) {
        const box = await action.boundingBox();
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(viewport.width + 1);
        expect(box.y).toBeGreaterThanOrEqual(0);
        expect(box.y + box.height).toBeLessThanOrEqual(bottom + 1);
    }
}

async function correctToBoundedHistory(page, data) {
    const until = page.locator('#id_fixed_until');
    await until.focus();
    await page.keyboard.press('ControlOrMeta+A');
    // DMY: March 1 closes the original January start after three occurrences.
    await page.keyboard.type('01/03/0001');
    await page.keyboard.press('Tab');
    await expect(until).toHaveValue('01/03/0001');
    await page.getByRole('button', { name: 'Save', exact: true }).focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/transactions\/$/);
    await expect(page.locator('#transaction-results-status')).toHaveText('1 transaction');
    await expect(page.locator('#transaction-results')).toContainText(title);
    await page.goto(`/banking/${data.bank}/`);
    await expect(page.locator(`#account-row-${data.account} [data-account-balance]`)).toHaveText(/^BRL -3[,.]00$/);
    await page.locator('#bank-activity > summary').press('Enter');
    const movements = page.locator('.banking-section').filter({
        has: page.getByRole('heading', { name: 'Recent balance movements', exact: true }),
    });
    await expect(movements.locator('li')).toHaveCount(3);
    for (const date of ['01/01/0001', '01/02/0001', '01/03/0001']) {
        await expect(movements).toContainText(date);
    }
}

for (const theme of ['light', 'dark']) {
    for (const width of [1440, 390]) {
        test(`recurrence limit preserves keyboard recovery and bounded ancient history (${theme}, ${width}px)`, async ({ page }, testInfo) => {
            await page.addInitScript(value => localStorage.setItem('theme', value), theme);
            await page.setViewportSize({ width, height: 900 });
            const errors = [];
            page.on('pageerror', error => errors.push(error.message));
            const data = await prepare(page, testInfo);
            await enterUnboundedRecurrence(page, data);
            const response = page.waitForResponse(result => result.request().method() === 'POST'
                && new URL(result.url()).pathname === '/transactions/create/');
            await page.getByRole('button', { name: 'Save', exact: true }).focus();
            await page.keyboard.press('Enter');
            expect((await response).status()).toBe(200);
            await expectBoundError(page, data);
            await expect(page.locator('#id_bank_account + .search-choice').getByRole('option', { selected: true })
                .locator('.payment-choice-name')).toHaveText(accountName);
            await page.screenshot({ path: testInfo.outputPath('recurrence-invalid.png'), fullPage: true });
            await expectFinalActionsFit(page);
            await page.screenshot({ path: testInfo.outputPath('recurrence-invalid-actions.png') });
            await expectNoSavedHistory(page, data);
            await correctToBoundedHistory(page, data);
            expect(errors).toEqual([]);
        });
    }
}

test('recurrence limit has a complete native error and correction path without JavaScript', async ({ browser }, testInfo) => {
    const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 900 } });
    const page = await context.newPage();
    try {
        const data = await prepare(page, testInfo);
        await enterUnboundedRecurrence(page, data);
        const response = page.waitForResponse(result => result.request().method() === 'POST'
            && new URL(result.url()).pathname === '/transactions/create/');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        expect((await response).status()).toBe(200);
        await expectBoundError(page, data);
        await page.screenshot({ path: testInfo.outputPath('recurrence-native-invalid.png'), fullPage: true });
        await expectFinalActionsFit(page);
        await expectNoSavedHistory(page, data);
        await correctToBoundedHistory(page, data);
    } finally {
        await context.close();
    }
});

for (const theme of ['light', 'dark']) {
    test(`Reports island follows a recovery redirect with current assets (${theme})`, async ({ page }, testInfo) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({ width: 1440, height: 900 });
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        const data = await prepare(page, testInfo);
        await postForm(page, `/banking/accounts/${data.account}/edit/`, {
            bank: data.bank, name: accountName, currency: 'BRL',
            opening_balance: '137.42', opening_date: '2020-01-01',
        });
        await page.goto('/analytics/');
        await expect(page.getByRole('heading', { name: 'Analytics', exact: true })).toBeVisible();
        await expect(page.locator('#reports-charts')).toBeVisible();
        await expect(page.locator('#report-summary .metric-panel').first()).toContainText(/137[,.]42/);
        const revision = await page.locator('meta[name="tuxedo-assets"]').getAttribute('content');
        expect(revision).toBeTruthy();
        expect(await page.evaluate(() => window.TuxedoRuntimeAssets.revision)).toBe(revision);
        await page.screenshot({ path: testInfo.outputPath('reports-before-recovery.png') });

        const previous = page.locator('#report-balance-previous');
        await expect(previous).toHaveAttribute('hx-target', '#reports-charts');
        const periodUrl = new URL(await previous.getAttribute('href'), page.url()).href;
        const islandRequests = [];
        await page.route(periodUrl, route => {
            const request = route.request();
            islandRequests.push({ type: request.resourceType(), headers: request.headers() });
            // Emulate the middleware's recovery response. An empty 200 keeps
            // HX-Redirect visible to HTMX instead of following a 302 first.
            return route.fulfill({
                status: 200,
                headers: {
                    'Content-Type': 'text/html; charset=utf-8',
                    'HX-Redirect': '/transactions/',
                    'X-Tuxedo-Assets': revision,
                },
                body: '',
            });
        });
        const freshDestination = page.waitForResponse(response => response.request().isNavigationRequest()
            && response.request().method() === 'GET'
            && new URL(response.url()).pathname === '/transactions/');
        await previous.focus();
        await page.keyboard.press('Enter');
        expect((await freshDestination).status()).toBe(200);
        await expect(page).toHaveURL(/\/transactions\/$/);
        await page.waitForLoadState('load');
        expect(islandRequests).toHaveLength(1);
        expect(islandRequests[0].type).toBe('xhr');
        expect(islandRequests[0].headers['hx-request']).toBe('true');
        expect(islandRequests[0].headers['hx-target']).toBe('reports-charts');
        expect(islandRequests[0].headers['x-tuxedo-assets']).toBe(revision);
        await expect(page.getByRole('heading', { name: 'Transactions', exact: true })).toBeVisible();
        await expect(page.locator('#transaction-results-status')).toHaveText('0 transactions');
        await expect(page.locator('#transaction-apply-filters')).toBeHidden();
        expect(await page.evaluate(() => window.TuxedoRuntimeAssets.revision)).toBe(revision);
        await expect(page.locator('#reports-charts, #report-summary, #balance-evolution')).toHaveCount(0);
        await expect(page.locator('main')).not.toContainText(/137[,.]42/);
        await page.screenshot({ path: testInfo.outputPath('transactions-after-reports-recovery.png') });
        expect(errors).toEqual([]);
    });
}
